"""Integration test: the full SPEC Section 5 walkthrough in demo mode.

This is the release gate for v0.1.0 (SPEC Section 7): capture, dedup,
score to HOT, hot list, availability, approval-mode booking (preview
then confirm), idempotent re-book, and the daily summary.
"""

from leadpipe import errors
from leadpipe.models import WriteMode
from leadpipe.tools import dispatch
from tests.conftest import make_ctx

HOT_SCORES = {
    "problem": 18,
    "fit": 19,
    "value": 13,
    "size": 8,
    "pay": 9,
    "access": 9,
    "urgency": 6,
    "activity": 3,
}  # total 85


def test_full_demo_walkthrough():
    ctx = make_ctx(seed=True, write_mode=WriteMode.APPROVAL)

    created = dispatch(
        ctx,
        "capture_lead",
        name="Walkthrough Wendy",
        email="wendy@wendysalon.example",
        phone="+1 415-555-0199",
        source="website",
        service_interest="Booking automation",
        confirm=True,
    )
    assert created["ok"] is True
    assert created["created"] is True
    lead_id = created["lead_id"]
    assert lead_id.endswith("00013")  # after the 12 seeded leads

    dupe = dispatch(
        ctx,
        "capture_lead",
        name="Walkthrough Wendy",
        email="WENDY@wendysalon.example",
        phone="+14155550199",
        source="instagram",
        confirm=True,
    )
    assert dupe["deduped"] is True
    assert dupe["lead_id"] == lead_id

    scored = dispatch(
        ctx, "score_lead", lead_id=lead_id, scores=HOT_SCORES, confirm=True
    )
    assert scored["score_total"] == 85
    assert scored["band"] == "HOT"

    hot = dispatch(ctx, "list_hot_leads", limit=10)
    assert lead_id in [lead["lead_id"] for lead in hot["leads"]]

    avail = dispatch(
        ctx,
        "check_availability",
        start="2026-11-24T00:00:00Z",
        end="2026-11-24T23:59:59Z",
        slot_minutes=30,
    )
    assert avail["ok"] is True
    slot = next(s for s in avail["slots"] if s["start"] >= "2026-11-24T10:30")
    start = slot["start"]
    # Book the first 30 minutes of the chosen free slot.
    from datetime import datetime, timedelta

    start_dt = datetime.fromisoformat(start.replace("Z", "+00:00"))
    end = (start_dt + timedelta(minutes=30)).isoformat().replace("+00:00", "Z")

    preview = dispatch(ctx, "book_appointment", lead_id=lead_id, start=start, end=end)
    assert preview["ok"] is False
    assert preview["error"]["code"] == errors.APPROVAL_REQUIRED
    assert preview["preview"]["lead_id"] == lead_id

    booked = dispatch(
        ctx,
        "book_appointment",
        lead_id=lead_id,
        start=start,
        end=end,
        confirm=True,
    )
    assert booked["created"] is True

    again = dispatch(
        ctx,
        "book_appointment",
        lead_id=lead_id,
        start=start,
        end=end,
        confirm=True,
    )
    assert again["created"] is False
    assert again["appointment_id"] == booked["appointment_id"]

    lead = dispatch(ctx, "get_lead", lead_id=lead_id)["lead"]
    assert lead["appointment_status"] == "confirmed"
    assert lead["band"] == "HOT"

    summary = dispatch(ctx, "daily_pipeline_summary", date="2026-11-23")
    assert summary["total_leads"] == 13
    assert summary["by_band"]["HOT"] == 4


def test_demo_seed_shape(demo_client):
    leads = demo_client.list_leads()
    assert len(leads) == 12
    stages = {row["stage"] for row in leads}
    assert stages == {
        "NEW",
        "CONTACTED",
        "QUALIFIED",
        "NURTURE",
        "DISCOVERY",
        "BOOKED",
        "PROPOSAL",
        "NEGOTIATION",
        "WON",
        "LOST",
    }
    bands = [row["band"] for row in leads if row["band"]]
    assert bands.count("HOT") == 3
    assert any(row["band"] == "" for row in leads)  # one unscored lead
    audit_actions = [row["action"] for row in demo_client.list_audit()]
    assert "capture_lead" in audit_actions
    # The deliberate duplicate pair: a deduped capture in the audit log.
    assert any("deduped" in row["detail"] for row in demo_client.list_audit())
