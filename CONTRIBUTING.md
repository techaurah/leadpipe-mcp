# Contributing to LeadPipe MCP

Thanks for considering a contribution. LeadPipe is built so a first PR
needs no Google account and no MCP expertise: the pure-logic core and
the fake client cover almost everything.

## Dev setup (under 10 minutes)

```bash
git clone https://github.com/techaurah/leadpipe-mcp.git
cd leadpipe-mcp
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pytest
python examples/demo_walkthrough.py
```

If `pytest` is green and the walkthrough completes, your environment is
correct. Nothing in the test suite touches the network.

## Where things live

- `src/leadpipe/scoring.py`, `stages.py`, `models.py`: pure logic
  (scoring, transitions, normalisation). No I/O, fully unit-tested.
- `src/leadpipe/tools/`: thin tool wrappers (validate, call the store
  through the protocol, map results and errors).
- `src/leadpipe/store/`: the store/calendar protocol (`base.py`), the
  Google implementation (`sheets.py`), the in-memory fake (`fake.py`),
  and the schema plus bootstrap (`schema.py`).
- `src/leadpipe/demo_data.py`: the 12-lead demo dataset.

## Good first contributions

- A new store backend behind the existing protocol (SQLite is a named
  v0.2 candidate).
- Client-configuration examples for another MCP client.
- Tests for a documented edge case in scoring, stages, or dedup.
- Documentation fixes and translations.

## Rules

- Open an issue before any scope change. The v0.1 tool set is frozen;
  new tools need their own issue and decision (see the roadmap in the
  README).
- Every PR links an issue (`Closes #...`) and includes test evidence:
  the command you ran and its result.
- Pure-logic changes must come with tests. Behaviour changes must keep
  the demo walkthrough test green: it is the release gate.
- Style: `ruff check`, `ruff format`, and `mypy` must pass (CI runs all
  three plus pytest on Python 3.11 and 3.12).
- Never commit credentials, a real `.env`, or real lead data. Demo data
  only.
- Do not add a tool that sends messages or invitations. v0.1's "sends
  nothing" guarantee is a design feature, not a missing feature.

## Response rhythm

Issues are triaged weekly at minimum. PRs get a first human response
within a few days. If a claimed issue goes quiet for two weeks, we will
unassign it kindly so someone else can pick it up.
