"""Google Sheets + Calendar implementation of the store protocols.

The Google client libraries are imported lazily, inside the constructor,
so importing this module (and running the whole core and test suite)
never requires them. Constructing a real client without credentials
raises a clear CONFIG_ERROR instead of a stack trace.

Only two API scopes are requested (SPEC Section 4.4): spreadsheets, and
calendar events. The credentials file is referenced by path only; its
contents are never logged or returned.
"""

from __future__ import annotations

import os
import threading
from datetime import UTC, datetime

from .. import errors
from ..config import Config
from . import schema

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/calendar.events",
    # Read-only calendar metadata, used only for free/busy queries.
    "https://www.googleapis.com/auth/calendar.readonly",
]


def _load_google(config: Config):
    """Return (sheets_service, calendar_service) or raise CONFIG_ERROR."""
    config.require_google()
    assert config.credentials_path is not None
    if not os.path.exists(config.credentials_path):
        raise errors.LeadPipeError(
            errors.CONFIG_ERROR,
            "GOOGLE_APPLICATION_CREDENTIALS points to a file that does not "
            f"exist: {config.credentials_path}. Create a Google Cloud "
            "service account key (or OAuth client file), share the Sheet "
            "with the service account, and set the path again.",
        )
    try:
        from google.oauth2 import service_account
        from googleapiclient.discovery import build
    except ImportError:
        raise errors.LeadPipeError(
            errors.CONFIG_ERROR,
            "Google client libraries are not installed. Install them with: "
            "pip install 'leadpipe-mcp[google]'",
        ) from None
    try:
        creds = service_account.Credentials.from_service_account_file(
            config.credentials_path, scopes=SCOPES
        )
        sheets = build("sheets", "v4", credentials=creds, cache_discovery=False)
        calendar = build("calendar", "v3", credentials=creds, cache_discovery=False)
    except Exception as exc:  # invalid key file, unsupported credential type
        raise errors.LeadPipeError(
            errors.CONFIG_ERROR,
            "Could not load Google credentials from the configured file. "
            "A service account key JSON is expected in v0.1. "
            f"Underlying error type: {type(exc).__name__}.",
        ) from None
    return sheets, calendar


def _iso(dt: datetime) -> str:
    return dt.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _parse_iso(raw: str) -> datetime:
    return datetime.fromisoformat(raw.replace("Z", "+00:00"))


