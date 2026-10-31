# AGENTS.md

Instructions for AI coding agents (and humans skimming) working in this
repository.

## Project in one paragraph

LeadPipe MCP is a Python MCP server that gives an AI assistant eight
guardrailed pipeline operations over a Google Sheet and Calendar, for
small businesses with no CRM. The design contract lives in the README
and `docs/`; the frozen v0.1 scope is eight tools and a "sends nothing
to anyone" guarantee.

## Layout

- `src/leadpipe/` package: `server.py` (FastMCP entry, lazy SDK import),
  `config.py`, `models.py`, `errors.py`, `scoring.py`, `stages.py`,
  `demo_data.py`, `bootstrap.py`
- `src/leadpipe/tools/` one module per tool group; `tools/__init__.py`
  holds the context object, write-mode enforcement, audit helper, and
  the dispatch registry
- `src/leadpipe/store/` `base.py` protocols, `sheets.py` Google
  implementation, `fake.py` in-memory implementation, `schema.py`
  headers and bootstrap
- `tests/` mirrors the tools; all tests run against the fake

## Commands

```bash
pip install -e ".[dev]"
pytest                        # full suite, offline
ruff check . && ruff format --check .
mypy src/leadpipe
python examples/demo_walkthrough.py   # end-to-end demo, offline
```

## Conventions

- Pure logic (scoring, transitions, normalisation, keys) takes no I/O
  and must be unit-tested. Tool wrappers stay thin.
- The error-code set in `errors.py` is closed; adding a code is a spec
  change, not a drive-by edit.
- Scores are computed server-side only. Never accept a total from a
  caller.
- Write modes are enforced in `tools/__init__.py` (`resolve_write_mode`
  plus the per-tool guard). A per-call flag may only make a call drier.
- No tool may send a message, invite an attendee, or delete anything.
- Type hints on all public functions. No credentials, real Sheet IDs,
  or real lead data in code, tests, or examples.
