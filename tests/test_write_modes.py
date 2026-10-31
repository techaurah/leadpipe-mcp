"""Write modes (SPEC 4.1): dry-run writes nothing, approval queues,
and a per-call flag can never upgrade a call."""

from leadpipe import errors
from leadpipe.models import WriteMode
from leadpipe.tools import dispatch
from tests.conftest import make_ctx

SCORES = {
    "problem": 18,
    "fit": 18,
    "value": 12,
    "size": 8,
    "pay": 8,
    "access": 8,
    "urgency": 5,
    "activity": 3,
}
TUE = "2026-11-24"


def _audit_modes(ctx):
    return [row["mode"] for row in ctx.store.list_audit()]


def test_dry_run_capture_writes_no_lead_but_logs():
    ctx = make_ctx(seed=True, write_mode=WriteMode.DIRECT)
    before = len(ctx.store.list_leads())
    audit_before = len(ctx.store.list_audit())
    result = dispatch(
        ctx,
        "capture_lead",
        name="Dry",
        email="dry@example.com",
        source="website",
        dry_run=True,
    )
    assert result["ok"] is True
    assert result["dry_run"] is True
    assert result["preview"]["created"] is True
    assert len(ctx.store.list_leads()) == before
    audit = ctx.store.list_audit()
    assert len(audit) == audit_before + 1
    assert audit[-1]["mode"] == "dry_run"
    assert audit[-1]["action"] == "capture_lead"


def test_dry_run_score_and_stage_change_nothing():
    ctx = make_ctx(seed=True, write_mode=WriteMode.DIRECT)
    scored = dispatch(
        ctx, "score_lead", lead_id="LP-2026-00009", scores=SCORES, dry_run=True
    )
    assert scored["dry_run"] is True
    assert scored["preview"]["score_total"] == 80
    lead = dispatch(ctx, "get_lead", lead_id="LP-2026-00009")["lead"]
    assert lead["score_total"] is None

    staged = dispatch(
        ctx,
        "update_stage",
        lead_id="LP-2026-00009",
        stage="CONTACTED",
        dry_run=True,
    )
    assert staged["dry_run"] is True
    lead = dispatch(ctx, "get_lead", lead_id="LP-2026-00009")["lead"]
    assert lead["stage"] == "NEW"


def test_dry_run_booking_creates_no_event():
    ctx = make_ctx(seed=True, write_mode=WriteMode.DIRECT)
    result = dispatch(
        ctx,
        "book_appointment",
        lead_id="LP-2026-00002",
        start=f"{TUE}T11:00:00Z",
        end=f"{TUE}T11:30:00Z",
        dry_run=True,
    )
    assert result["dry_run"] is True
    lead = dispatch(ctx, "get_lead", lead_id="LP-2026-00002")["lead"]
    assert lead["appointment_status"] == ""


def test_approval_without_confirm_writes_nothing():
    ctx = make_ctx(seed=True, write_mode=WriteMode.APPROVAL)
    before = len(ctx.store.list_leads())
    result = dispatch(
        ctx, "capture_lead", name="Hold", email="hold@example.com", source="email"
    )
    assert result["ok"] is False
    assert result["error"]["code"] == errors.APPROVAL_REQUIRED
    assert result["preview"]["created"] is True
    assert len(ctx.store.list_leads()) == before


def test_approval_with_confirm_executes():
    ctx = make_ctx(seed=True, write_mode=WriteMode.APPROVAL)
    result = dispatch(
        ctx,
        "capture_lead",
        name="Go",
        email="go@example.com",
        source="email",
        confirm=True,
    )
    assert result["ok"] is True
    assert result["created"] is True
    assert "approval" in _audit_modes(ctx)


def test_approval_booking_flow():
    ctx = make_ctx(seed=True, write_mode=WriteMode.APPROVAL)
    preview = dispatch(
        ctx,
        "book_appointment",
        lead_id="LP-2026-00002",
        start=f"{TUE}T11:00:00Z",
        end=f"{TUE}T11:30:00Z",
    )
    assert preview["error"]["code"] == errors.APPROVAL_REQUIRED
    lead = dispatch(ctx, "get_lead", lead_id="LP-2026-00002")["lead"]
    assert lead["appointment_status"] == ""
    booked = dispatch(
        ctx,
        "book_appointment",
        lead_id="LP-2026-00002",
        start=f"{TUE}T11:00:00Z",
        end=f"{TUE}T11:30:00Z",
        confirm=True,
    )
    assert booked["created"] is True


def test_per_call_dry_run_overrides_direct_config():
    ctx = make_ctx(seed=True, write_mode=WriteMode.DIRECT)
    result = dispatch(
        ctx,
        "update_stage",
        lead_id="LP-2026-00003",
        stage="CONTACTED",
        dry_run=True,
    )
    assert result["dry_run"] is True


def test_confirm_cannot_upgrade_dry_run_config():
    ctx = make_ctx(seed=True, write_mode=WriteMode.DRY_RUN)
    before = len(ctx.store.list_leads())
    result = dispatch(
        ctx,
        "capture_lead",
        name="NoUpgrade",
        email="noup@example.com",
        source="website",
        confirm=True,
    )
    # Still a dry run: confirm is harmless in dry-run mode, never executes.
    assert result["dry_run"] is True
    assert len(ctx.store.list_leads()) == before


def test_config_level_dry_run_mode():
    ctx = make_ctx(seed=True, write_mode=WriteMode.DRY_RUN)
    result = dispatch(ctx, "score_lead", lead_id="LP-2026-00009", scores=SCORES)
    assert result["dry_run"] is True
    assert result["preview"]["band"] == "HOT"
