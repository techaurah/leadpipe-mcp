"""Shared enums, normalisation helpers, and pydantic input models.

Pure helpers (email/phone normalisation, dedup keys, idempotency key) live
here or in the pure-logic modules and take no I/O.
"""

from __future__ import annotations

import hashlib
import re
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from . import errors

# ---------------------------------------------------------------------------
# Enums (SPEC Sections 2.1, 2.4, 2.5.1)
# ---------------------------------------------------------------------------


class Source(StrEnum):
    WEBSITE = "website"
    INSTAGRAM = "instagram"
    FACEBOOK = "facebook"
    WHATSAPP = "whatsapp"
    EMAIL = "email"
    REFERRAL = "referral"
    CALL = "call"
    WALK_IN = "walk_in"
    OTHER = "other"


class Stage(StrEnum):
    NEW = "NEW"
    CONTACTED = "CONTACTED"
    QUALIFIED = "QUALIFIED"
    NURTURE = "NURTURE"
    DISCOVERY = "DISCOVERY"
    BOOKED = "BOOKED"
    PROPOSAL = "PROPOSAL"
    NEGOTIATION = "NEGOTIATION"
    WON = "WON"
    LOST = "LOST"


class Band(StrEnum):
    HOT = "HOT"
    WARM = "WARM"
    NURTURE = "NURTURE"
    LOW = "LOW"


class WriteMode(StrEnum):
    DIRECT = "direct"
    DRY_RUN = "dry_run"
    APPROVAL = "approval"


# ---------------------------------------------------------------------------
# Normalisation and keys (pure logic, SPEC Sections 2.1 and 2.7)
# ---------------------------------------------------------------------------

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def normalise_email(raw: str) -> str:
    """Trim and lowercase an email address; reject unparseable values."""
    email = raw.strip().lower()
    if not _EMAIL_RE.match(email):
        raise errors.validation(f"Unparseable email address: {raw!r}", "email")
    return email


def normalise_phone(raw: str) -> str:
    """Strip spaces, dashes and brackets; convert a leading 00 to +."""
    phone = re.sub(r"[\s\-()]", "", raw.strip())
    if phone.startswith("00"):
        phone = "+" + phone[2:]
    if not re.fullmatch(r"\+?\d{7,15}", phone):
        raise errors.validation(f"Unparseable phone number: {raw!r}", "phone")
    return phone


def idempotency_key(lead_id: str, start_iso: str, end_iso: str) -> str:
    """sha256 of ``lead_id|start|end``, first 32 hex chars (SPEC 2.7)."""
    digest = hashlib.sha256(f"{lead_id}|{start_iso}|{end_iso}".encode()).hexdigest()
    return digest[:32]


# ---------------------------------------------------------------------------
# Input models. extra="forbid" so unknown fields (e.g. a caller-supplied
# score_total) are rejected rather than silently accepted (SPEC Section 7).
# ---------------------------------------------------------------------------


class _Args(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CaptureLeadArgs(_Args):
    name: str
    email: str | None = None
    phone: str | None = None
    company: str | None = None
    source: str
    service_interest: str | None = None
    location: str | None = None
    problem_notes: str | None = None
    dry_run: bool = False
    confirm: bool = False


class GetLeadArgs(_Args):
    lead_id: str | None = None
    email: str | None = None
    phone: str | None = None


class ListHotLeadsArgs(_Args):
    limit: int = 20
    include_booked: bool = False


class ScoreLeadArgs(_Args):
    lead_id: str
    scores: dict
    dry_run: bool = False
    confirm: bool = False


class UpdateStageArgs(_Args):
    lead_id: str
    stage: str
    note: str | None = None
    dry_run: bool = False
    confirm: bool = False


class CheckAvailabilityArgs(_Args):
    start: str
    end: str
    slot_minutes: int = 30


class BookAppointmentArgs(_Args):
    lead_id: str
    start: str
    end: str
    title: str | None = None
    notes: str | None = None
    dry_run: bool = False
    confirm: bool = False


class DailySummaryArgs(_Args):
    date: str | None = Field(default=None)
