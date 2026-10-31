"""Environment-only configuration (SPEC Section 4.3).

No credential, token or key value is ever a tool input or output. The
Google credentials file is referenced by path only; its contents are
never read by this module, logged, or written anywhere.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from datetime import time
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from . import errors
from .models import WriteMode

DEFAULT_TIMEZONE = "UTC"
DEFAULT_BUSINESS_HOURS = "09:00-17:00"
# Monday=0 .. Friday=4
DEFAULT_BUSINESS_DAYS = (0, 1, 2, 3, 4)

_HOURS_RE = re.compile(r"^(\d{2}):(\d{2})-(\d{2}):(\d{2})$")


def parse_business_hours(raw: str) -> tuple[time, time]:
    match = _HOURS_RE.match(raw.strip())
    if not match:
        raise errors.LeadPipeError(
            errors.CONFIG_ERROR,
            f"LEADPIPE_BUSINESS_HOURS must look like '09:00-17:00', got {raw!r}.",
        )
    h1, m1, h2, m2 = (int(g) for g in match.groups())
    try:
        return time(h1, m1), time(h2, m2)
    except ValueError:
        raise errors.LeadPipeError(
            errors.CONFIG_ERROR, f"Invalid business hours: {raw!r}."
        ) from None


@dataclass(frozen=True)
class Config:
    sheet_id: str | None = None
    calendar_id: str | None = None
    credentials_path: str | None = None
    write_mode: WriteMode = WriteMode.APPROVAL
    timezone_name: str = DEFAULT_TIMEZONE
    business_hours: str = DEFAULT_BUSINESS_HOURS
    business_days: tuple[int, ...] = field(default=DEFAULT_BUSINESS_DAYS)
    demo: bool = False

    @property
    def tz(self) -> ZoneInfo:
        try:
            return ZoneInfo(self.timezone_name)
        except ZoneInfoNotFoundError:
            raise errors.LeadPipeError(
                errors.CONFIG_ERROR, f"Unknown IANA timezone: {self.timezone_name!r}."
            ) from None

    @property
    def business_window(self) -> tuple[time, time]:
        return parse_business_hours(self.business_hours)

    @classmethod
    def from_env(cls, env: dict[str, str] | None = None) -> Config:
        source = os.environ if env is None else env
        demo = source.get("LEADPIPE_DEMO", "").strip() in ("1", "true", "TRUE")
        raw_mode = source.get("LEADPIPE_WRITE_MODE", "").strip().lower()
        if raw_mode:
            try:
                mode = WriteMode(raw_mode)
            except ValueError:
                raise errors.LeadPipeError(
                    errors.CONFIG_ERROR,
                    "LEADPIPE_WRITE_MODE must be one of: direct, dry_run, approval.",
                ) from None
        else:
            # Demo defaults to direct; real credentials default to approval.
            mode = WriteMode.DIRECT if demo else WriteMode.APPROVAL
        return cls(
            sheet_id=source.get("LEADPIPE_SHEET_ID") or None,
            calendar_id=source.get("LEADPIPE_CALENDAR_ID") or None,
            credentials_path=source.get("GOOGLE_APPLICATION_CREDENTIALS") or None,
            write_mode=mode,
            timezone_name=source.get("LEADPIPE_TIMEZONE") or DEFAULT_TIMEZONE,
            business_hours=source.get("LEADPIPE_BUSINESS_HOURS")
            or DEFAULT_BUSINESS_HOURS,
            demo=demo,
        )

    def require_google(self) -> None:
        """Raise a clear CONFIG_ERROR when real-mode prerequisites are absent."""
        missing = []
        if not self.sheet_id:
            missing.append("LEADPIPE_SHEET_ID")
        if not self.calendar_id:
            missing.append("LEADPIPE_CALENDAR_ID")
        if not self.credentials_path:
            missing.append("GOOGLE_APPLICATION_CREDENTIALS")
        if missing:
            raise errors.LeadPipeError(
                errors.CONFIG_ERROR,
                "Missing required configuration: "
                + ", ".join(missing)
                + ". Set them in the environment (see .env.example), "
                "or run in demo mode with LEADPIPE_DEMO=1.",
            )
