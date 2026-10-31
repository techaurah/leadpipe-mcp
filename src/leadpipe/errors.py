"""Error types and the closed error-code set (SPEC Section 6.3)."""

from __future__ import annotations

VALIDATION_ERROR = "VALIDATION_ERROR"
LEAD_NOT_FOUND = "LEAD_NOT_FOUND"
STAGE_TRANSITION_INVALID = "STAGE_TRANSITION_INVALID"
SLOT_UNAVAILABLE = "SLOT_UNAVAILABLE"
APPROVAL_REQUIRED = "APPROVAL_REQUIRED"
SCHEMA_MISMATCH = "SCHEMA_MISMATCH"
CONFIG_ERROR = "CONFIG_ERROR"
GOOGLE_API_ERROR = "GOOGLE_API_ERROR"

ERROR_CODES = frozenset(
    {
        VALIDATION_ERROR,
        LEAD_NOT_FOUND,
        STAGE_TRANSITION_INVALID,
        SLOT_UNAVAILABLE,
        APPROVAL_REQUIRED,
        SCHEMA_MISMATCH,
        CONFIG_ERROR,
        GOOGLE_API_ERROR,
    }
)


class LeadPipeError(Exception):
    """An error that maps directly onto the tool error format."""

    def __init__(self, code: str, message: str, field: str | None = None) -> None:
        if code not in ERROR_CODES:
            raise ValueError(f"Unknown error code: {code}")
        super().__init__(message)
        self.code = code
        self.message = message
        self.field = field

    def to_result(self) -> dict:
        return {
            "ok": False,
            "error": {"code": self.code, "message": self.message, "field": self.field},
        }


def validation(message: str, field: str | None = None) -> LeadPipeError:
    return LeadPipeError(VALIDATION_ERROR, message, field)


def not_found(lead_id: str) -> LeadPipeError:
    return LeadPipeError(LEAD_NOT_FOUND, f"No lead found for {lead_id!r}.", "lead_id")
