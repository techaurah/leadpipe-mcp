"""Concurrent capture_lead calls on one shared store (SPEC 2.1).

Regression coverage for the duplicate-ID race: capture used to read
next_lead_seq, append, then write the counter back, so two threads
could mint the same lead ID. Allocation now happens atomically in the
store (allocate_lead_seq), and these tests pin that behaviour.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

from leadpipe.tools import dispatch

THREADS = 8
PER_THREAD = 100


def _capture_batch(ctx, worker: int) -> list[dict]:
    results = []
    for i in range(PER_THREAD):
        n = worker * PER_THREAD + i
        results.append(
            dispatch(
                ctx,
                "capture_lead",
                name=f"Concurrent {n}",
                email=f"conc{n}@example.test",
                source="website",
            )
        )
    return results


def test_concurrent_captures_get_unique_ids(empty_ctx):
    with ThreadPoolExecutor(max_workers=THREADS) as pool:
        batches = list(pool.map(lambda w: _capture_batch(empty_ctx, w), range(THREADS)))
    results = [r for batch in batches for r in batch]
    total = THREADS * PER_THREAD
    assert len(results) == total
    assert all(r["ok"] and r["created"] for r in results)
    lead_ids = [r["lead_id"] for r in results]
    assert len(set(lead_ids)) == total
    assert len(empty_ctx.store.list_leads()) == total
    assert empty_ctx.store.get_meta("next_lead_seq") == str(total + 1)


def test_concurrent_allocate_lead_seq_hands_out_each_value_once(empty_ctx):
    store = empty_ctx.store

    def allocate_batch(_worker: int) -> list[int]:
        return [store.allocate_lead_seq() for _ in range(250)]

    with ThreadPoolExecutor(max_workers=THREADS) as pool:
        batches = list(pool.map(allocate_batch, range(THREADS)))
    values = sorted(v for batch in batches for v in batch)
    assert values == list(range(1, THREADS * 250 + 1))
    assert store.get_meta("next_lead_seq") == str(THREADS * 250 + 1)
