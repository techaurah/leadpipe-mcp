# Roadmap: LeadPipe MCP

Where LeadPipe MCP is going after v0.1.0. This is a plan, not a
promise: items land when they are built, tested, and reviewed, in
roughly this order.

## What v0.2 adds

- **Live Google smoke test results:** the Sheets and Calendar store
  is complete code, exercised so far only against the fake store.
  v0.2 runs it against a real Google account end to end and
  publishes what broke and what changed.
- **SQLite store option:** a local SQLite backend behind the same
  store protocol, for businesses that want the pipeline without a
  Google Sheet.
- Cancel and reschedule tools, on the same guardrails as booking.
- CSV import through the same dedup path as `capture_lead`.

## Deliberately out of scope

- **Not a CRM.** No contact management suites, marketing campaigns,
  or reporting dashboards; the Sheet stays the system of record.
- **It sends nothing to anyone.** No email, SMS, or WhatsApp sending
  to leads; LeadPipe writes pipeline data, humans and other tools
  do the talking.
- **No hosted service.** It runs in your own MCP client, on your
  own Google account. There is no TechAurah server in the loop.

## How priorities are set

Priorities are set from GitHub issues and Discussions: open an
issue for concrete, actionable work, and start a discussion for
ideas and questions. Items with a real user blocked on them move
first.
