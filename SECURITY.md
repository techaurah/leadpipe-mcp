# Security Policy

## Reporting a vulnerability

Please do not open a public issue for a security problem.

- Preferred: use GitHub's private vulnerability reporting on this
  repository (Security tab, "Report a vulnerability").
- Or email the maintainers via the contact route at
  https://techaurah.com and put "LeadPipe security" in the subject.

You can expect an acknowledgement within a few days. Please give us a
reasonable window to fix and release before disclosing publicly.

## Supported versions

| Version | Supported |
|---|---|
| 0.1.x | Yes |
| Earlier | No (0.1.0 is the first release) |

## Credential handling rules

- LeadPipe reads Google credentials by file path only
  (`GOOGLE_APPLICATION_CREDENTIALS`). Credential contents are never
  logged, returned by a tool, or written to the Sheet.
- Only two Google API capabilities are requested: the Sheets API for
  the one pipeline Sheet, and Calendar events plus read-only free/busy
  metadata. No Gmail, no Drive-wide, no contacts, no admin scopes.
- The server only ever opens the Sheet and calendar named in its
  configuration. Share exactly those with the service account, nothing
  else.
- `.env` files and key files are gitignored. If you believe a credential
  was committed to a fork, revoke it in Google Cloud first, then tell
  us.

## What the server can never do in v0.1

By design there is no code path that sends email, SMS, or messages,
invites calendar attendees, or deletes a lead, an event, or an audit
row. Reports that find a way around the write-mode guardrails
(dry-run or approval executing a write) are treated as vulnerabilities.