class GoogleSheetsStore:
    """LeadStore backed by one Google Sheet with the SPEC 3.1 schema."""

    def __init__(self, config: Config) -> None:
        self._config = config
        self._sheets, _ = _load_google(config)
        self._sheet_id = config.sheet_id
        self._seq_lock = threading.Lock()

    # -- low-level helpers -------------------------------------------------
    def _values(self, range_: str) -> list[list[str]]:
        try:
            result = (
                self._sheets.spreadsheets()
                .values()
                .get(spreadsheetId=self._sheet_id, range=range_)
                .execute()
            )
        except Exception as exc:
            raise errors.LeadPipeError(
                errors.GOOGLE_API_ERROR,
                f"Google Sheets read failed ({type(exc).__name__}).",
            ) from None
        return result.get("values", [])

    def _update(self, range_: str, values: list[list[str]]) -> None:
        try:
            (
                self._sheets.spreadsheets()
                .values()
                .update(
                    spreadsheetId=self._sheet_id,
                    range=range_,
                    valueInputOption="RAW",
                    body={"values": values},
                )
                .execute()
            )
        except Exception as exc:
            raise errors.LeadPipeError(
                errors.GOOGLE_API_ERROR,
                f"Google Sheets write failed ({type(exc).__name__}).",
            ) from None

    def _append(self, tab: str, values: list[list[str]]) -> None:
        try:
            (
                self._sheets.spreadsheets()
                .values()
                .append(
                    spreadsheetId=self._sheet_id,
                    range=tab,
                    valueInputOption="RAW",
                    insertDataOption="INSERT_ROWS",
                    body={"values": values},
                )
                .execute()
            )
        except Exception as exc:
            raise errors.LeadPipeError(
                errors.GOOGLE_API_ERROR,
                f"Google Sheets append failed ({type(exc).__name__}).",
            ) from None

    def _tab_names(self) -> list[str]:
        try:
            meta = (
                self._sheets.spreadsheets().get(spreadsheetId=self._sheet_id).execute()
            )
        except Exception as exc:
            raise errors.LeadPipeError(
                errors.GOOGLE_API_ERROR,
                f"Google Sheets metadata read failed ({type(exc).__name__}).",
            ) from None
        return [s["properties"]["title"] for s in meta.get("sheets", [])]

    def _rows_as_dicts(self, tab: str) -> list[dict[str, str]]:
        values = self._values(tab)
        if len(values) < 2:
            return []
        headers = values[0]
        rows = []
        for raw in values[1:]:
            padded = list(raw) + [""] * (len(headers) - len(raw))
            rows.append(dict(zip(headers, padded, strict=False)))
        return rows

    # -- schema primitives ---------------------------------------------------
    def has_tab(self, tab: str) -> bool:
        return tab in self._tab_names()

    def get_headers(self, tab: str) -> list[str]:
        values = self._values(f"{tab}!1:1")
        return values[0] if values else []

    def create_tab(self, tab: str, headers: list[str]) -> None:
        try:
            (
                self._sheets.spreadsheets()
                .batchUpdate(
                    spreadsheetId=self._sheet_id,
                    body={"requests": [{"addSheet": {"properties": {"title": tab}}}]},
                )
                .execute()
            )
        except Exception as exc:
            raise errors.LeadPipeError(
                errors.GOOGLE_API_ERROR,
                f"Could not create tab {tab!r} ({type(exc).__name__}).",
            ) from None
        self._update(f"{tab}!A1", [headers])

    def get_meta(self, key: str) -> str | None:
        for row in self._rows_as_dicts(schema.TAB_META):
            if row.get("key") == key:
                return row.get("value", "")
        return None

    def set_meta(self, key: str, value: str) -> None:
        values = self._values(schema.TAB_META)
        for idx, raw in enumerate(values[1:], start=2):
            if raw and raw[0] == key:
                self._update(f"{schema.TAB_META}!A{idx}:B{idx}", [[key, value]])
                return
        self._append(schema.TAB_META, [[key, value]])

    def allocate_lead_seq(self) -> int:
        # The Sheets API has no compare-and-swap for a single cell, so
        # this lock only serialises allocators inside this process. The
        # server runs as one process per Sheet, which is the guarantee
        # this provides; two server processes pointed at the same Sheet
        # could still interleave and mint a duplicate ID.
        with self._seq_lock:
            raw = self.get_meta("next_lead_seq")
            if raw is None:
                raise errors.LeadPipeError(
                    errors.SCHEMA_MISMATCH,
                    "Meta.next_lead_seq is missing. Run bootstrap.",
                )
            seq = int(raw)
            self.set_meta("next_lead_seq", str(seq + 1))
            return seq

    # -- leads -----------------------------------------------------------------
    def list_leads(self) -> list[dict[str, str]]:
        if not self.has_tab(schema.TAB_LEADS):
            raise errors.LeadPipeError(
                errors.SCHEMA_MISMATCH, "Leads tab is missing. Run bootstrap first."
            )
        schema.validate_headers(schema.TAB_LEADS, self.get_headers(schema.TAB_LEADS))
        return self._rows_as_dicts(schema.TAB_LEADS)

    def append_lead(self, row: dict[str, str]) -> None:
        self._append(schema.TAB_LEADS, [[row.get(h, "") for h in schema.LEADS_HEADERS]])

    def update_lead(self, lead_id: str, changes: dict[str, str]) -> None:
        values = self._values(schema.TAB_LEADS)
        headers = values[0]
        for idx, raw in enumerate(values[1:], start=2):
            if raw and raw[0] == lead_id:
                current = dict(
                    zip(
                        headers,
                        list(raw) + [""] * (len(headers) - len(raw)),
                        strict=False,
                    )
                )
                current.update({k: v for k, v in changes.items() if k != "lead_id"})
                self._update(
                    f"{schema.TAB_LEADS}!A{idx}",
                    [[current.get(h, "") for h in headers]],
                )
                return
        raise errors.not_found(lead_id)

    # -- audit -------------------------------------------------------------------
    def append_audit(self, entry: dict[str, str]) -> None:
        self._append(
            schema.TAB_AUDIT, [[entry.get(h, "") for h in schema.AUDIT_HEADERS]]
        )

    def list_audit(self) -> list[dict[str, str]]:
        return self._rows_as_dicts(schema.TAB_AUDIT)


