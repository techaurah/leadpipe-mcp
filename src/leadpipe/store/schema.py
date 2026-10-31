"""Sheet schema (SPEC Section 3.1) and bootstrap logic (SPEC Section 3.3).

Column order is part of the contract. Bootstrap creates missing tabs and
initialises Meta, but never rewrites a user's data: a tab whose headers
do not match exactly aborts the run with SCHEMA_MISMATCH.
"""

from __future__ import annotations

from datetime import UTC, datetime

from .. import errors

SCHEMA_VERSION = "1"

TAB_LEADS = "Leads"
TAB_AUDIT = "AuditLog"
TAB_META = "Meta"

LEADS_HEADERS = [
    "lead_id",
    "created_at",
    "updated_at",
    "name",
    "email",
    "phone",
    "company",
    "source",
    "service_interest",
    "location",
    "problem_notes",
    "score_problem",
    "score_fit",
    "score_value",
    "score_size",
    "score_pay",
    "score_access",
    "score_urgency",
    "score_activity",
    "score_total",
    "band",
    "stage",
    "owner",
    "next_action",
    "next_action_date",
    "appointment_id",
    "appointment_start",
    "appointment_status",
    "last_contact_at",
]

AUDIT_HEADERS = ["timestamp", "action", "lead_id", "detail", "mode", "actor"]

META_HEADERS = ["key", "value"]

TAB_HEADERS: dict[str, list[str]] = {
    TAB_LEADS: LEADS_HEADERS,
    TAB_AUDIT: AUDIT_HEADERS,
    TAB_META: META_HEADERS,
}

ACTOR = "leadpipe-mcp"


def utc_now_iso(now: datetime | None = None) -> str:
    moment = now or datetime.now(UTC)
    return moment.astimezone(UTC).isoformat().replace("+00:00", "Z")


def validate_headers(tab: str, actual: list[str]) -> None:
    expected = TAB_HEADERS[tab]
    if list(actual) != expected:
        raise errors.LeadPipeError(
            errors.SCHEMA_MISMATCH,
            f"Tab {tab!r} headers do not match the LeadPipe schema. "
            f"Expected {expected}, found {list(actual)}. Nothing was changed.",
        )


def bootstrap_store(store, now: datetime | None = None) -> dict:
    """Create missing tabs/headers and initialise Meta. Idempotent.

    Validation of all existing tabs happens before any creation, so a
    mismatch aborts with nothing changed.
    """
    for tab in TAB_HEADERS:
        if store.has_tab(tab):
            validate_headers(tab, store.get_headers(tab))
    created_tabs: list[str] = []
    for tab, headers in TAB_HEADERS.items():
        if not store.has_tab(tab):
            store.create_tab(tab, headers)
            created_tabs.append(tab)
    meta_initialised = False
    defaults = {
        "schema_version": SCHEMA_VERSION,
        "next_lead_seq": "1",
        "created_by": "leadpipe-bootstrap",
        "created_at": utc_now_iso(now),
    }
    for key, value in defaults.items():
        if store.get_meta(key) is None:
            store.set_meta(key, value)
            meta_initialised = True
    return {
        "created_tabs": created_tabs,
        "meta_initialised": meta_initialised,
        "schema_version": SCHEMA_VERSION,
    }
