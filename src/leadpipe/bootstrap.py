"""Bootstrap command (SPEC Section 3.3).

Usage:
    python -m leadpipe.bootstrap [--demo]
    leadpipe bootstrap [--demo]

Creates missing tabs and headers, initialises Meta, and never rewrites
existing data: a mismatched tab aborts the run with SCHEMA_MISMATCH.
With --demo it also seeds the demo dataset (only into an empty Sheet).
"""

from __future__ import annotations

import sys

from . import errors
from .config import Config
from .demo_data import seed_demo_dataset
from .store.fake import FakeGoogleClient
from .store.schema import bootstrap_store


def run(config: Config, demo_seed: bool = False) -> dict:
    if config.demo:
        client = FakeGoogleClient()
        report = bootstrap_store(client)
        result = {"mode": "demo", "sheet_id": "in-memory-demo", **report}
        if demo_seed:
            result["seed"] = seed_demo_dataset(client)
        return result
    config.require_google()
    from .store.sheets import build_clients

    store, calendar = build_clients(config)
    report = bootstrap_store(store)
    result = {
        "mode": "google",
        "sheet_id": config.sheet_id,
        "sheet_url": f"https://docs.google.com/spreadsheets/d/{config.sheet_id}",
        **report,
    }
    if demo_seed:
        result["seed"] = seed_demo_dataset(_Composite(store, calendar))
    return result


class _Composite:
    """Presents one store+calendar surface over the two Google clients."""

    def __init__(self, store, calendar) -> None:
        self._store = store
        self._calendar = calendar

    def __getattr__(self, name):
        if hasattr(self._store, name):
            return getattr(self._store, name)
        return getattr(self._calendar, name)


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    demo_seed = "--demo" in args
    try:
        config = Config.from_env()
        result = run(config, demo_seed=demo_seed)
    except errors.LeadPipeError as exc:
        print(f"bootstrap failed [{exc.code}]: {exc.message}", file=sys.stderr)
        return 2
    print("LeadPipe bootstrap complete")
    for key, value in result.items():
        print(f"  {key}: {value}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
