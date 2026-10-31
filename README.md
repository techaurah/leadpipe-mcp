<h1 align="center">LeadPipe MCP</h1>

<p align="center">
  <strong>An MCP server that gives an AI assistant a safe lead pipeline, with dedup, scoring, stage rules and booking guardrails, over a Google Sheet the business already owns.</strong>
</p>

<p align="center">
  <a href="LICENSE"><img alt="License: MIT" src="https://img.shields.io/badge/license-MIT-blue.svg"></a>
  <a href="https://github.com/techaurah/leadpipe-mcp/actions/workflows/ci.yml"><img alt="CI" src="https://img.shields.io/github/actions/workflow/status/techaurah/leadpipe-mcp/ci.yml?branch=main"></a>
  <img alt="Python 3.11+" src="https://img.shields.io/badge/python-3.11%2B-blue.svg">
  <img alt="Version 0.1.0" src="https://img.shields.io/badge/version-0.1.0-brightgreen.svg">
  <img alt="MCP server" src="https://img.shields.io/badge/MCP-server-purple.svg">
</p>

<p align="center">
  <a href="docs/client-config.md">Client config</a> ·
  <a href="docs/schema.md">Schema</a> ·
  <a href="docs/safety.md">Safety model</a> ·
  <a href="examples/README.md">Examples</a> ·
  <a href="CONTRIBUTING.md">Contributing</a> ·
  <a href="https://techaurah.com">TechAurah</a>
</p>

## The problem

