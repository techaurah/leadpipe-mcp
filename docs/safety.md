# Safety model

LeadPipe exists because pointing an AI assistant at raw spreadsheet
CRUD is unsafe: nothing stops it duplicating a lead, moving a stage
backwards, or double-booking a slot. These are the guardrails, and
where they live in the code.

## Write modes

Set with `LEADPIPE_WRITE_MODE`. A per-call `dry_run: true` can make any
call drier; no call can make itself less safe than the configured mode.

| Mode | Behaviour |
|---|---|
| direct | Writes execute immediately and are audit-logged as `direct`. |
| dry_run | All validation, dedup, transition and availability checks run against current data. The tool returns the exact change it would make under a `preview` key and writes nothing except its AuditLog entry (mode `dry_run`). |
| approval | A write without `confirm` behaves like a dry run and returns an `APPROVAL_REQUIRED` result with the preview. A human reviews it in the assistant client; repeating the call with `confirm: true` executes. Default with real credentials. |

Demo mode defaults to `direct` because its data is disposable. The demo
walkthrough uses approval mode so you can see the preview flow.

Mode enforcement lives in one place (`tools/__init__.py`,
`resolve_write_mode`) and the test suite covers every writing tool in
every mode (`tests/test_write_modes.py`).

## The guardrails, tool by tool

- capture_lead deduplicates on normalised email, then phone, before
  any write. A duplicate never creates a row, never changes stage or
  score, and only fills empty fields.
- score_lead computes the total server-side from the eight validated
  components. A caller-supplied total is rejected as an unknown field.
- update_stage validates against the transition map. WON is terminal;
  LOST can only reactivate to NURTURE.
- book_appointment re-checks free/busy at call time (an earlier
  availability answer is never trusted) and carries an idempotency key
  per lead and slot, so a repeat call returns the existing event
  instead of creating a duplicate.
- check_availability returns busy times with titles always null. An
  assistant needs to know when you are busy, not what you are doing.

## What v0.1 can never do

- Send anything: no email, SMS, WhatsApp, DM, or calendar invitation.
  Booked events are created on the business calendar with no attendees.
- Delete anything: no tool deletes a lead, an event, or an audit row.
- Read anything outside the one configured Sheet and calendar.
- Make an LLM call. Scoring judgements come from the caller; the
  arithmetic and every guardrail are deterministic code.

## Credentials and scopes

Configuration is environment variables only. The Google credentials
file is referenced by path; its contents are never logged, returned by
a tool, or written to the Sheet. Only two capabilities are requested:
the Sheets API (for the one pipeline Sheet) and Calendar events, plus
read-only free/busy metadata. No Gmail, no Drive-wide access, no
contacts, no admin scopes.

Each user supplies their own Google Cloud credentials (a service
account key) in v0.1. That keeps the project outside Google's
app-verification process and keeps every business's data in an account
that business controls.