class GoogleCalendarClient:
    """CalendarClient backed by the Google Calendar API."""

    def __init__(self, config: Config) -> None:
        self._config = config
        _, self._calendar = _load_google(config)
        self._calendar_id = config.calendar_id

    def freebusy(
        self, start: datetime, end: datetime
    ) -> list[tuple[datetime, datetime]]:
        try:
            result = (
                self._calendar.freebusy()
                .query(
                    body={
                        "timeMin": _iso(start),
                        "timeMax": _iso(end),
                        "items": [{"id": self._calendar_id}],
                    }
                )
                .execute()
            )
        except Exception as exc:
            raise errors.LeadPipeError(
                errors.GOOGLE_API_ERROR,
                f"Calendar free/busy query failed ({type(exc).__name__}).",
            ) from None
        busy = result["calendars"][self._calendar_id]["busy"]
        # Titles are never read or returned: times only (SPEC 2.6).
        return sorted((_parse_iso(b["start"]), _parse_iso(b["end"])) for b in busy)

    def _event_to_dict(self, event: dict) -> dict:
        props = event.get("extendedProperties", {}).get("private", {})
        return {
            "id": event["id"],
            "start": _parse_iso(event["start"]["dateTime"]),
            "end": _parse_iso(event["end"]["dateTime"]),
            "title": event.get("summary", ""),
            "description": event.get("description", ""),
            "lead_id": props.get("leadpipe_lead_id", ""),
            "idempotency_key": props.get("leadpipe_idempotency_key", ""),
            "html_link": event.get("htmlLink", ""),
        }

    def find_event_by_key(self, key: str) -> dict | None:
        try:
            result = (
                self._calendar.events()
                .list(
                    calendarId=self._calendar_id,
                    privateExtendedProperty=f"leadpipe_idempotency_key={key}",
                    maxResults=1,
                )
                .execute()
            )
        except Exception as exc:
            raise errors.LeadPipeError(
                errors.GOOGLE_API_ERROR,
                f"Calendar event lookup failed ({type(exc).__name__}).",
            ) from None
        items = result.get("items", [])
        return self._event_to_dict(items[0]) if items else None

    def create_event(
        self,
        *,
        start: datetime,
        end: datetime,
        title: str,
        description: str,
        lead_id: str,
        idempotency_key: str,
    ) -> dict:
        body = {
            "summary": title,
            "description": description,
            "start": {"dateTime": _iso(start)},
            "end": {"dateTime": _iso(end)},
            # No attendees in v0.1: nothing is ever sent to a lead (SPEC 4.2).
            "extendedProperties": {
                "private": {
                    "leadpipe_lead_id": lead_id,
                    "leadpipe_idempotency_key": idempotency_key,
                }
            },
        }
        try:
            event = (
                self._calendar.events()
                .insert(calendarId=self._calendar_id, body=body, sendUpdates="none")
                .execute()
            )
        except Exception as exc:
            raise errors.LeadPipeError(
                errors.GOOGLE_API_ERROR,
                f"Calendar event creation failed ({type(exc).__name__}).",
            ) from None
        return self._event_to_dict(event)

    def list_events(self, start: datetime, end: datetime) -> list[dict]:
        try:
            result = (
                self._calendar.events()
                .list(
                    calendarId=self._calendar_id,
                    timeMin=_iso(start),
                    timeMax=_iso(end),
                    singleEvents=True,
                    orderBy="startTime",
                )
                .execute()
            )
        except Exception as exc:
            raise errors.LeadPipeError(
                errors.GOOGLE_API_ERROR,
                f"Calendar event listing failed ({type(exc).__name__}).",
            ) from None
        return [self._event_to_dict(e) for e in result.get("items", [])]


def build_clients(config: Config):
    """Return (LeadStore, CalendarClient) for real mode."""
    return GoogleSheetsStore(config), GoogleCalendarClient(config)
