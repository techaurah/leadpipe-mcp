"""daily_pipeline_summary against the fixed demo fixture (SPEC 2.8).

Fixture date: Monday 2026-11-23. Seeded leads were created 0-20 days
before it; Diego's next action was due 2026-11-22 (overdue), Omar's and
Tom's are due today (not overdue). Amara's appointment is Tue 2026-11-24.
"""

from leadpipe import errors
from leadpipe.tools import dispatch


def test_summary_counts(demo_ctx):
    result = dispatch(demo_ctx, "daily_pipeline_summary", date="2026-11-23")
    assert result["ok"] is True
    assert result["date"] == "2026-11-23"
    assert result["total_leads"] == 12
    assert result["new_today"] == 1  # Grace Liu, created on the seed day
    assert result["by_stage"] == {
        "NEW": 3,
        "CONTACTED": 1,
        "QUALIFIED": 1,
        "NURTURE": 1,
        "DISCOVERY": 1,
        "BOOKED": 1,
        "PROPOSAL": 1,
        "NEGOTIATION": 1,
        "WON": 1,
        "LOST": 1,
    }
    assert result["by_band"] == {
        "HOT": 3,
        "WARM": 5,
        "NURTURE": 2,
        "LOW": 1,
        "UNSCORED": 1,
    }


def test_summary_hot_unbooked(demo_ctx):
    result = dispatch(demo_ctx, "daily_pipeline_summary", date="2026-11-23")
    ids = [lead["lead_id"] for lead in result["hot_unbooked"]]
    assert ids == ["LP-2026-00002", "LP-2026-00003"]  # 92 then 81; Amara booked


def test_summary_overdue_next_actions(demo_ctx):
    result = dispatch(demo_ctx, "daily_pipeline_summary", date="2026-11-23")
    overdue = result["overdue_next_actions"]
    assert [o["lead_id"] for o in overdue] == ["LP-2026-00002"]
    assert overdue[0]["next_action_date"] == "2026-11-22"


def test_summary_appointments_today(demo_ctx):
    monday = dispatch(demo_ctx, "daily_pipeline_summary", date="2026-11-23")
    assert monday["appointments_today"] == []
    tuesday = dispatch(demo_ctx, "daily_pipeline_summary", date="2026-11-24")
    assert len(tuesday["appointments_today"]) == 1
    appt = tuesday["appointments_today"][0]
    assert appt["lead_id"] == "LP-2026-00001"
    assert appt["name"] == "Amara Chen"
    assert appt["start"] == "2026-11-24T10:00:00Z"
    assert appt["end"] == "2026-11-24T10:30:00Z"


def test_summary_bad_date(demo_ctx):
    result = dispatch(demo_ctx, "daily_pipeline_summary", date="23-11-2026")
    assert result["ok"] is False
    assert result["error"]["code"] == errors.VALIDATION_ERROR


def test_summary_reflects_new_capture(demo_ctx):
    dispatch(
        demo_ctx,
        "capture_lead",
        name="Today Lead",
        email="today@example.com",
        source="website",
    )
    result = dispatch(demo_ctx, "daily_pipeline_summary", date="2026-11-23")
    # The capture is stamped with the real clock, not the fixture date,
    # so total grows but new_today for the fixture date does not.
    assert result["total_leads"] == 13
