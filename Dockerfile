# LeadPipe MCP server, demo mode.
# Runs the server on the built-in fake client with seeded demo data,
# so it starts and answers MCP introspection with zero credentials.
# For real Google Sheets and Calendar access, run without LEADPIPE_DEMO
# and provide credentials as described in docs/client-config.md.
FROM python:3.12-slim

WORKDIR /app
COPY . .
RUN pip install --no-cache-dir .

ENV LEADPIPE_DEMO=1
CMD ["leadpipe", "demo"]
