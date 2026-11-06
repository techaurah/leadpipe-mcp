"""Tool annotations: every registered tool declares the four MCP hints.

M8ven's listing flagged all eight tools as missing readOnlyHint,
destructiveHint, idempotentHint and openWorldHint. This test pins the
values so a future tool cannot ship unannotated by accident.
"""

from __future__ import annotations

import asyncio

import pytest

pytest.importorskip("mcp")

from leadpipe.config import Config
from leadpipe.server import create_server

EXPECTED = {
    # name: (readOnly, destructive, idempotent, openWorld)
    "capture_lead": (False, False, True, True),
    "get_lead": (True, False, True, True),
    "list_hot_leads": (True, False, True, True),
    "score_lead": (False, False, True, True),
    "update_stage": (False, False, False, True),
    "check_availability": (True, False, True, True),
    "book_appointment": (False, False, True, True),
    "daily_pipeline_summary": (True, False, True, True),
}


def test_all_tools_declare_all_four_annotations() -> None:
    server = create_server(Config(demo=True))
    tools = asyncio.run(server.list_tools())
    assert {t.name for t in tools} == set(EXPECTED)
    for tool in tools:
        assert tool.annotations is not None, tool.name
        got = (
            tool.annotations.readOnlyHint,
            tool.annotations.destructiveHint,
            tool.annotations.idempotentHint,
            tool.annotations.openWorldHint,
        )
        assert got == EXPECTED[tool.name], tool.name
