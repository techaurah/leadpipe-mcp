"""update_stage tool wrapper (SPEC 2.5). The transition map itself is
pure logic in leadpipe.stages."""

from __future__ import annotations

from .. import stages as stage_logic
from ..models import Stage, UpdateStageArgs, WriteMode
from ..store import schema
from . import ToolContext, approval_result, audit, find_lead, resolve_write_mode

__all__ = ["UpdateStageArgs", "update_stage"]


def update_stage(ctx: ToolContext, args: UpdateStageArgs) -> dict:
    row = find_lead(ctx, args.lead_id)
    from_stage = stage_logic.parse_stage(row["stage"])
    to_stage = stage_logic.parse_stage(args.stage)
    stage_logic.validate_transition(from_stage, to_stage)
    mode = resolve_write_mode(ctx.config, args.dry_run)

    preview = {
        "lead_id": args.lead_id,
        "stage_from": from_stage.value,
        "stage_to": to_stage.value,
    }
    if from_stage == to_stage:
        # Successful no-op (SPEC 2.5): nothing to write in any mode.
        return {"ok": True, **preview, "updated_at": row.get("updated_at", "")}
    if mode == WriteMode.DRY_RUN:
        audit(ctx, "update_stage", args.lead_id, preview, mode)
        return {"ok": True, "dry_run": True, "preview": preview}
    if mode == WriteMode.APPROVAL and not args.confirm:
        audit(ctx, "update_stage", args.lead_id, {"executed": False}, mode)
        return approval_result(preview)

    now = schema.utc_now_iso()
    ctx.store.update_lead(  # type: ignore[attr-defined]
        args.lead_id, {"stage": to_stage.value, "updated_at": now}
    )
    detail = dict(preview)
    if args.note:
        detail["note"] = args.note
    audit(ctx, "update_stage", args.lead_id, detail, mode)
    return {"ok": True, **preview, "updated_at": now}


# Re-exported for callers that only need the enum alongside the tool.
__all__ += ["Stage"]
