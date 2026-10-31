"""Shared fixtures. Every test runs against FakeGoogleClient; no test
touches the network or real Google credentials (SPEC Section 7).

The demo seed uses a fixed moment: Monday 2026-11-23 09:00 UTC.
Business days seeded: Tue 2026-11-24, Wed 2026-11-25, Thu 2026-11-26.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from leadpipe.config import Config
from leadpipe.demo_data import seed_demo_dataset
from leadpipe.models import WriteMode
from leadpipe.store.fake import FakeGoogleClient
from leadpipe.store.schema import bootstrap_store
from leadpipe.tools import ToolContext

FIXED_NOW = datetime(2026, 11, 23, 9, 0, tzinfo=UTC)


def make_client(seed: bool = False) -> FakeGoogleClient:
    client = FakeGoogleClient()
    bootstrap_store(client, now=FIXED_NOW)
    if seed:
        seed_demo_dataset(client, now=FIXED_NOW)
    return client


def make_ctx(
    seed: bool = False, write_mode: WriteMode = WriteMode.DIRECT
) -> ToolContext:
    client = make_client(seed=seed)
    return ToolContext(
        store=client,
        calendar=client,
        config=Config(demo=True, write_mode=write_mode),
    )


@pytest.fixture()
def empty_ctx() -> ToolContext:
    return make_ctx(seed=False)


@pytest.fixture()
def demo_ctx() -> ToolContext:
    return make_ctx(seed=True)


@pytest.fixture()
def demo_client() -> FakeGoogleClient:
    return make_client(seed=True)
