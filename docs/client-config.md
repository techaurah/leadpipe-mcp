# Client configuration

LeadPipe is a standard MCP server over stdio. Any MCP-capable client
can run it. Each example is shown twice: demo mode (zero credentials,
in-memory sample data) and real mode (your Google Sheet and Calendar).

Install first:

```bash
pip install leadpipe-mcp        # once published
# or from a clone:
pip install -e ".[google]"      # google extra is needed for real mode
```

## Claude Desktop

Edit `claude_desktop_config.json` (Settings, Developer, Edit Config).

Demo mode:

```json
{
  "mcpServers": {
    "leadpipe": {
      "command": "leadpipe",
      "args": ["demo"],
      "env": {}
    }
  }
}
```

Real mode:

```json
{
  "mcpServers": {
    "leadpipe": {
      "command": "leadpipe",
      "args": [],
      "env": {
        "LEADPIPE_SHEET_ID": "your-sheet-id-here",
        "LEADPIPE_CALENDAR_ID": "primary",
        "GOOGLE_APPLICATION_CREDENTIALS": "/path/to/your-service-account-key.json",
        "LEADPIPE_WRITE_MODE": "approval",
        "LEADPIPE_TIMEZONE": "America/New_York"
      }
    }
  }
}
```

## Cursor

Create or edit `.cursor/mcp.json` in your workspace (or the global
`~/.cursor/mcp.json`). The server entries use the same shape:

Demo mode:

```json
{
  "mcpServers": {
    "leadpipe": {
      "command": "leadpipe",
      "args": ["demo"],
      "env": {}
    }
  }
}
```

Real mode: use the real-mode `env` block from the Claude Desktop example
above, unchanged.

## Before real mode: bootstrap once

Real mode needs the Sheet schema in place. Create an empty Google
Sheet, share it with your service account's email (Editor), then run:

```bash
export LEADPIPE_SHEET_ID=your-sheet-id-here
export LEADPIPE_CALENDAR_ID=primary
export GOOGLE_APPLICATION_CREDENTIALS=/path/to/your-service-account-key.json
leadpipe bootstrap
```

Bootstrap creates the `Leads`, `AuditLog` and `Meta` tabs with the
exact schema headers and prints the Sheet URL. It is safe to re-run: it
validates existing tabs and changes nothing when they already match. If
a tab's headers do not match, it aborts with `SCHEMA_MISMATCH` and
changes nothing.

## Running from source without installing

Replace `"command": "leadpipe"` with your Python and module entry:

```json
{
  "command": "python",
  "args": ["-m", "leadpipe.server"],
  "env": { "PYTHONPATH": "/path/to/leadpipe-mcp/src", "LEADPIPE_DEMO": "1" }
}
```
