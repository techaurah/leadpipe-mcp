"""Tool wrappers: thin layers over the pure logic and the store protocol.

Every tool returns a single JSON-able dict in the SPEC 6.3 shape:
``{"ok": True, ...}`` or ``{"ok": False, "error": {...}}``.
Write-mode enforcement (SPEC 4.1) lives here so all four writing tools
behave identically:

- per-call ``dry_run=True`` forces a dry run; it can never upgrade a call.
- ``approval`` mode without ``confirm=True`` previews and writes nothing.
- ``confirm`` never executes in dry-run mode.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass

from pydantic import ValidationError

from .. import errors
from .. import scoring as _core_scoring
from ..config import Config
from ..models import WriteMode
from ..store import schema


@dataclass
class ToolContext:
    store: object  # LeadStore protocol
    calendar: object  # CalendarClient protocol
    config: Config


def resolve_write_mode(config: Config, dry_run: bool) -> WriteMode:
    """Effective mode for one call. A per-call flag can only make a call
    drier, never the reverse (SPEC 4.1)."""
    if dry_run:
        return WriteMode.DRY_RUN
    return config.write_mode


def audit(
    ctx: ToolContext,
    action: str,
    lead_id: str,
    detail: dict,
    mode: WriteMode,
) -> bool:
    """Append an AuditLog entry. Returns False instead of failing if the
    audit write itself is impossible (e.g. read-only Sheets scope)."""
    entry = {
        "timestamp": schema.utc_now_iso(),
        "action": action,
        "lead_id": lead_id,
        "detail": json.dumps(detail, sort_keys=True),
        "mode": mode.value,
        "actor": schema.ACTOR,
    }
    try:
        ctx.store.append_audit(entry)  # type: ignore[attr-defined]
        return True
    except errors.LeadPipeError:
        return False


def find_lead(ctx: ToolContext, lead_id: str) -> dict:
    for row in ctx.store.list_leads():  # type: ignore[attr-defined]
        if row.get("lead_id") == lead_id:
            return row
    raise errors.not_found(lead_id)


def recompute(row: dict) -> tuple[int | None, str | None]:
    """(score_total, band) recomputed from stored components, or
    (None, None) when the lead has not been scored."""
    components = _core_scoring.components_from_row(row)
    if components is None:
        return None, None
    total = _core_scoring.compute_total(components)
    return total, _core_scoring.band_for(total).value


def approval_result(preview: dict) -> dict:
    return {
        "ok": False,
        "error": {
            "code": errors.APPROVAL_REQUIRED,
            "message": (
                "Write mode is 'approval'. Review the preview, then repeat "
                "the call with confirm=true to execute."
            ),
            "field": None,
        },
        "preview": preview,
    }


# ---------------------------------------------------------------------------
# Dispatch: validate args with the pydantic models, call the tool, and map
# every LeadPipeError onto the shared error format.
# ---------------------------------------------------------------------------


def _validate(model_cls, kwargs: dict):
    try:
        return model_cls(**kwargs)
    except ValidationError as exc:
        first: dict = dict(exc.errors()[0]) if exc.errors() else {}
        field = ".".join(str(p) for p in first.get("loc", [])) or None
        raise errors.validation(
            f"Invalid arguments: {first.get('msg', 'validation failed')}", field
        ) from None


def dispatch(ctx: ToolContext, tool_name: str, **kwargs) -> dict:
    from . import calendar_tools, capture, leads
    from . import scoring as scoring_tools
    from . import stages as stages_tools

    registry: dict[str, tuple[Callable, object]] = {
        "capture_lead": (capture.capture_lead, capture.CaptureLeadArgs),
        "get_lead": (leads.get_lead, leads.GetLeadArgs),
        "list_hot_leads": (leads.list_hot_leads, leads.ListHotLeadsArgs),
        "score_lead": (scoring_tools.score_lead, scoring_tools.ScoreLeadArgs),
        "update_stage": (stages_tools.update_stage, stages_tools.UpdateStageArgs),
        "check_availability": (
            calendar_tools.check_availability,
            calendar_tools.CheckAvailabilityArgs,
        ),
        "book_appointment": (
            calendar_tools.book_appointment,
            calendar_tools.BookAppointmentArgs,
        ),
        "daily_pipeline_summary": (
            leads.daily_pipeline_summary,
            leads.DailySummaryArgs,
        ),
    }
    if tool_name not in registry:
        return errors.LeadPipeError(
            errors.VALIDATION_ERROR, f"Unknown tool: {tool_name}"
        ).to_result()
    fn, model_cls = registry[tool_name]
    try:
        args = _validate(model_cls, kwargs)
        return fn(ctx, args)
    except errors.LeadPipeError as exc:
        return exc.to_result()


TOOL_NAMES = (
    "capture_lead",
    "get_lead",
    "list_hot_leads",
    "score_lead",
    "update_stage",
    "check_availability",
    "book_appointment",
    "daily_pipeline_summary",
)