Most small service businesses have no CRM. They run their pipeline in a
spreadsheet and an inbox: 56% of US small businesses do not use a
unified CRM, and of those, 39% track customers with spreadsheets and
email ([SMB Group survey for Bigin by Zoho CRM, 2023](https://cdn.zoho.com/news/survey-from-zoho-finds-small-businesses-ready-to-invest-in-crm-solutions.html), vendor-commissioned, n>1,500). The US alone has 36.2 million small businesses ([SBA Office of Advocacy, 2025](https://advocacy.sba.gov/2025/06/30/new-advocacy-report-shows-the-number-of-small-businesses-in-the-u-s-exceeds-36-million/)), and response speed matters: firms that responded to web leads within an hour were about 7 times more likely to qualify them, while 23% never responded at all ([Oldroyd, McElheran and Elkington, HBR, 2011](https://hbr.org/2011/03/the-short-life-of-online-sales-leads)).

When these businesses connect an AI assistant today, they get one of
two bad options: a vendor MCP server that requires the paid CRM they
do not own, or a generic spreadsheet MCP that exposes raw row CRUD, so
the assistant can duplicate a lead, move a stage backwards, or
double-book a slot with nothing stopping it.

**LeadPipe does the pipeline job, with guardrails. It does not send
messages, run campaigns, or replace a CRM for businesses that have
outgrown a spreadsheet.**

## Demo

The demo walkthrough runs the whole product offline against an
in-memory fake client (approval mode, so writes preview first). Real
output, trimmed:

```text
== 1. capture_lead (new lead) ==
{ "ok": true, "lead_id": "LP-2026-00013", "created": true,
  "deduped": false, "stage": "NEW", "score_total": null, "band": null }

== 2. capture_lead again (same contact, deduped) ==
{ "ok": true, "lead_id": "LP-2026-00013", "created": false,
  "deduped": true, "matched_on": "email", "stage": "NEW" }

== 3. score_lead (total computed server-side) ==
{ "ok": true, "lead_id": "LP-2026-00013", "score_total": 85,
  "band": "HOT", "components": { "problem": 18, "fit": 19, ... } }

== 7. book_appointment with confirm=true ==
{ "ok": true, "appointment_id": "fake-event-0007", "created": true, ... }

== 8. book_appointment again (idempotent, no duplicate) ==
{ "ok": true, "appointment_id": "fake-event-0007", "created": false, ... }
```

## Quickstart (5 minutes, zero credentials)

Prerequisites: Python 3.11 or newer. No Google account, no API keys,
no paid services for the demo.

```bash
git clone https://github.com/techaurah/leadpipe-mcp.git
cd leadpipe-mcp
python -m venv .venv && source .venv/bin/activate
pip install -e .
python examples/demo_walkthrough.py
```

Expected result: nine numbered steps print, ending with
`Walkthrough complete`. You have just captured, deduped, scored,
listed, checked, booked, re-booked (no duplicate) and summarised a
pipeline, all offline.

To use it inside an MCP client, register the demo server (Claude
Desktop example, full guide in [docs/client-config.md](docs/client-config.md)):

```json
{
  "mcpServers": {
    "leadpipe": { "command": "leadpipe", "args": ["demo"], "env": {} }
  }
}
```

For real mode you need a Google Sheet, a calendar, and your own Google
service account key. Run `leadpipe bootstrap` once (it creates the
schema and refuses to touch a Sheet whose headers do not match), then
register the server with the env values from `.env.example`.

## What it does

- [x] `capture_lead`: records a lead and deduplicates on normalised email, then phone, before any write ([schema](docs/schema.md))
- [x] `get_lead`: fetches one lead by ID, email or phone, with the score recomputed from components so a hand-edited Sheet cannot fake a total
- [x] `list_hot_leads`: HOT leads (80+) in attention order, booked ones excluded unless asked
- [x] `score_lead`: applies the deterministic 0-100 model; the total is computed server-side and never accepted from the caller ([model](docs/schema.md#scoring-model))
- [x] `update_stage`: moves stages only along the validated transition map; WON is terminal, LOST reactivates only to NURTURE ([map](docs/schema.md#stage-map))
- [x] `check_availability`: free slots intersected with business hours; busy titles are never returned
- [x] `book_appointment`: re-checks availability at call time and uses an idempotency key, so a repeat call returns the existing event instead of double-booking
- [x] `daily_pipeline_summary`: counts by stage and band, hot unbooked leads, today's appointments, overdue next actions
- [x] Write modes: direct, dry-run and approval, with approval the default on real credentials ([safety](docs/safety.md))
- [x] Demo mode: a fake Google client with a 12-lead seed dataset, so everything above runs with no credentials

## Configuration

Environment variables only. Full annotated list in `.env.example`.

| Variable | Required | Purpose |
|---|---|---|
| `LEADPIPE_DEMO` | No | `1` runs the in-memory demo (no Google anything) |
| `LEADPIPE_SHEET_ID` | Real mode | The pipeline Sheet's ID |
| `LEADPIPE_CALENDAR_ID` | Real mode | Calendar to check and book (`primary` allowed) |
| `GOOGLE_APPLICATION_CREDENTIALS` | Real mode | Path to your own service account key file; contents are never logged or returned |
| `LEADPIPE_WRITE_MODE` | No | `direct`, `dry_run`, or `approval` (default: approval, direct in demo) |
| `LEADPIPE_TIMEZONE` | No | IANA timezone for business hours and summaries (default UTC) |
| `LEADPIPE_BUSINESS_HOURS` | No | Default `09:00-17:00`, Monday to Friday |

## Examples

| Example | What it shows | Time | Credentials |
|---|---|---|---|
| [Demo walkthrough](examples/demo_walkthrough.py) | All eight tools end to end on the fake client | About 1 minute | None |
| [Client config](docs/client-config.md) | Claude Desktop and Cursor registration, demo and real mode | About 5 minutes | None for demo |

## Roadmap

- **Now:** v0.1.0, the eight tools, Sheets and Calendar store, demo mode.
- **Next (candidates, each needs its own issue):** cancel and reschedule tools, CSV import through the same dedup path, a `list_leads` filter tool, per-weekday business hours.
- **Later (candidates):** SQLite store behind the same protocol, attendee invitations behind approval mode, a follow-up due-date report.

## Contributing

Read [CONTRIBUTING.md](CONTRIBUTING.md), find a `good first issue`,
and send a PR that links its issue and passes CI. The easiest first
contributions need no Google account: a store backend behind the
existing protocol, a client-config example, or a test for a documented
edge case.

## Community and support

| Channel | Best for |
|---|---|
| GitHub Issues | Bugs and feature requests (actionable work) |
| GitHub Discussions | Questions, ideas, show and tell |
| [SECURITY.md](SECURITY.md) | Vulnerability reports (private, never a public issue) |
| [techaurah.com](https://techaurah.com) | Commercial support and AI engineering engagements |

## License

MIT. See [LICENSE](LICENSE).

## About TechAurah

TechAurah is an AI and software engineering company building AI
products, agents and automation for service businesses, and publishing
the reusable parts as open source. We are available for AI engineering
projects: [techaurah.com](https://techaurah.com).
