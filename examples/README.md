# Examples

## demo_walkthrough.py

The full demo sequence, runnable offline with zero credentials:

```bash
pip install -e .
python examples/demo_walkthrough.py
```

It runs against the in-memory fake client in approval mode: capture a
lead, capture the same contact again (deduped), score it HOT, list hot
leads, check availability on the seeded calendar, book with a preview
then a confirm, re-book the same slot (no duplicate), and print the
daily pipeline summary. The same sequence is the integration test in
`tests/test_demo_walkthrough.py`.

## Client configuration

Ready-to-paste MCP client entries (Claude Desktop and Cursor, demo and
real mode) live in [docs/client-config.md](../docs/client-config.md).
