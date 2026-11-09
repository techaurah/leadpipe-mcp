"""Shared deterministic workloads for the LeadPipe stress suite.

Every scenario runs in-process through ``leadpipe.tools.dispatch``
against ``FakeGoogleClient`` only: no network, no MCP stdio framing,
no real Google backend. Seed data comes from ``random.Random(SEED)``
so a re-run generates the identical workload; only the timings change.

Fixture setup (preloading rows) writes through the store protocol
directly, never through dispatch: preloading 10,000 leads through
capture_lead would measure fixture construction, not the scenario.
"""

from __future__ import annotations

import random
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta

from leadpipe import scoring
from leadpipe.config import Config
from leadpipe.models import WriteMode
from leadpipe.store import schema
from leadpipe.store.fake import FakeGoogleClient
from leadpipe.store.schema import bootstrap_store
from leadpipe.tools import ToolContext, dispatch, recompute

SEED = 20261109
FIXED_NOW = datetime(2026, 11, 23, 9, 0, tzinfo=UTC)
SOURCES = ("website", "instagram", "facebook", "whatsapp", "email", "referral")

# (band, min total, max total, forced count) for the 1,000 scored leads
# in the 10,000-lead store used by L4 and L5.
FORCED_BANDS = (
    ("HOT", 80, 100, 60),
    ("WARM", 65, 79, 140),
    ("NURTURE", 50, 64, 300),
    ("LOW", 0, 49, 500),
)
SCORED_COUNT = sum(count for *_range, count in FORCED_BANDS)


def make_ctx() -> tuple[FakeGoogleClient, ToolContext]:
    """A bootstrapped fake store with the conftest fixed clock."""
    client = FakeGoogleClient()
    bootstrap_store(client, now=FIXED_NOW)
    ctx = ToolContext(
        store=client,
        calendar=client,
        config=Config(demo=True, write_mode=WriteMode.DIRECT),
    )
    return client, ctx


def components_for_total(rng: random.Random, total: int) -> dict[str, int]:
    """Eight valid score components summing exactly to ``total``.

    Field order is shuffled by ``rng``; each field takes a random amount
    bounded by its range and by what the remaining fields can still
    absorb, so the total is exact for every value in 0..100.
    """
    fields = list(scoring.COMPONENT_RANGES)
    rng.shuffle(fields)
    components = {field: 0 for field in scoring.COMPONENT_FIELDS}
    remaining = total
    for pos, field in enumerate(fields):
        _low, high = scoring.COMPONENT_RANGES[field]
        capacity_after = sum(scoring.COMPONENT_RANGES[f][1] for f in fields[pos + 1 :])
        take = rng.randint(max(0, remaining - capacity_after), min(high, remaining))
        components[field] = take
        remaining -= take
    if remaining != 0:  # pragma: no cover, guards the generator itself
        raise AssertionError(f"could not place total {total}")
    return components


def make_row(seq: int, email: str = "", name: str = "") -> dict[str, str]:
    row = {header: "" for header in schema.LEADS_HEADERS}
    row.update(
        {
            "lead_id": f"LP-2026-{seq:05d}",
            "created_at": "2026-11-23T09:00:00Z",
            "updated_at": "2026-11-23T09:00:00Z",
            "name": name or f"Preloaded Lead {seq}",
            "email": email,
            "source": "website",
            "stage": "NEW",
            "owner": "unassigned",
        }
    )
    return row


def preload(client: FakeGoogleClient, count: int, email_prefix: str) -> list[str]:
    """Append ``count`` unscored leads directly and advance the sequence.

    Returns the lead IDs in order. ``next_lead_seq`` is set to
    ``count + 1`` so later capture_lead calls continue the sequence.
    """
    ids = []
    for seq in range(1, count + 1):
        row = make_row(seq, email=f"{email_prefix}{seq}@example.test")
        client.append_lead(row)
        ids.append(row["lead_id"])
    client.set_meta("next_lead_seq", str(count + 1))
    return ids


class OpTimer:
    """Per-call latency samples around a callable."""

    def __init__(self) -> None:
        self.samples: list[float] = []

    def time(self, fn, *args, **kwargs):
        start = time.perf_counter()
        result = fn(*args, **kwargs)
        self.samples.append(time.perf_counter() - start)
        return result

    def stats(self, ops: int | None = None) -> dict:
        count = len(self.samples)
        total = sum(self.samples)
        ordered = sorted(self.samples)
        p95 = ordered[min(count - 1, int(0.95 * count))] if count else 0.0
        return {
            "ops": ops if ops is not None else count,
            "seconds": round(total, 4),
            "ops_per_sec": round((ops or count) / total, 1) if total else 0.0,
            "mean_ms": round(total / count * 1000, 3) if count else 0.0,
            "p95_ms": round(p95 * 1000, 3),
        }


