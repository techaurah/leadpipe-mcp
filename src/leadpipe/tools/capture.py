"""capture_lead (SPEC 2.1): record a new lead, deduplicating before write."""

from __future__ import annotations

from .. import errors
from ..models import (
    CaptureLeadArgs,
    Source,
    Stage,
    WriteMode,
    normalise_email,
    normalise_phone,
)
from ..store import schema
from . import ToolContext, approval_result, audit, resolve_write_mode

__all__ = ["CaptureLeadArgs", "capture_lead"]


def _prepare(ctx: ToolContext, args: CaptureLeadArgs) -> tuple[dict, dict | None]:
    """Validate input and look for a duplicate.

    Returns (row_that_would_be_written, duplicate_match_or_None). The
    duplicate dict carries the existing row, matched_on, and the field
    fills a merge would apply.
    """
    name = args.name.strip()
    if not name:
        raise errors.validation("name must be non-empty", "name")
    if args.email is None and args.phone is None:
        raise errors.validation("At least one of email, phone is required", "email")
    email = normalise_email(args.email) if args.email else ""
    phone = normalise_phone(args.phone) if args.phone else ""
    try:
        source = Source(args.source)
    except ValueError:
        raise errors.validation(f"Unknown source: {args.source!r}", "source") from None

    leads = ctx.store.list_leads()  # type: ignore[attr-defined]
    duplicate = None
    if email:
        for row in leads:
            if row.get("email", "") == email:
                duplicate = (row, "email")
                break
    if duplicate is None and phone:
        for row in leads:
            if row.get("phone", "") == phone:
                duplicate = (row, "phone")
                break

    now = schema.utc_now_iso()
    if duplicate is not None:
        row, matched_on = duplicate
        fills: dict[str, str] = {}
        candidates = {
            "email": email,
            "phone": phone,
            "company": (args.company or "").strip(),
            "service_interest": (args.service_interest or "").strip(),
            "location": (args.location or "").strip(),
            "problem_notes": (args.problem_notes or "").strip(),
        }
        for field_name, value in candidates.items():
            if value and not row.get(field_name, ""):
                fills[field_name] = value
        return {}, {
            "row": row,
            "matched_on": matched_on,
            "fills": fills,
            "now": now,
        }

    # Preview only: this peek names the ID a dry run or an approval
    # prompt would use. The write path takes the real ID from
    # store.allocate_lead_seq(), which advances the counter atomically;
    # nothing here may write the counter back.
    seq_raw = ctx.store.get_meta("next_lead_seq")  # type: ignore[attr-defined]
    if seq_raw is None:
        raise errors.LeadPipeError(
            errors.SCHEMA_MISMATCH, "Meta.next_lead_seq is missing. Run bootstrap."
        )
    seq = int(seq_raw)
    year = now[:4]
    lead_id = f"LP-{year}-{seq:05d}"
    row = {h: "" for h in schema.LEADS_HEADERS}
    row.update(
        {
            "lead_id": lead_id,
            "created_at": now,
            "updated_at": now,
            "name": name,
            "email": email,
            "phone": phone,
            "company": (args.company or "").strip(),
            "source": source.value,
            "service_interest": (args.service_interest or "").strip(),
            "location": (args.location or "").strip(),
            "problem_notes": (args.problem_notes or "").strip(),
            "stage": Stage.NEW.value,
            "owner": "unassigned",
        }
    )
    return row, None


def capture_lead(ctx: ToolContext, args: CaptureLeadArgs) -> dict:
    mode = resolve_write_mode(ctx.config, args.dry_run)
    row, duplicate = _prepare(ctx, args)

    if duplicate is not None:
        existing = duplicate["row"]
        preview = {
            "lead_id": existing["lead_id"],
            "created": False,
            "deduped": True,
            "matched_on": duplicate["matched_on"],
            "stage": existing["stage"],
            "field_fills": duplicate["fills"],
        }
        if mode == WriteMode.DRY_RUN:
            audit(
                ctx,
                "capture_lead",
                existing["lead_id"],
                {"deduped": True, "matched_on": duplicate["matched_on"]},
                mode,
            )
            return {"ok": True, "dry_run": True, "preview": preview}
        if mode == WriteMode.APPROVAL and not args.confirm:
            audit(
                ctx,
                "capture_lead",
                existing["lead_id"],
                {"deduped": True, "executed": False},
                mode,
            )
            return approval_result(preview)
        if duplicate["fills"]:
            changes = dict(duplicate["fills"])
            changes["updated_at"] = duplicate["now"]
            ctx.store.update_lead(existing["lead_id"], changes)  # type: ignore[attr-defined]
        audit(
            ctx,
            "capture_lead",
            existing["lead_id"],
            {"deduped": True, "matched_on": duplicate["matched_on"]},
            mode,
        )
        return {"ok": True, **preview}

    preview = {
        "lead_id": row["lead_id"],
        "created": True,
        "deduped": False,
        "stage": Stage.NEW.value,
        "score_total": None,
        "band": None,
        "row": row,
    }
    if mode == WriteMode.DRY_RUN:
        audit(ctx, "capture_lead", row["lead_id"], {"created": True}, mode)
        return {"ok": True, "dry_run": True, "preview": preview}
    if mode == WriteMode.APPROVAL and not args.confirm:
        audit(ctx, "capture_lead", row["lead_id"], {"executed": False}, mode)
        return approval_result(preview)

    # Allocate the sequence atomically in the store, then stamp the
    # allocated ID on the row. Doing the read-modify-write here raced
    # under concurrent captures and minted duplicate IDs.
    seq = ctx.store.allocate_lead_seq()  # type: ignore[attr-defined]
    row["lead_id"] = f"LP-{row['created_at'][:4]}-{seq:05d}"
    preview["lead_id"] = row["lead_id"]
    ctx.store.append_lead(row)  # type: ignore[attr-defined]
    audit(ctx, "capture_lead", row["lead_id"], {"created": True}, mode)
    result = {k: v for k, v in preview.items() if k != "row"}
    return {"ok": True, **result}
