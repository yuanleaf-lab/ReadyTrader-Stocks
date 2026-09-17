# Paper-only Streamable HTTP local runbook

1. Use Python 3.12 and a project-local venv. Install requirements.lock.txt and requirements-dev.txt.
2. Configure environment variables explicitly using env.example as a reference. .env is not auto-loaded.
3. Run `python -m pytest -o addopts='' -q` and `python -m pip check`.
4. Launch `python -m app.main` from the repository root. It binds `0.0.0.0:${PORT}`; `PORT` defaults to `8000`.
5. Confirm `GET http://127.0.0.1:8000/health`, then connect an MCP client to `http://127.0.0.1:8000/mcp`.
6. Inspect the twelve-tool allowlist, cash and orders with an MCP client. Do not infer a fill from transport success: require ok=true and status=filled.

No deposit or live mode is available. To reset, run `python -m tools.authorize_paper_reset`
as operator and explicitly authorize the one-use token. Never let an MCP caller
mint its own token. Old cycles remain in SQLite.

On database errors, preserve the DB, WAL and SHM together. Stop the process before
making a filesystem copy, or use SQLite's backup API for a consistent live backup.
Never delete the database to cure a lock or silently fall back to another path.
Legacy schemas fail closed and require a separate, audited migration.

On stale/failed quotes, reject new fills and retry later with the same request ID.
A persisted rejection is final for that ID; a deliberate new attempt requires a new
ID and a new decision. Missing valuation returns an error, never zero equity.
A split-affected holding is blocked; inspect and reconcile before resuming it.

Runtime boundaries: unauthenticated local Streamable HTTP only; no OAuth, public
auth or Railway setup exists here. Linux container execution, deployment
persistence/restart tests and ChatGPT end-to-end validation belong to the next
separately authorized phase.