# ---------------------------------------------------------------------------
# L1: pure scoring core control.
# ---------------------------------------------------------------------------


def scenario_l1() -> dict:
    rng = random.Random(SEED)
    boundaries = [
        (0, "LOW"),
        (49, "LOW"),
        (50, "NURTURE"),
        (64, "NURTURE"),
        (65, "WARM"),
        (79, "WARM"),
        (80, "HOT"),
        (100, "HOT"),
    ]
    cases: list[dict[str, int]] = []
    for i in range(10_000):
        if i % 8 == 0:
            total, _band = boundaries[(i // 8) % len(boundaries)]
        else:
            total = rng.randint(0, 100)
        cases.append(components_for_total(rng, total))

    timer = OpTimer()
    boundary_hits = 0
    for comps in cases:
        components, total, band = timer.time(scoring.score, comps)
        if total != sum(comps.values()):
            raise AssertionError(f"total {total} != components {comps}")
        if band is not scoring.band_for(total):
            raise AssertionError(f"band {band} inconsistent with total {total}")
        if components != comps:
            raise AssertionError("score() mutated or dropped components")
    for total, band_name in boundaries:
        comps = components_for_total(random.Random(SEED + total), total)
        _components, got_total, got_band = scoring.score(comps)
        if got_total != total or got_band.value != band_name:
            raise AssertionError(
                f"boundary {total}: got total {got_total}, band {got_band.value}"
            )
        boundary_hits += 1
    return {
        "calls": 10_000,
        "boundary_cases_checked": boundary_hits,
        "timing": timer.stats(ops=10_000),
    }


# ---------------------------------------------------------------------------
# L2: capture volume into an empty store.
# ---------------------------------------------------------------------------


def scenario_l2() -> dict:
    client, ctx = make_ctx()
    timer = OpTimer()
    results = []
    for i in range(1, 1001):
        results.append(
            timer.time(
                dispatch,
                ctx,
                "capture_lead",
                name=f"Stress Lead {i}",
                email=f"stress{i}@example.test",
                source=SOURCES[i % len(SOURCES)],
            )
        )
    rows = client.list_leads()
    ids = [row["lead_id"] for row in rows]
    suffixes = sorted(int(lead_id.rsplit("-", 1)[1]) for lead_id in ids)
    return {
        "results_ok_created": sum(
            1 for r in results if r.get("ok") and r.get("created")
        ),
        "rows": len(rows),
        "unique_ids": len(set(ids)),
        "sequential_ids": suffixes == list(range(1, 1001)),
        "next_lead_seq": client.get_meta("next_lead_seq"),
        "audit_entries": len(client.list_audit()),
        "timing": timer.stats(ops=1000),
    }


# ---------------------------------------------------------------------------
# L3: dedup cost at three preload sizes.
# ---------------------------------------------------------------------------


def scenario_l3(size: int) -> dict:
    client, ctx = make_ctx()
    if size:
        preload(client, size, "preload")
    fresh_timer, dup_timer = OpTimer(), OpTimer()
    fresh_results = []
    for i in range(1, 201):
        fresh_results.append(
            fresh_timer.time(
                dispatch,
                ctx,
                "capture_lead",
                name=f"Fresh {size} {i}",
                email=f"fresh{size}_{i}@example.test",
                source="website",
            )
        )
    if size:
        dup_emails = [f"preload{i}@example.test" for i in range(size - 199, size + 1)]
    else:
        dup_emails = [f"fresh0_{i}@example.test" for i in range(1, 201)]
    dup_results = []
    for j, email in enumerate(dup_emails):
        dup_results.append(
            dup_timer.time(
                dispatch,
                ctx,
                "capture_lead",
                name=f"Duplicate {j}",
                email=email,
                source="website",
            )
        )
    return {
        "preload": size,
        "fresh_created": sum(1 for r in fresh_results if r.get("created")),
        "fresh_ok": sum(1 for r in fresh_results if r.get("ok")),
        "dup_created": sum(1 for r in dup_results if r.get("created")),
        "dup_deduped": sum(1 for r in dup_results if r.get("deduped")),
        "rows_final": len(client.list_leads()),
        "fresh_timing": fresh_timer.stats(ops=200),
        "dup_timing": dup_timer.stats(ops=200),
    }


# ---------------------------------------------------------------------------
# L4 and L5: scoring and reads on a 10,000-lead store.
# ---------------------------------------------------------------------------


def build_scored_store() -> dict:
    """10,000 preloaded leads; the first 1,000 scored via dispatch with
    forced totals (60 HOT, 140 WARM, 300 NURTURE, 500 LOW)."""
    rng = random.Random(SEED)
    client, ctx = make_ctx()
    ids = preload(client, 10_000, "bulk")
    targets: list[tuple[str, int]] = []
    for band_name, low, high, count in FORCED_BANDS:
        for _ in range(count):
            targets.append((band_name, rng.randint(low, high)))
    rng.shuffle(targets)
    timer = OpTimer()
    expected: dict[str, tuple[int, str]] = {}
    for lead_id, (band_name, total) in zip(ids[:SCORED_COUNT], targets, strict=True):
        comps = components_for_total(rng, total)
        result = timer.time(dispatch, ctx, "score_lead", lead_id=lead_id, scores=comps)
        if not result.get("ok"):
            raise AssertionError(f"score_lead failed for {lead_id}: {result}")
        if result["score_total"] != total or result["band"] != band_name:
            raise AssertionError(
                f"score_lead for {lead_id}: got {result['score_total']}/"
                f"{result['band']}, forced {total}/{band_name}"
            )
        expected[lead_id] = (total, band_name)
    return {
        "client": client,
        "ctx": ctx,
        "expected": expected,
        "score_timing": timer.stats(ops=SCORED_COUNT),
    }


def scenario_l4(built: dict) -> dict:
    rows = {row["lead_id"]: row for row in built["client"].list_leads()}
    mismatches = []
    for lead_id, (total, band_name) in built["expected"].items():
        row = rows[lead_id]
        recomputed_total, recomputed_band = recompute(row)
        if (
            row.get("score_total") != str(total)
            or row.get("band") != band_name
            or recomputed_total != total
            or recomputed_band != band_name
        ):
            mismatches.append(
                {
                    "lead_id": lead_id,
                    "stored": (row.get("score_total"), row.get("band")),
                    "recomputed": (recomputed_total, recomputed_band),
                    "expected": (total, band_name),
                }
            )
    return {
        "verified": len(built["expected"]) - len(mismatches),
        "mismatches": mismatches,
        "score_timing": built["score_timing"],
    }


def scenario_l5(built: dict) -> dict:
    ctx = built["ctx"]
    hot_timer, summary_timer = OpTimer(), OpTimer()
    hot = None
    for _ in range(20):
        hot = hot_timer.time(dispatch, ctx, "list_hot_leads", limit=100)
    summary = None
    for _ in range(20):
        summary = summary_timer.time(dispatch, ctx, "daily_pipeline_summary")
    expected_bands = {"HOT": 60, "WARM": 140, "NURTURE": 300, "LOW": 500}
    expected_bands["UNSCORED"] = 10_000 - SCORED_COUNT
    return {
        "hot_count": hot["count"] if hot else None,
        "hot_all_hot": bool(hot)
        and all(lead["band"] == "HOT" for lead in hot["leads"]),
        "summary_total": summary["total_leads"] if summary else None,
        "summary_stage_sum": sum(summary["by_stage"].values()) if summary else None,
        "summary_by_band": summary["by_band"] if summary else None,
        "expected_by_band": expected_bands,
        "hot_timing": hot_timer.stats(ops=20),
        "summary_timing": summary_timer.stats(ops=20),
    }


# ---------------------------------------------------------------------------
# L6: booking idempotency.
# ---------------------------------------------------------------------------


def _event_count(client: FakeGoogleClient) -> int:
    return len(
        client.list_events(
            datetime(2026, 1, 1, tzinfo=UTC), datetime(2027, 6, 1, tzinfo=UTC)
        )
    )


def scenario_l6() -> dict:
    client, ctx = make_ctx()
    ids = preload(client, 501, "book")
    same_timer = OpTimer()
    same_results = []
    for _ in range(500):
        same_results.append(
            same_timer.time(
                dispatch,
                ctx,
                "book_appointment",
                lead_id=ids[0],
                start="2026-11-24T09:00:00Z",
                end="2026-11-24T09:30:00Z",
            )
        )
    events_after_same = _event_count(client)

    distinct_timer = OpTimer()
    distinct_results = []
    base = datetime(2026, 11, 24, tzinfo=UTC)
    for k, lead_id in enumerate(ids[1:]):
        start = base + timedelta(days=k // 8, hours=k % 8)
        end = start + timedelta(minutes=30)
        distinct_results.append(
            distinct_timer.time(
                dispatch,
                ctx,
                "book_appointment",
                lead_id=lead_id,
                start=start.isoformat().replace("+00:00", "Z"),
                end=end.isoformat().replace("+00:00", "Z"),
            )
        )
    appointment_ids = {r.get("appointment_id") for r in same_results}
    return {
        "same_ok": sum(1 for r in same_results if r.get("ok")),
        "same_created": sum(1 for r in same_results if r.get("created")),
        "same_appointment_ids": len(appointment_ids),
        "events_after_same_key": events_after_same,
        "distinct_ok": sum(1 for r in distinct_results if r.get("ok")),
        "distinct_created": sum(1 for r in distinct_results if r.get("created")),
        "events_final": _event_count(client),
        "same_timing": same_timer.stats(ops=500),
        "distinct_timing": distinct_timer.stats(ops=500),
    }


# ---------------------------------------------------------------------------
# L7: concurrency probe on one shared client. No invariant is asserted
# here: the raw outcome is returned so callers can record findings.
# ---------------------------------------------------------------------------


def scenario_l7() -> dict:
    rng = random.Random(SEED)
    client, ctx = make_ctx()
    preloaded = preload(client, 500, "seed")

    captures = [
        (
            "capture_lead",
            {
                "name": f"Concurrent {n}",
                "email": f"conc{n}@example.test",
                "source": "website",
            },
        )
        for n in range(1, 801)
    ]
    scores = []
    for j in range(600):
        total = 40 + (j % 61)
        scores.append(
            (
                "score_lead",
                {
                    "lead_id": preloaded[j % 500],
                    "scores": components_for_total(rng, total),
                },
            )
        )
    gets = [("get_lead", {"lead_id": preloaded[(j * 7) % 500]}) for j in range(600)]
    pools = [captures[i * 100 : (i + 1) * 100] for i in range(8)]
    pools = [
        pool + scores[i * 75 : (i + 1) * 75] + gets[i * 75 : (i + 1) * 75]
        for i, pool in enumerate(pools)
    ]
    for w, pool in enumerate(pools):
        random.Random(SEED + w).shuffle(pool)

    def run_jobs(job_list: list) -> list[dict]:
        outcomes = []
        for tool, kwargs in job_list:
            start = time.perf_counter()
            try:
                result = dispatch(ctx, tool, **kwargs)
                outcomes.append(
                    {
                        "tool": tool,
                        "ok": bool(result.get("ok")),
                        "created": bool(result.get("created")),
                        "lead_id": result.get("lead_id"),
                        "error_code": (result.get("error") or {}).get("code")
                        if not result.get("ok")
                        else None,
                        "exception": None,
                        "seconds": time.perf_counter() - start,
                    }
                )
            except Exception as exc:  # recorded as a finding, never hidden
                outcomes.append(
                    {
                        "tool": tool,
                        "ok": False,
                        "created": False,
                        "lead_id": None,
                        "error_code": None,
                        "exception": f"{type(exc).__name__}: {exc}",
                        "seconds": time.perf_counter() - start,
                    }
                )
        return outcomes

    wall_start = time.perf_counter()
    with ThreadPoolExecutor(max_workers=8) as executor:
        per_worker = list(executor.map(run_jobs, pools))
    wall_seconds = time.perf_counter() - wall_start
    outcomes = [outcome for batch in per_worker for outcome in batch]

    created_ids = [
        o["lead_id"]
        for o in outcomes
        if o["tool"] == "capture_lead" and o["created"] and o["lead_id"]
    ]
    id_counts = Counter(created_ids)
    duplicate_ids = {lid: c for lid, c in id_counts.items() if c > 1}
    exceptions = [o["exception"] for o in outcomes if o["exception"]]
    error_codes = Counter(
        o["error_code"] for o in outcomes if not o["ok"] and not o["exception"]
    )
    samples = [o["seconds"] for o in outcomes]
    ordered = sorted(samples)
    finding = None
    if duplicate_ids or exceptions or error_codes:
        finding = {
            "duplicate_lead_ids": {
                "distinct_ids": len(duplicate_ids),
                "extra_rows": sum(c - 1 for c in duplicate_ids.values()),
                "sample": dict(list(duplicate_ids.items())[:5]),
            },
            "exceptions": {
                "count": len(exceptions),
                "sample": exceptions[:5],
            },
            "error_results_by_code": dict(error_codes),
        }
    return {
        "total_calls": len(outcomes),
        "ok": sum(1 for o in outcomes if o["ok"]),
        "capture_created": len(created_ids),
        "capture_deduped_or_failed": sum(
            1 for o in outcomes if o["tool"] == "capture_lead" and not o["created"]
        ),
        "unique_created_ids": len(set(created_ids)),
        "final_rows": len(client.list_leads()),
        "expected_rows": 500 + len(created_ids),
        "wall_seconds": round(wall_seconds, 4),
        "ops_per_sec": round(len(outcomes) / wall_seconds, 1),
        "p95_ms": round(ordered[int(0.95 * len(ordered))] * 1000, 3),
        "finding": finding,
    }
