"""FakeGoogleClient: in-memory store + calendar (SPEC Section 5).

Implements the same protocols as the Google implementation. No network,
no credentials; all state resets when the object is dropped. Used by
demo mode and by every test.
"""

from __future__ import annotations

import itertools
import threading
from datetime import datetime

from .. import errors
from . import schema


class FakeGoogleClient:
    def __init__(self) -> None:
        self._tabs: dict[str, dict] = {}
        self._events: list[dict] = []
        self._event_seq = itertools.count(1)
        self._seq_lock = threading.Lock()

    # -- schema primitives ---------------------------------------------------
    def has_tab(self, tab: str) -> bool:
        return tab in self._tabs

    def get_headers(self, tab: str) -> list[str]:
        return list(self._tabs[tab]["headers"])

    def create_tab(self, tab: str, headers: list[str]) -> None:
        if tab in self._tabs:
            return
        self._tabs[tab] = {"headers": list(headers), "rows": []}

    def get_meta(self, key: str) -> str | None:
        for row in self._rows(schema.TAB_META):
            if row.get("key") == key:
                return row.get("value", "")
        return None

    def set_meta(self, key: str, value: str) -> None:
        rows = self._rows(schema.TAB_META)
        for row in rows:
            if row.get("key") == key:
                row["value"] = value
                return
        rows.append({"key": key, "value": value})

    def allocate_lead_seq(self) -> int:
        # The read and the write-back happen under one lock so two
        # threads can never be handed the same sequence value.
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

    # -- leads ----------------------------------------------------------------
    def _rows(self, tab: str) -> list[dict]:
        if tab not in self._tabs:
            return []
        return self._tabs[tab]["rows"]

    def list_leads(self) -> list[dict[str, str]]:
        self._require_schema()
        return [dict(r) for r in self._rows(schema.TAB_LEADS)]

    def append_lead(self, row: dict[str, str]) -> None:
        self._require_schema()
        full = {h: str(row.get(h, "")) for h in schema.LEADS_HEADERS}
        self._tabs[schema.TAB_LEADS]["rows"].append(full)

    def update_lead(self, lead_id: str, changes: dict[str, str]) -> None:
        self._require_schema()
        for row in self._tabs[schema.TAB_LEADS]["rows"]:
            if row["lead_id"] == lead_id:
                for key, value in changes.items():
                    if key in schema.LEADS_HEADERS and key != "lead_id":
                        row[key] = str(value)
                return
        raise errors.not_found(lead_id)

    # -- audit ------------------------------------------------------------------
    def append_audit(self, entry: dict[str, str]) -> None:
        if not self.has_tab(schema.TAB_AUDIT):
            raise errors.LeadPipeError(
                errors.SCHEMA_MISMATCH,
                "AuditLog tab is missing. Run bootstrap first.",
            )
        full = {h: str(entry.get(h, "")) for h in schema.AUDIT_HEADERS}
        self._tabs[schema.TAB_AUDIT]["rows"].append(full)

    def list_audit(self) -> list[dict[str, str]]:
        return [dict(r) for r in self._rows(schema.TAB_AUDIT)]

    # -- calendar ---------------------------------------------------------------
    def freebusy(
        self, start: datetime, end: datetime
    ) -> list[tuple[datetime, datetime]]:
        return sorted(
            (e["start"], e["end"])
            for e in self._events
            if e["start"] < end and start < e["end"]
        )

    def find_event_by_key(self, key: str) -> dict | None:
        for event in self._events:
            if event["idempotency_key"] == key:
                return dict(event)
        return None

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
        event_id = f"fake-event-{next(self._event_seq):04d}"
        event = {
            "id": event_id,
            "start": start,
            "end": end,
            "title": title,
            "description": description,
            "lead_id": lead_id,
            "idempotency_key": idempotency_key,
            "html_link": f"https://calendar.example.test/event/{event_id}",
        }
        self._events.append(event)
        return dict(event)

    def list_events(self, start: datetime, end: datetime) -> list[dict]:
        return [dict(e) for e in self._events if e["start"] < end and start < e["end"]]

    # -- helpers ------------------------------------------------------------------
    def _require_schema(self) -> None:
        if not self.has_tab(schema.TAB_LEADS):
            raise errors.LeadPipeError(
                errors.SCHEMA_MISMATCH,
                "Leads tab is missing. Run bootstrap first.",
            )
