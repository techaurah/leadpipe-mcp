# LeadPipe stress results

Measured 2026-11-10. Timed run: `pytest benchmarks/stress_leadpipe.py
--benchmark-only` (pytest-benchmark, pedantic, 1 round per scenario;
per-call latencies recorded with `time.perf_counter` inside the
workloads, raw output in `benchmarks/last_run.json`). Invariant run:
`pytest benchmarks/test_stress_invariants.py`, 10 passed,
0 failed (the L7 strict test passes: see the L7 section below).

Machine: AMD EPYC 9D64 88-Core Processor; RAM 7.7 GB; OS Linux-7.0.0-43-generic-x86_64-with-glibc2.39;
Python 3.12.3; leadpipe-mcp 0.1.0;
source state: local working tree (uncommitted changes present, not a
tagged release).

| Scenario | Volume | Ops/sec | p95 (ms) | Invariants |
| --- | --- | ---: | ---: | --- |
| L1 scoring core (control) | 10,000 score() calls | 181,296.2 | 0.013 | Pass: totals and bands exact, boundaries 0/49/50/64/65/79/80/100 |
| L2 capture volume | 1,000 captures, empty store | 2,847.5 | 0.535 | Pass: 1,000 rows, unique sequential IDs, seq +1,000, 1,000 audit entries |
| L3 dedup at preload 0 | 200 duplicate + 200 fresh captures | 10,007.3 (dup) / 13,141.2 (fresh) | 0.124 (dup) / 0.117 (fresh) | Pass: duplicates created 0 rows, fresh created 200 |
| L3 dedup at preload 1,000 | 200 duplicate + 200 fresh captures | 1,716.1 (dup) / 1,829.8 (fresh) | 0.673 (dup) / 0.627 (fresh) | Pass: duplicates created 0 rows, fresh created 200 |
| L3 dedup at preload 10,000 | 200 duplicate + 200 fresh captures | 185.3 (dup) / 173.4 (fresh) | 6.160 (dup) / 7.012 (fresh) | Pass: duplicates created 0 rows, fresh created 200 |
| L4 score at scale | 1,000 score_lead on a 10,000-lead store | 181.1 | 8.176 | Pass: 1,000 of 1,000 stored totals and bands match forced values and recompute exactly |
| L5 list_hot_leads | 20 calls on the 10,000-lead store | 71.8 | 15.907 | Pass: exactly the 60 forced HOT leads returned |
| L5 daily_pipeline_summary | 20 calls on the 10,000-lead store | 31.3 | 36.484 | Pass: stage counts sum to 10,000; bands 60 HOT / 140 WARM / 300 NURTURE / 500 LOW / 9,000 UNSCORED |
| L6 booking, same key | 500 calls, one lead and slot | 5,509.6 | 0.218 | Pass: exactly 1 event, 1 appointment ID, 499 idempotent returns |
| L6 booking, distinct keys | 500 calls, distinct leads and slots | 3,329.4 | 0.374 | Pass: exactly 500 events created (501 total with L6 same-key) |
| L7 concurrency probe | 2,000 mixed calls, 8 threads, one shared client | 1,820.2 (wall-clock) | 6.104 | Pass: 800 created, 800 unique lead IDs, zero exceptions, zero error results. Accounting held: 2,000 outcomes, final rows 1,300 = expected |

Ops/sec is operations divided by summed per-call latencies, except L7,
which is wall-clock throughput across 8 threads. p95 is across
individual calls (L5: across the 20 repeated reads).

## L7: duplicate lead IDs under concurrent capture, fixed

The previous run of this probe found a real defect: `capture_lead`
allocated an ID by reading `next_lead_seq`, appending the row, then
writing `next_lead_seq + 1` back, and that read-modify-write was not
atomic, so concurrent captures minted duplicate lead IDs (benchmark
run: 800 created, only 411 distinct IDs; invariant run: 800 created,
478 distinct IDs).

Sequence allocation now lives in the store layer:
`store.allocate_lead_seq()` reads `next_lead_seq` and advances it
under a per-store lock, and the write path of `capture_lead` takes its
ID from that call instead of doing its own read-modify-write. The
Sheets backend serialises allocators within the process the same way;
its comment records the limit honestly (the Sheets API has no
compare-and-swap for a cell, so the guarantee is single-process,
which matches how the server runs).

This run, after the fix: 800 capture calls returned created and all
800 lead IDs are distinct, with zero exceptions and zero error
results, and the hard accounting held: exactly 2,000 outcomes and
final rows equal to preloaded plus successful creates. Regression
coverage lives in `tests/test_capture_concurrency.py` and in the L7
strict invariant test, which now passes.

## Honesty note

In-process against the in-memory fake store. These numbers describe
LeadPipe's own code cost; the production Google Sheets backend is
API-bound and is not measured here.

Excluded: MCP stdio framing, network calls, and the Google API.
Dedup and read costs grow linearly with store size in v0.1 (full scans
in capture, list_hot_leads and the summary); the L3 and L5 rows price
that honestly rather than hiding it.

These results are re-measured on each run and regenerated from
`last_run.json`; they are never hand-edited.
