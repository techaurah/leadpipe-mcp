"""MCP server entry point (SPEC Section 6).

The official MCP SDK (FastMCP) is imported lazily, inside
``create_server``, so the core logic, the demo walkthrough and the whole
test suite run in environments where the ``mcp`` package is not
installed. Only actually serving over stdio requires it.

Commands:
    leadpipe            serve over stdio
    leadpipe demo       serve in demo mode (fake client, seeded data)
    leadpipe bootstrap  create/validate the Sheet schema
"""

from __future__ import annotations

import sys

from . import errors
from .config import Config
from .tools import ToolContext, dispatch


def build_context(config: Config) -> ToolContext:
    """Wire a ToolContext for demo or real mode."""
    if config.demo:
        from .demo_data import seed_demo_dataset
        from .store.fake import FakeGoogleClient
        from .store.schema import bootstrap_store

        client = FakeGoogleClient()
        bootstrap_store(client)
        seed_demo_dataset(client)
        return ToolContext(store=client, calendar=client, config=config)
    config.require_google()
    from .store.sheets import build_clients

    store, calendar = build_clients(config)
    return ToolContext(store=store, calendar=calendar, config=config)


def create_server(config: Config):
    """Create the FastMCP server with the eight tools registered."""
    try:
        from mcp.server.fastmcp import FastMCP
    except ImportError:
        raise errors.LeadPipeError(
            errors.CONFIG_ERROR,
            "The MCP SDK is not installed. Install it with: "
            "pip install 'leadpipe-mcp' (or 'mcp' on its own). "
            "The core tools and demo walkthrough work without it; "
            "only stdio serving requires it.",
        ) from None

    ctx = build_context(config)
    server = FastMCP("leadpipe")

    @server.tool()
    def capture_lead(
        name: str,
        source: str,
        email: str | None = None,
        phone: str | None = None,
        company: str | None = None,
        service_interest: str | None = None,
        location: str | None = None,
        problem_notes: str | None = None,
        dry_run: bool = False,
        confirm: bool = False,
    ) -> dict:
        """Record a new lead, deduplicating on email then phone before any write."""
        return dispatch(
            ctx,
            "capture_lead",
            name=name,
            source=source,
            email=email,
            phone=phone,
            company=company,
            service_interest=service_interest,
            location=location,
            problem_notes=problem_notes,
            dry_run=dry_run,
            confirm=confirm,
        )

    @server.tool()
    def get_lead(
        lead_id: str | None = None,
        email: str | None = None,
        phone: str | None = None,
    ) -> dict:
        """Fetch one lead by lead_id, email or phone (exactly one)."""
        return dispatch(ctx, "get_lead", lead_id=lead_id, email=email, phone=phone)

    @server.tool()
    def list_hot_leads(limit: int = 20, include_booked: bool = False) -> dict:
        """List HOT leads (score 80+), highest score first, oldest first."""
        return dispatch(
            ctx, "list_hot_leads", limit=limit, include_booked=include_booked
        )

    @server.tool()
    def score_lead(
        lead_id: str,
        scores: dict,
        dry_run: bool = False,
        confirm: bool = False,
    ) -> dict:
        """Apply the deterministic scoring model. The eight component
        judgements are supplied by the caller; the total is computed
        server-side and never accepted as an input."""
        return dispatch(
            ctx,
            "score_lead",
            lead_id=lead_id,
            scores=scores,
            dry_run=dry_run,
            confirm=confirm,
        )

    @server.tool()
    def update_stage(
        lead_id: str,
        stage: str,
        note: str | None = None,
        dry_run: bool = False,
        confirm: bool = False,
    ) -> dict:
        """Move a lead to a new stage; illegal transitions are rejected."""
        return dispatch(
            ctx,
            "update_stage",
            lead_id=lead_id,
            stage=stage,
            note=note,
            dry_run=dry_run,
            confirm=confirm,
        )

    @server.tool()
    def check_availability(start: str, end: str, slot_minutes: int = 30) -> dict:
        """Free slots on the business calendar, intersected with business
        hours. Busy times are returned without titles."""
        return dispatch(
            ctx,
            "check_availability",
            start=start,
            end=end,
            slot_minutes=slot_minutes,
        )

    @server.tool()
    def book_appointment(
        lead_id: str,
        start: str,
        end: str,
        title: str | None = None,
        notes: str | None = None,
        dry_run: bool = False,
        confirm: bool = False,
    ) -> dict:
        """Book a calendar appointment for a lead. Availability is
        re-checked at call time and repeat calls never duplicate."""
        return dispatch(
            ctx,
            "book_appointment",
            lead_id=lead_id,
            start=start,
            end=end,
            title=title,
            notes=notes,
            dry_run=dry_run,
            confirm=confirm,
        )

    @server.tool()
    def daily_pipeline_summary(date: str | None = None) -> dict:
        """One-call summary: counts by stage and band, hot unbooked
        leads, today's appointments, overdue next actions."""
        return dispatch(ctx, "daily_pipeline_summary", date=date)

    return server


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if args and args[0] == "bootstrap":
        from .bootstrap import main as bootstrap_main

        return bootstrap_main(args[1:])
    try:
        env: dict[str, str] = {}
        import os

        env.update(os.environ)
        if args and args[0] == "demo":
            env["LEADPIPE_DEMO"] = "1"
        config = Config.from_env(env)
        server = create_server(config)
    except errors.LeadPipeError as exc:
        print(f"leadpipe [{exc.code}]: {exc.message}", file=sys.stderr)
        return 2
    server.run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
