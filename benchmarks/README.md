# LeadPipe stress benchmarks

How LeadPipe behaves at volumes a single small business will never
reach, measured in-process against the in-memory fake store. The point
is not the headline speed; it is that the invariants (dedup, sequence,
idempotency, recomputed scores) still hold at 10,000 leads, and that
the one place they might not, concurrent writes, is probed openly.

## Run it

```bash
pip install -e ".[dev]"        # dev extras include pytest-benchmark

# Correctness only (no timing dependency, suitable for CI):
pytest benchmarks/test_stress_invariants.py

# Timed suite (writes benchmarks/last_run.json):
pytest benchmarks/stress_leadpipe.py --benchmark-only
```

`benchmarks/RESULTS.md` is generated from a real run's
`last_run.json` plus the invariant suite outcome. Results are
re-measured, never hand-edited: if a number in RESULTS.md did not come
out of a run on the stated machine and date, it does not belong there.

## Method

- Everything goes through `leadpipe.tools.dispatch`, the same entry
  the MCP server uses, against `FakeGoogleClient` only.
- Fixture preloads write through the store protocol directly. Scoring
  1,000 of 10,000 leads measures dispatch; preloading through
  capture_lead would measure fixture construction instead.
- Seed data is deterministic: `random.Random(20261109)`, fixed clock
  Monday 2026-11-23 09:00 UTC, the conftest pattern from `tests/`.
- Timings: pytest-benchmark harness (pedantic, 1 round per scenario)
  around workloads that record per-call latencies with
  `time.perf_counter`. Ops/sec is operations divided by the summed
  per-call latencies; p95 is across individual calls (for L7, across
  all 2,000 calls in 8 threads; for L5, across 20 repeated reads).

## What each scenario proves

- **L1, scoring control.** 10,000 pure `scoring.score()` calls,
  including exact band boundaries (49/50, 64/65, 79/80, 0, 100).
  Totals always equal the component sum and bands always match
  `band_for`. This is the control: if L1 is slow, everything is.
- **L2, capture volume.** 1,000 unique captures into an empty store
  produce exactly 1,000 rows, unique sequential IDs,
  `next_lead_seq` advanced by exactly 1,000, and exactly 1,000 audit
  entries: one audited write per capture, no silent extras.
- **L3, dedup cost.** At preload sizes 0, 1,000 and 10,000: 200
  duplicate captures (email match) create zero rows and 200 fresh
  captures create exactly 200. Dedup is a full scan in v0.1, so this
  prices that scan honestly as the store grows.
- **L4, scoring at scale.** 1,000 of 10,000 preloaded leads are scored
  through dispatch with forced totals (60 HOT, 140 WARM, 300 NURTURE,
  500 LOW). Every stored total and band must equal the forced values,
  and recomputing from the stored components must reproduce them: a
  hand-edited sheet can never produce an inconsistent total.
- **L5, reads at scale.** `list_hot_leads` returns exactly the 60
  forced HOT leads and `daily_pipeline_summary` stage counts sum to
  the full 10,000, with band counts matching the forced distribution
  plus 9,000 unscored.
- **L6, booking idempotency.** 500 booking calls with the same
  lead and slot produce exactly 1 event and one appointment ID; 500
  calls with distinct keys produce exactly 500 more events. Retries
  are free; duplicates are impossible by construction.
- **L7, concurrency probe.** 8 threads x 250 mixed calls (800 unique
  captures, 600 scores, 600 gets) on ONE shared `FakeGoogleClient`.
  The hard accounting must hold (2,000 outcomes, final rows equal
  preloaded plus successful creates). ID uniqueness and zero errors
  are asserted separately: sequence allocation lives in the store
  (`allocate_lead_seq`, under a per-store lock), so concurrent
  captures cannot mint the same ID. An earlier version of capture did
  the read-modify-write itself, non-atomically, and this probe caught
  the resulting duplicate IDs; RESULTS.md records both the finding
  and the fixed run. The probe stays in the suite as the regression
  check.

## Exclusions

No MCP stdio framing, no network, no Google API. The production
Sheets backend is API-bound; its latency is Google's, not LeadPipe's,
and it is not measured here. See the honesty note in RESULTS.md.
