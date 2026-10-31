"""score_lead tool wrapper (SPEC 2.4). The pure model lives in
leadpipe.scoring; no LLM call is made anywhere in this server."""

from __future__ import annotations

from .. import scoring
from ..models import ScoreLeadArgs, WriteMode
from . import ToolContext, approval_result, audit, find_lead, resolve_write_mode

__all__ = ["ScoreLeadArgs", "score_lead"]


def score_lead(ctx: ToolContext, args: ScoreLeadArgs) -> dict:
    components, total, band = scoring.score(args.scores)
    row = find_lead(ctx, args.lead_id)
    mode = resolve_write_mode(ctx.config, args.dry_run)

    changes = {f"score_{field}": str(value) for field, value in components.items()}
    changes["score_total"] = str(total)
    changes["band"] = band.value

    preview = {
        "lead_id": args.lead_id,
        "score_total": total,
        "band": band.value,
        "components": components,
        "previous_total": row.get("score_total", "") or None,
    }
    if mode == WriteMode.DRY_RUN:
        audit(ctx, "score_lead", args.lead_id, {"total": total}, mode)
        return {"ok": True, "dry_run": True, "preview": preview}
    if mode == WriteMode.APPROVAL and not args.confirm:
        audit(ctx, "score_lead", args.lead_id, {"executed": False}, mode)
        return approval_result(preview)

    from ..store import schema

    changes["updated_at"] = schema.utc_now_iso()
    ctx.store.update_lead(args.lead_id, changes)  # type: ignore[attr-defined]
    audit(
        ctx,
        "score_lead",
        args.lead_id,
        {"previous_total": preview["previous_total"], "new_total": total},
        mode,
    )
    return {
        "ok": True,
        "lead_id": args.lead_id,
        "score_total": total,
        "band": band.value,
        "components": components,
    }
