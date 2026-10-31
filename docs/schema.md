# Sheet schema and pipeline reference

LeadPipe stores everything in one Google Sheet with three tabs. Column
order is part of the contract: the server addresses columns by header
name and refuses to run against a tab whose headers do not match
exactly (`SCHEMA_MISMATCH`). Bootstrap creates this schema; it never
rewrites an existing tab to fit.

## Tab: Leads

One row per lead. Header row 1, data from row 2.

| Col | Header | Notes |
|---|---|---|
| A | lead_id | `LP-YYYY-NNNNN`, immutable, never reused |
| B | created_at | ISO 8601 UTC |
| C | updated_at | ISO 8601 UTC |
| D | name | |
| E | email | Normalised lowercase, empty if absent |
| F | phone | Normalised (spaces/dashes/brackets stripped, leading 00 becomes +) |
| G | company | |
| H | source | website, instagram, facebook, whatsapp, email, referral, call, walk_in, other |
| I | service_interest | |
| J | location | |
| K | problem_notes | Free text: the stated problem |
| L-S | score_problem, score_fit, score_value, score_size, score_pay, score_access, score_urgency, score_activity | The eight scoring components, empty until scored |
| T | score_total | 0-100, computed by the server only |
| U | band | HOT, WARM, NURTURE, LOW, empty until scored |
| V | stage | See the stage map below |
| W | owner | Free text, `unassigned` at capture |
| X | next_action | |
| Y | next_action_date | YYYY-MM-DD, empty if none |
| Z | appointment_id | Calendar event ID, empty if none |
| AA | appointment_start | ISO 8601 UTC, empty if none |
| AB | appointment_status | confirmed, cancelled, or empty |
| AC | last_contact_at | ISO 8601 UTC, empty if never |

## Tab: AuditLog

Append-only. The server never edits or deletes rows here.

| Header | Notes |
|---|---|
| timestamp | ISO 8601 UTC |
| action | Tool name (capture_lead, score_lead, update_stage, book_appointment) |
| lead_id | The affected lead |
| detail | JSON string of the change (from/to values, matched_on, totals) |
| mode | direct, dry_run, or approval |
| actor | `leadpipe-mcp` in v0.1 |

Dry runs are logged here with mode `dry_run` and change nothing else.
Stage history is not stored on the lead row; it is reconstructed from
this log.

## Tab: Meta

Key/value pairs: `schema_version` (1), `next_lead_seq` (the next lead
sequence number to issue), `created_by`, `created_at`.

## Scoring model

Eight caller-supplied judgements, summed by the server. The total is
never accepted as an input.

| Component | Range | What it measures |
|---|---|---|
| problem | 0-20 | A clear, stated problem the business can solve |
| fit | 0-20 | Service fit with what the business sells |
| value | 0-15 | Potential value of the engagement |
| size | 0-10 | Business size and capacity to use the service |
| pay | 0-10 | Signals of ability to pay |
| access | 0-10 | Access to the decision maker |
| urgency | 0-10 | Time pressure to act |
| activity | 0-5 | Recent activity and responsiveness |

Bands: HOT 80-100, WARM 65-79, NURTURE 50-64, LOW below 50. Reads
recompute the total and band from components, so a hand-edited Sheet
cannot produce an inconsistent total.

## Stage map

Stages: NEW, CONTACTED, QUALIFIED, NURTURE, DISCOVERY, BOOKED,
PROPOSAL, NEGOTIATION, WON, LOST.

| From | May move to |
|---|---|
| NEW | CONTACTED, QUALIFIED, NURTURE, LOST |
| CONTACTED | QUALIFIED, NURTURE, DISCOVERY, LOST |
| QUALIFIED | DISCOVERY, BOOKED, NURTURE, LOST |
| NURTURE | CONTACTED, QUALIFIED, LOST |
| DISCOVERY | BOOKED, PROPOSAL, NURTURE, LOST |
| BOOKED | DISCOVERY, PROPOSAL, LOST |
| PROPOSAL | NEGOTIATION, BOOKED, LOST |
| NEGOTIATION | WON, PROPOSAL, LOST |
| WON | (terminal) |
| LOST | NURTURE (reactivation only) |

Any pair not listed is rejected with `STAGE_TRANSITION_INVALID`.
Moving to the current stage is a successful no-op.
