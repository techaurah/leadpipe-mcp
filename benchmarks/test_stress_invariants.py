"""Stress invariants as plain pytest tests (no timing dependency).

These run the same deterministic workloads as stress_leadpipe.py and
assert only correctness, so CI can run them without pytest-benchmark:

    pytest benchmarks/test_stress_invariants.py

L7 is split in two: the accounting test must always hold (every call
accounted for, no lost or phantom rows), while the strict test asserts
zero collisions and zero errors. If the strict test fails, its message
is the finding, with counts, and RESULTS.md records it as a FINDING.
"""

from __future__ import annotations

import pytest
import stress_common as sc


def test_l1_scoring_control() -> None:
    result = sc.scenario_l1()
    assert result["calls"] == 10_000
    assert result["boundary_cases_checked"] == 8


def test_l2_capture_volume() -> None:
    result = sc.scenario_l2()
    assert result["results_ok_created"] == 1000
    assert result["rows"] == 1000
    assert result["unique_ids"] == 1000
    assert result["sequential_ids"] is True
    assert result["next_lead_seq"] == "1001"
    assert result["audit_entries"] == 1000


@pytest.mark.parametrize("size", [0, 1000, 10_000])
def test_l3_dedup_cost(size: int) -> None:
    result = sc.scenario_l3(size)
    assert result["fresh_ok"] == 200
    assert result["fresh_created"] == 200
    assert result["dup_created"] == 0
    assert result["dup_deduped"] == 200
    assert result["rows_final"] == size + 200


@pytest.fixture(scope="module")
def built_store() -> dict:
    return sc.build_scored_store()


def test_l4_score_recompute(built_store: dict) -> None:
    result = sc.scenario_l4(built_store)
    assert result["mismatches"] == []
    assert result["verified"] == sc.SCORED_COUNT


def test_l5_hot_and_summary(built_store: dict) -> None:
    result = sc.scenario_l5(built_store)
    assert result["hot_count"] == 60
    assert result["hot_all_hot"] is True
    assert result["summary_total"] == 10_000
    assert result["summary_stage_sum"] == 10_000
    assert result["summary_by_band"] == result["expected_by_band"]


def test_l6_booking_idempotency() -> None:
    result = sc.scenario_l6()
    assert result["same_ok"] == 500
    assert result["same_created"] == 1
    assert result["same_appointment_ids"] == 1
    assert result["events_after_same_key"] == 1
    assert result["distinct_ok"] == 500
    assert result["distinct_created"] == 500
    assert result["events_final"] == 501


@pytest.fixture(scope="module")
def l7_result() -> dict:
    return sc.scenario_l7()


def test_l7_concurrency_accounting(l7_result: dict) -> None:
    """Hard invariants: every call is accounted for and the row count
    is exactly the preloaded rows plus one row per successful create."""
    assert l7_result["total_calls"] == 2000
    assert l7_result["final_rows"] == l7_result["expected_rows"]


def test_l7_no_collisions_or_errors(l7_result: dict) -> None:
    """Strict probe: unique IDs, no exceptions, no error results.

    A failure here is a genuine concurrency finding, reported with
    counts, not a test bug. See benchmarks/RESULTS.md.
    """
    finding = l7_result["finding"]
    assert finding is None, f"FINDING: {finding}"
    assert l7_result["unique_created_ids"] == l7_result["capture_created"]
