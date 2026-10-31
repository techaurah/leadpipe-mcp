"""Availability and booking (SPEC 2.6, 2.7).

Seed calendar (business days Tue 2026-11-24, Wed 25, Thu 26):
- Tue: busy 09:00-10:00, Amara's appointment 10:00-10:30, busy 13:00-14:30
- Wed: busy 11:00-12:00, busy 15:00-16:00
- Thu: busy 09:30-10:30
Business hours 09:00-17:00 UTC, Mon-Fri.
"""

from datetime import UTC, datetime

from leadpipe import errors
from leadpipe.tools import dispatch


def _day_events(ctx, day_start: datetime, day_end: datetime):
    return ctx.calendar.list_events(day_start, day_end)


DAY_START = datetime(2026, 11, 24, tzinfo=UTC)
DAY_END = datetime(2026, 11, 25, tzinfo=UTC)

TUE = "2026-11-24"


def avail(ctx, day=TUE, slot=30):
    return dispatch(
        ctx,
        "check_availability",
        start=f"{day}T00:00:00Z",
        end=f"{day}T23:59:59Z",
        slot_minutes=slot,
    )


def test_availability_intersects_business_hours_and_busy(demo_ctx):
    result = avail(demo_ctx)
    assert result["ok"] is True
    starts = [s["start"] for s in result["slots"]]
    assert starts[0] == f"{TUE}T10:30:00Z"  # after standup + Amara's booking
    assert f"{TUE}T14:30:00Z" in starts  # after the workshop block
    # Nothing outside 09:00-17:00, and busy titles are never exposed.
    for slot in result["slots"]:
        assert slot["start"][11:16] >= "09:00"
        assert slot["end"][11:16] <= "17:00"
    assert all(b["title"] is None for b in result["busy"])
    assert len(result["busy"]) == 3  # two seeded blocks + Amara's event


def test_availability_skips_weekends(demo_ctx):
    result = avail(demo_ctx, day="2026-11-28")  # Saturday
    assert result["slots"] == []


def test_availability_slot_size_filter(demo_ctx):
    # The 10:30-13:00 gap fits 30 and 60; a narrow gap only fits small slots.
    result = avail(demo_ctx, slot=60)
    starts = [s["start"] for s in result["slots"]]
    assert f"{TUE}T10:30:00Z" in starts
    assert f"{TUE}T14:30:00Z" in starts


def test_availability_validation(demo_ctx):
    bad_slot = dispatch(
        demo_ctx,
        "check_availability",
        start=f"{TUE}T00:00:00Z",
        end=f"{TUE}T23:59:59Z",
        slot_minutes=20,
    )
    assert bad_slot["error"]["code"] == errors.VALIDATION_ERROR
    reversed_range = dispatch(
        demo_ctx,
        "check_availability",
        start=f"{TUE}T12:00:00Z",
        end=f"{TUE}T11:00:00Z",
    )
    assert reversed_range["error"]["code"] == errors.VALIDATION_ERROR
    too_long = dispatch(
        demo_ctx,
        "check_availability",
        start="2026-11-24T00:00:00Z",
        end="2026-12-24T00:00:00Z",
    )
    assert too_long["error"]["code"] == errors.VALIDATION_ERROR


def _book(ctx, lead_id, start, end, **kwargs):
    return dispatch(
        ctx, "book_appointment", lead_id=lead_id, start=start, end=end, **kwargs
    )


def test_book_creates_event_and_updates_lead(demo_ctx):
    result = _book(demo_ctx, "LP-2026-00002", f"{TUE}T11:00:00Z", f"{TUE}T11:30:00Z")
    assert result["ok"] is True
    assert result["created"] is True
    lead = dispatch(demo_ctx, "get_lead", lead_id="LP-2026-00002")["lead"]
    assert lead["appointment_status"] == "confirmed"
    assert lead["appointment_id"] == result["appointment_id"]
    assert lead["appointment_start"] == f"{TUE}T11:00:00Z"


def test_book_rechecks_availability_at_call_time(demo_ctx):
    # Amara's seeded appointment occupies 10:00-10:30 on Tuesday.
    result = _book(demo_ctx, "LP-2026-00003", f"{TUE}T10:15:00Z", f"{TUE}T10:45:00Z")
    assert result["ok"] is False
    assert result["error"]["code"] == errors.SLOT_UNAVAILABLE


def test_book_after_freebusy_changes(demo_ctx):
    # Book the slot for one lead; a second lead then finds it gone even
    # though an earlier availability check showed it free.
    first = _book(demo_ctx, "LP-2026-00002", f"{TUE}T15:00:00Z", f"{TUE}T15:30:00Z")
    assert first["created"] is True
    second = _book(demo_ctx, "LP-2026-00003", f"{TUE}T15:00:00Z", f"{TUE}T15:30:00Z")
    assert second["error"]["code"] == errors.SLOT_UNAVAILABLE


def test_booking_idempotency(demo_ctx):
    args = ("LP-2026-00002", f"{TUE}T16:00:00Z", f"{TUE}T16:30:00Z")
    first = _book(demo_ctx, *args)
    second = _book(demo_ctx, *args)
    assert first["created"] is True
    assert second["created"] is False
    assert second["appointment_id"] == first["appointment_id"]
    events = _day_events(demo_ctx, DAY_START, DAY_END)
    mine = [e for e in events if e["lead_id"] == "LP-2026-00002"]
    assert len(mine) == 1


def test_book_unknown_lead(demo_ctx):
    result = _book(demo_ctx, "LP-2026-99999", f"{TUE}T11:00:00Z", f"{TUE}T11:30:00Z")
    assert result["error"]["code"] == errors.LEAD_NOT_FOUND


def test_book_default_title_uses_service_and_name(demo_ctx):
    _book(demo_ctx, "LP-2026-00003", f"{TUE}T11:00:00Z", f"{TUE}T11:30:00Z")
    events = [
        e
        for e in _day_events(demo_ctx, DAY_START, DAY_END)
        if e["lead_id"] == "LP-2026-00003"
    ]
    assert events[0]["title"] == "Booking automation — Priya Nair"
    # v0.1 sends nothing: the fake event model has no attendees at all.
    assert "attendees" not in events[0]
