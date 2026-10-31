"""Scoring model: boundaries, ranges, server-side totals (SPEC 2.4, 7)."""

import pytest

from leadpipe import errors, scoring
from leadpipe.models import Band
from leadpipe.tools import dispatch

FULL = {
    "problem": 20,
    "fit": 20,
    "value": 15,
    "size": 10,
    "pay": 10,
    "access": 10,
    "urgency": 10,
    "activity": 5,
}


def components_for_total(total: int) -> dict:
    """Build a valid component set summing exactly to ``total``."""
    remaining = total
    out = {}
    for field, (_lo, hi) in scoring.COMPONENT_RANGES.items():
        take = min(hi, remaining)
        out[field] = take
        remaining -= take
    assert remaining == 0
    return out


@pytest.mark.parametrize(
    "total,band",
    [
        (49, Band.LOW),
        (50, Band.NURTURE),
        (64, Band.NURTURE),
        (65, Band.WARM),
        (79, Band.WARM),
        (80, Band.HOT),
        (100, Band.HOT),
        (0, Band.LOW),
    ],
)
def test_band_boundaries(total, band):
    assert scoring.band_for(total) is band
    components, computed, computed_band = scoring.score(components_for_total(total))
    assert computed == total
    assert computed_band is band


def test_each_component_min_and_max():
    zeros = {f: 0 for f in scoring.COMPONENT_RANGES}
    assert scoring.score(zeros)[1] == 0
    assert scoring.score(FULL)[1] == 100


@pytest.mark.parametrize(
    "bad",
    [
        {"problem": 21},  # above max
        {"activity": 6},  # above max
        {"fit": -1},  # below min
        {"pay": 5.5},  # non-integer
        {"pay": "5"},  # string
        {"pay": True},  # bool is not an integer score
    ],
)
def test_component_validation_rejects(bad):
    scores = dict(FULL)
    scores.update(bad)
    with pytest.raises(errors.LeadPipeError) as excinfo:
        scoring.validate_components(scores)
    assert excinfo.value.code == errors.VALIDATION_ERROR


def test_missing_component_rejected():
    scores = dict(FULL)
    del scores["urgency"]
    with pytest.raises(errors.LeadPipeError) as excinfo:
        scoring.validate_components(scores)
    assert excinfo.value.code == errors.VALIDATION_ERROR


def test_unknown_component_rejected():
    scores = dict(FULL)
    scores["vibes"] = 5
    with pytest.raises(errors.LeadPipeError):
        scoring.validate_components(scores)


def test_score_lead_tool_computes_total(demo_ctx):
    result = dispatch(
        demo_ctx,
        "capture_lead",
        name="Score Me",
        email="score@example.com",
        source="website",
    )
    lead_id = result["lead_id"]
    scored = dispatch(demo_ctx, "score_lead", lead_id=lead_id, scores=FULL)
    assert scored["ok"] is True
    assert scored["score_total"] == 100
    assert scored["band"] == "HOT"
    stored = dispatch(demo_ctx, "get_lead", lead_id=lead_id)["lead"]
    assert stored["score_total"] == 100
    assert stored["score_problem"] == 20


def test_total_supplied_by_caller_is_rejected(demo_ctx):
    result = dispatch(
        demo_ctx,
        "score_lead",
        lead_id="LP-2026-00001",
        scores=FULL,
        score_total=100,
    )
    assert result["ok"] is False
    assert result["error"]["code"] == errors.VALIDATION_ERROR


def test_score_unknown_lead(demo_ctx):
    result = dispatch(demo_ctx, "score_lead", lead_id="LP-2026-99999", scores=FULL)
    assert result["ok"] is False
    assert result["error"]["code"] == errors.LEAD_NOT_FOUND


def test_rescore_replaces_atomically(demo_ctx):
    lead_id = dispatch(
        demo_ctx, "capture_lead", name="Re", email="re@example.com", source="email"
    )["lead_id"]
    dispatch(demo_ctx, "score_lead", lead_id=lead_id, scores=FULL)
    low = {f: 0 for f in scoring.COMPONENT_RANGES}
    result = dispatch(demo_ctx, "score_lead", lead_id=lead_id, scores=low)
    assert result["score_total"] == 0
    assert result["band"] == "LOW"
