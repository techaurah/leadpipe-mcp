"""check_availability and book_appointment (SPEC 2.6, 2.7).

Booking never trusts an earlier availability answer: free/busy is
re-checked at call time, and the idempotency key makes a repeat booking
return the existing event instead of creating a duplicate. No event is
ever created with attendees: v0.1 sends nothing to anyone (SPEC 4.2).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from .. import errors
from ..models import (
    BookAppointmentArgs,
    CheckAvailabilityArgs,
    WriteMode,
    idempotency_key,
)
from ..store import schema
from . import ToolContext, approval_result, audit, find_lead, resolve_write_mode

__all__ = [
    "BookAppointmentArgs",
    "CheckAvailabilityArgs",
    "book_appointment",
    "check_availability",
]

ALLOWED_SLOT_MINUTES = (15, 30, 45, 60)
MAX_RANGE_DAYS = 14


def _to_iso(dt: datetime) -> str:
    return dt.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _parse_range(start_raw: str, end_raw: str) -> tuple[datetime, datetime]:
    def parse(raw: str, field: str) -> datetime:
        try:
            value = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError:
            raise errors.validation(
                f"{field} must be an ISO 8601 datetime", field
            ) from None
        if value.tzinfo is None:
            raise errors.validation(f"{field} must include a timezone", field)
        return value

    start, end = parse(start_raw, "start"), parse(end_raw, "end")
    if end <= start:
        raise errors.validation("end must be after start", "end")
    return start, end


def check_availability(ctx: ToolContext, args: CheckAvailabilityArgs) -> dict:
    if args.slot_minutes not in ALLOWED_SLOT_MINUTES:
        raise errors.validation(
            f"slot_minutes must be one of {ALLOWED_SLOT_MINUTES}", "slot_minutes"
        )
    start, end = _parse_range(args.start, args.end)
    if (end - start) > timedelta(days=MAX_RANGE_DAYS):
        raise errors.validation("Range must be at most 14 days", "end")

    tz = ctx.config.tz
    open_time, close_time = ctx.config.business_window
    business_days = set(ctx.config.business_days)
    busy = ctx.calendar.freebusy(start, end)  # type: ignore[attr-defined]

    slots: list[dict] = []
    day = start.astimezone(tz).date()
    last_day = end.astimezone(tz).date()
    min_len = timedelta(minutes=args.slot_minutes)
    while day <= last_day:
        if day.weekday() in business_days:
            window_start = datetime.combine(day, open_time, tzinfo=tz)
            window_end = datetime.combine(day, close_time, tzinfo=tz)
            lo, hi = max(window_start, start), min(window_end, end)
            if lo < hi:
                cursor = lo
                for busy_start, busy_end in busy:
                    if busy_end <= cursor or busy_start >= hi:
                        continue
                    if busy_start > cursor and busy_start - cursor >= min_len:
                        slots.append(
                            {"start": _to_iso(cursor), "end": _to_iso(busy_start)}
                        )
                    cursor = max(cursor, busy_end)
                if hi - cursor >= min_len:
                    slots.append({"start": _to_iso(cursor), "end": _to_iso(hi)})
        day += timedelta(days=1)

    return {
        "ok": True,
        "timezone": ctx.config.timezone_name,
        "slots": slots,
        "busy": [
            {"start": _to_iso(s), "end": _to_iso(e), "title": None} for s, e in busy
        ],
    }


def book_appointment(ctx: ToolContext, args: BookAppointmentArgs) -> dict:
    row = find_lead(ctx, args.lead_id)
    start, end = _parse_range(args.start, args.end)
    mode = resolve_write_mode(ctx.config, args.dry_run)
    key = idempotency_key(args.lead_id, _to_iso(start), _to_iso(end))

    # Idempotency first: a repeat call returns the existing event in any
    # mode, because returning it writes nothing (SPEC 2.7).
    existing = ctx.calendar.find_event_by_key(key)  # type: ignore[attr-defined]
    if existing is not None:
        return {
            "ok": True,
            "lead_id": args.lead_id,
            "appointment_id": existing["id"],
            "start": _to_iso(existing["start"]),
            "end": _to_iso(existing["end"]),
            "created": False,
            "calendar_html_link": existing.get("html_link", ""),
        }

    # Re-check availability at call time; earlier answers are never trusted.
    busy = ctx.calendar.freebusy(start, end)  # type: ignore[attr-defined]
    if busy:
        raise errors.LeadPipeError(
            errors.SLOT_UNAVAILABLE,
            "The requested slot is no longer free on the calendar.",
            "start",
        )

    title = args.title or (
        f"{row.get('service_interest') or 'Consultation'} — {row.get('name', '')}"
    )
    description_lines = [f"LeadPipe lead: {args.lead_id}"]
    if args.notes:
        description_lines.append(args.notes)
    description = "\n".join(description_lines)

    preview = {
        "lead_id": args.lead_id,
        "start": _to_iso(start),
        "end": _to_iso(end),
        "title": title,
        "idempotency_key": key,
    }
    if mode == WriteMode.DRY_RUN:
        audit(ctx, "book_appointment", args.lead_id, preview, mode)
        return {"ok": True, "dry_run": True, "preview": preview}
    if mode == WriteMode.APPROVAL and not args.confirm:
        audit(ctx, "book_appointment", args.lead_id, {"executed": False}, mode)
        return approval_result(preview)

    event = ctx.calendar.create_event(  # type: ignore[attr-defined]
        start=start,
        end=end,
        title=title,
        description=description,
        lead_id=args.lead_id,
        idempotency_key=key,
    )
    ctx.store.update_lead(  # type: ignore[attr-defined]
        args.lead_id,
        {
            "appointment_id": event["id"],
            "appointment_start": _to_iso(start),
            "appointment_status": "confirmed",
            "updated_at": schema.utc_now_iso(),
        },
    )
    audit(
        ctx,
        "book_appointment",
        args.lead_id,
        {"appointment_id": event["id"], "idempotency_key": key},
        mode,
    )
    return {
        "ok": True,
        "lead_id": args.lead_id,
        "appointment_id": event["id"],
        "start": _to_iso(start),
        "end": _to_iso(end),
        "created": True,
        "calendar_html_link": event.get("html_link", ""),
    }
