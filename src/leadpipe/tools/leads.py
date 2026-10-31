"""get_lead, list_hot_leads and daily_pipeline_summary (SPEC 2.2, 2.3, 2.8).

All three are read tools: they never write to the store or calendar.
Totals and bands are recomputed from stored components on every read.
"""

from __future__ import annotations

from datetime import UTC, datetime, time, timedelta

from .. import errors
from ..models import (
    DailySummaryArgs,
    GetLeadArgs,
    ListHotLeadsArgs,
    Stage,
    normalise_email,
    normalise_phone,
)
from ..scoring import COMPONENT_FIELDS
from . import ToolContext, find_lead, recompute

__all__ = [
    "DailySummaryArgs",
    "GetLeadArgs",
    "ListHotLeadsArgs",
    "daily_pipeline_summary",
    "get_lead",
    "list_hot_leads",
]


def _typed_lead(row: dict) -> dict:
    """Full lead object: every column, with score fields typed and the
    total/band recomputed from components (SPEC 2.2)."""
    lead: dict = {}
    for key, value in row.items():
        if key.startswith("score_") and key != "score_total":
            lead[key] = int(value) if value not in ("", None) else None
        else:
            lead[key] = value
    total, band = recompute(row)
    lead["score_total"] = total
    lead["band"] = band
    lead["score_components"] = (
        {f: lead[f"score_{f}"] for f in COMPONENT_FIELDS} if total is not None else None
    )
    return lead


def get_lead(ctx: ToolContext, args: GetLeadArgs) -> dict:
    provided = [
        name
        for name, value in (
            ("lead_id", args.lead_id),
            ("email", args.email),
            ("phone", args.phone),
        )
        if value
    ]
    if len(provided) != 1:
        raise errors.validation(
            "Provide exactly one of lead_id, email, phone",
            provided[0] if provided else None,
        )
    if args.lead_id:
        row = find_lead(ctx, args.lead_id)
        return {"ok": True, "lead": _typed_lead(row)}
    leads = ctx.store.list_leads()  # type: ignore[attr-defined]
    if args.email:
        email = normalise_email(args.email)
        for row in leads:
            if row.get("email", "") == email:
                return {"ok": True, "lead": _typed_lead(row)}
        raise errors.not_found(f"email {email}")
    phone = normalise_phone(args.phone or "")
    for row in leads:
        if row.get("phone", "") == phone:
            return {"ok": True, "lead": _typed_lead(row)}
    raise errors.not_found(f"phone {phone}")


def list_hot_leads(ctx: ToolContext, args: ListHotLeadsArgs) -> dict:
    if args.limit < 1 or args.limit > 100:
        raise errors.validation("limit must be between 1 and 100", "limit")
    hot: list[tuple[int, str, dict]] = []
    for row in ctx.store.list_leads():  # type: ignore[attr-defined]
        total, band = recompute(row)
        if band != "HOT":
            continue
        if not args.include_booked and row.get("appointment_status") == "confirmed":
            continue
        hot.append((total or 0, row.get("created_at", ""), row))
    # Highest score first, oldest first within a score (SPEC 2.3).
    hot.sort(key=lambda item: (-item[0], item[1]))
    leads = [
        {
            "lead_id": row["lead_id"],
            "name": row.get("name", ""),
            "company": row.get("company", ""),
            "source": row.get("source", ""),
            "score_total": total,
            "band": band,
            "stage": row.get("stage", ""),
            "next_action": row.get("next_action", ""),
            "next_action_date": row.get("next_action_date", ""),
            "appointment_status": row.get("appointment_status", ""),
        }
        for total, _created, row in hot[: args.limit]
        for band in [recompute(row)[1]]
    ]
    return {"ok": True, "count": len(leads), "leads": leads}


def _parse_dt(raw: str) -> datetime | None:
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None


def daily_pipeline_summary(ctx: ToolContext, args: DailySummaryArgs) -> dict:
    tz = ctx.config.tz
    if args.date:
        try:
            target = datetime.strptime(args.date, "%Y-%m-%d").date()
        except ValueError:
            raise errors.validation("date must be YYYY-MM-DD", "date") from None
    else:
        target = datetime.now(tz).date()

    leads = ctx.store.list_leads()  # type: ignore[attr-defined]
    by_stage = {stage.value: 0 for stage in Stage}
    by_band = {"HOT": 0, "WARM": 0, "NURTURE": 0, "LOW": 0, "UNSCORED": 0}
    new_today = 0
    hot_unbooked: list[dict] = []
    overdue: list[dict] = []

    for row in leads:
        by_stage[row.get("stage", "NEW")] = by_stage.get(row.get("stage", "NEW"), 0) + 1
        total, band = recompute(row)
        by_band[band if band else "UNSCORED"] += 1
        created = _parse_dt(row.get("created_at", ""))
        if created is not None and created.astimezone(tz).date() == target:
            new_today += 1
        if band == "HOT" and row.get("appointment_status") != "confirmed":
            hot_unbooked.append(
                {
                    "lead_id": row["lead_id"],
                    "name": row.get("name", ""),
                    "score_total": total,
                    "stage": row.get("stage", ""),
                }
            )
        due_raw = row.get("next_action_date", "")
        stage = row.get("stage", "")
        if (
            due_raw
            and row.get("next_action", "")
            and stage not in (Stage.WON.value, Stage.LOST.value)
        ):
            try:
                due = datetime.strptime(due_raw, "%Y-%m-%d").date()
            except ValueError:
                due = None
            if due is not None and due < target:
                overdue.append(
                    {
                        "lead_id": row["lead_id"],
                        "name": row.get("name", ""),
                        "stage": stage,
                        "next_action": row.get("next_action", ""),
                        "next_action_date": due_raw,
                    }
                )

    hot_unbooked.sort(key=lambda item: -(item["score_total"] or 0))
    overdue.sort(key=lambda item: item["next_action_date"])

    day_start = datetime.combine(target, time.min, tzinfo=tz)
    day_end = day_start + timedelta(days=1)
    appointments = []
    for event in ctx.calendar.list_events(day_start, day_end):  # type: ignore[attr-defined]
        lead_id = event.get("lead_id", "")
        if not lead_id:
            continue
        name = ""
        for row in leads:
            if row["lead_id"] == lead_id:
                name = row.get("name", "")
                break
        appointments.append(
            {
                "lead_id": lead_id,
                "name": name,
                "start": event["start"]
                .astimezone(UTC)
                .isoformat()
                .replace("+00:00", "Z"),
                "end": event["end"].astimezone(UTC).isoformat().replace("+00:00", "Z"),
            }
        )
    appointments.sort(key=lambda item: item["start"])

    return {
        "ok": True,
        "date": target.isoformat(),
        "total_leads": len(leads),
        "new_today": new_today,
        "by_stage": by_stage,
        "by_band": by_band,
        "hot_unbooked": hot_unbooked,
        "appointments_today": appointments,
        "overdue_next_actions": overdue,
    }
