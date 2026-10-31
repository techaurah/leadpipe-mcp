"""Stage transition map: every allowed pair passes, illegal set fails."""

import pytest

from leadpipe import errors
from leadpipe.models import Stage
from leadpipe.stages import TRANSITIONS, can_transition, validate_transition
from leadpipe.tools import dispatch


def test_every_allowed_pair_passes():
    for from_stage, targets in TRANSITIONS.items():
        for to_stage in targets:
            assert can_transition(from_stage, to_stage)
            validate_transition(from_stage, to_stage)


@pytest.mark.parametrize(
    "from_stage,to_stage",
    [
        (Stage.WON, Stage.CONTACTED),
        (Stage.WON, Stage.NURTURE),
        (Stage.WON, Stage.LOST),
        (Stage.LOST, Stage.QUALIFIED),
        (Stage.LOST, Stage.CONTACTED),
        (Stage.LOST, Stage.WON),
        (Stage.NEW, Stage.WON),
        (Stage.NEW, Stage.BOOKED),
        (Stage.NEW, Stage.PROPOSAL),
        (Stage.BOOKED, Stage.WON),
        (Stage.NEGOTIATION, Stage.BOOKED),
        (Stage.CONTACTED, Stage.WON),
    ],
)
def test_illegal_pairs_fail(from_stage, to_stage):
    assert not can_transition(from_stage, to_stage)
    with pytest.raises(errors.LeadPipeError) as excinfo:
        validate_transition(from_stage, to_stage)
    assert excinfo.value.code == errors.STAGE_TRANSITION_INVALID


def test_same_stage_is_noop_success():
    for stage in Stage:
        assert can_transition(stage, stage)


def _capture(ctx, email="stage@example.com"):
    return dispatch(
        ctx, "capture_lead", name="Stage Tester", email=email, source="website"
    )["lead_id"]


def test_update_stage_tool_flow(demo_ctx):
    lead_id = _capture(demo_ctx)
    result = dispatch(demo_ctx, "update_stage", lead_id=lead_id, stage="CONTACTED")
    assert result["ok"] is True
    assert result["stage_from"] == "NEW"
    assert result["stage_to"] == "CONTACTED"
    lead = dispatch(demo_ctx, "get_lead", lead_id=lead_id)["lead"]
    assert lead["stage"] == "CONTACTED"


def test_update_stage_illegal_via_tool(demo_ctx):
    lead_id = _capture(demo_ctx, "illegal@example.com")
    result = dispatch(demo_ctx, "update_stage", lead_id=lead_id, stage="WON")
    assert result["ok"] is False
    assert result["error"]["code"] == errors.STAGE_TRANSITION_INVALID
    lead = dispatch(demo_ctx, "get_lead", lead_id=lead_id)["lead"]
    assert lead["stage"] == "NEW"


def test_update_stage_same_stage_noop(demo_ctx):
    lead_id = _capture(demo_ctx, "noop@example.com")
    result = dispatch(demo_ctx, "update_stage", lead_id=lead_id, stage="NEW")
    assert result["ok"] is True
    assert result["stage_from"] == result["stage_to"] == "NEW"


def test_lost_reactivation_only_to_nurture(demo_ctx):
    lead_id = _capture(demo_ctx, "lost@example.com")
    dispatch(demo_ctx, "update_stage", lead_id=lead_id, stage="LOST")
    ok = dispatch(demo_ctx, "update_stage", lead_id=lead_id, stage="NURTURE")
    assert ok["ok"] is True
    dispatch(demo_ctx, "update_stage", lead_id=lead_id, stage="LOST")
    bad = dispatch(demo_ctx, "update_stage", lead_id=lead_id, stage="QUALIFIED")
    assert bad["ok"] is False
    assert bad["error"]["code"] == errors.STAGE_TRANSITION_INVALID


def test_update_stage_unknown_stage_and_lead(demo_ctx):
    lead_id = _capture(demo_ctx, "unk@example.com")
    bad = dispatch(demo_ctx, "update_stage", lead_id=lead_id, stage="SIDWAYS")
    assert bad["error"]["code"] == errors.VALIDATION_ERROR
    missing = dispatch(
        demo_ctx, "update_stage", lead_id="LP-2026-99999", stage="CONTACTED"
    )
    assert missing["error"]["code"] == errors.LEAD_NOT_FOUND
