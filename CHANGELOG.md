# Changelog

All notable changes to this project are documented here.
The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Fixed

- Duplicate lead IDs when `capture_lead` calls ran concurrently on
  one shared store. Capture read the `next_lead_seq` counter, appended
  the lead, then wrote the counter back, and that read-modify-write
  was not atomic, so two captures running at the same time could be
  handed the same ID. Sequence allocation now lives in the store
  layer (`allocate_lead_seq`), which reads and advances the counter
  under a lock, and capture takes its ID from that call. For the
  Google Sheets backend the lock serialises allocation inside the
  server process, which is how the server runs. Found by the L7
  stress probe in `benchmarks/`; regression coverage in
  `tests/test_capture_concurrency.py`.

### Added

- MCP tool annotations on all eight tools (`readOnlyHint`,
  `destructiveHint`, `idempotentHint`, `openWorldHint`), closing the
  gap flagged by the M8ven listing; covered by
  `tests/test_tool_annotations.py`.

## [0.1.0] - 2026-10-31

### Added

- MCP server (official Python SDK, FastMCP, stdio) with eight tools:
  `capture_lead`, `get_lead`, `list_hot_leads`, `score_lead`,
  `update_stage`, `check_availability`, `book_appointment`,
  `daily_pipeline_summary`.
- Google Sheets store with a fixed three-tab schema (Leads, AuditLog,
  Meta) and a bootstrap command that creates or validates it and refuses
  to run against mismatched headers.
- Deterministic 0-100 scoring model computed server-side (components are
  caller judgements; a caller-supplied total is never accepted), with
  HOT / WARM / NURTURE / LOW bands.
- Validated stage transition map: illegal moves are rejected, same-stage
  moves are a successful no-op, LOST can only reactivate to NURTURE.
- Capture deduplication on normalised email, then phone, before any
  write; duplicates merge only into empty fields and never change stage
  or score.
- Booking safety: availability re-checked at call time, idempotency key
  per lead and slot so repeat bookings return the existing event, and
  no attendees on any event (v0.1 sends nothing to anyone).
- Three write modes: direct, dry-run (preview plus an audit entry, no
  other writes), and approval (preview first, execute only with
  `confirm=true`). Approval is the default with real credentials.
- Demo mode: an in-memory fake Google client with a 12-lead seed dataset
  and a seeded calendar, so the full walkthrough runs with zero
  credentials. The walkthrough is also the integration test.
- pytest suite covering scoring boundaries, every allowed stage
  transition, dedup cases, availability and booking, write modes,
  summary counts, and bootstrap behaviour.
