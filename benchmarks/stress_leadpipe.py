"""LeadPipe stress benchmarks (pytest-benchmark).

Run with:

    pytest benchmarks/stress_leadpipe.py --benchmark-only

Each scenario runs once under the pytest-benchmark harness
(pedantic, 1 round) while the workload itself records per-call
latencies with time.perf_counter; those per-call samples are what
benchmarks/RESULTS.md reports (ops/sec from summed call latencies,
p95 across calls). A session fixture writes the raw measurements to
benchmarks/last_run.json so RESULTS.md is generated, never hand-typed.

Correctness is asserted inside the workloads themselves; the same
workloads run as plain tests in test_stress_invariants.py.
"""

from __future__ import annotations

import json
import random
from pathlib import Path

import pytest

pytest.importorskip(
    "pytest_benchmark", reason="stress benchmarks need pytest-benchmark"
)

import stress_common as sc  # noqa: E402

from leadpipe.tools import dispatch  # noqa: E402

COLLECTED: dict = {}


@pytest.fixture(scope="session", autouse=True)
def _write_last_run():
    yield
    path = Path(__file__).with_name("last_run.json")
    path.write_text(json.dumps(COLLECTED, indent=2, sort_keys=True))


def _run(benchmark, key: str, fn) -> dict:
    result = benchmark.pedantic(fn, rounds=1, iterations=1, warmup_rounds=0)
    COLLECTED[key] = result
    return result


def test_l1_scoring_core(benchmark) -> None:
    result = _run(benchmark, "l1", sc.scenario_l1)
    assert result["calls"] == 10_000


def test_l2_capture_volume(benchmark) -> None:
    result = _run(benchmark, "l2", sc.scenario_l2)
    assert result["rows"] == 1000
    assert result["unique_ids"] == 1000


@pytest.mark.parametrize("size", [0, 1000, 10_000])
def test_l3_dedup_cost(benchmark, size: int) -> None:
    result = _run(benchmark, f"l3_{size}", lambda: sc.scenario_l3(size))
    assert result["dup_created"] == 0
    assert result["rows_final"] == size + 200


_BUILT: dict | None = None


def _built_store() -> dict:
    global _BUILT
    if _BUILT is None:
        _BUILT = sc.build_scored_store()
    return _BUILT


def test_l4_score_at_scale(benchmark) -> None:
    built = _built_store()
    result = sc.scenario_l4(built)
    COLLECTED["l4"] = {
        "verified": result["verified"],
        "mismatches": result["mismatches"],
        "score_timing": result["score_timing"],
    }
    assert result["mismatches"] == []
    # Time a second 1,000-lead scoring pass over the same store so the
    # benchmark harness measures the dispatch itself, not the fixture.
    rng = random.Random(sc.SEED)
    plan = [
        (lead_id, sc.components_for_total(rng, total))
        for lead_id, (total, _band) in built["expected"].items()
    ]

    def rescore() -> None:
        for lead_id, comps in plan:
            dispatch(built["ctx"], "score_lead", lead_id=lead_id, scores=comps)

    benchmark.pedantic(rescore, rounds=1, iterations=1, warmup_rounds=0)


def test_l5_reads_at_scale(benchmark) -> None:
    result = _run(benchmark, "l5", lambda: sc.scenario_l5(_built_store()))
    assert result["hot_count"] == 60
    assert result["summary_stage_sum"] == 10_000


def test_l6_booking_idempotency(benchmark) -> None:
    result = _run(benchmark, "l6", sc.scenario_l6)
    assert result["same_created"] == 1
    assert result["events_final"] == 501


def test_l7_concurrency_probe(benchmark) -> None:
    result = _run(benchmark, "l7", sc.scenario_l7)
    assert result["total_calls"] == 2000
    assert result["final_rows"] == result["expected_rows"]
