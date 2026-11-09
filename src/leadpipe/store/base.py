"""Store and calendar protocols (SPEC Section 6.2).

Tool wrappers depend only on these interfaces. The production
implementation talks to Google Sheets and Calendar; the fake implements
the same surface in memory for demo mode and the whole test suite.
Rows are plain dicts keyed by the schema headers; values are strings,
exactly as they would appear in a Sheet cell.
"""

from __future__ import annotations

from datetime import datetime
from typing import Protocol, runtime_checkable


@runtime_checkable
class LeadStore(Protocol):
    # -- schema / bootstrap primitives -------------------------------------
    def has_tab(self, tab: str) -> bool: ...

    def get_headers(self, tab: str) -> list[str]: ...

    def create_tab(self, tab: str, headers: list[str]) -> None: ...

    def get_meta(self, key: str) -> str | None: ...

    def set_meta(self, key: str, value: str) -> None: ...

    def allocate_lead_seq(self) -> int:
        """Atomically read Meta.next_lead_seq, advance it by one, and
        return the value that was read. Raises SCHEMA_MISMATCH when the
        counter is missing. Allocation lives in the store so the
        read-modify-write happens under the store's lock; callers must
        not advance the counter themselves."""
        ...

    # -- leads --------------------------------------------------------------
    def list_leads(self) -> list[dict[str, str]]: ...

    def append_lead(self, row: dict[str, str]) -> None: ...

    def update_lead(self, lead_id: str, changes: dict[str, str]) -> None: ...

    # -- audit ---------------------------------------------------------------
    def append_audit(self, entry: dict[str, str]) -> None: ...

    def list_audit(self) -> list[dict[str, str]]: ...


@runtime_checkable
class CalendarClient(Protocol):
    def freebusy(
        self, start: datetime, end: datetime
    ) -> list[tuple[datetime, datetime]]: ...

    def find_event_by_key(self, key: str) -> dict | None: ...

    def create_event(
        self,
        *,
        start: datetime,
        end: datetime,
        title: str,
        description: str,
        lead_id: str,
        idempotency_key: str,
    ) -> dict: ...

    def list_events(self, start: datetime, end: datetime) -> list[dict]: ...
