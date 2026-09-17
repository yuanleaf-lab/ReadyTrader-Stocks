# Local paper application

- `main.py`: exactly twelve FastMCP tools over Streamable HTTP at `/mcp`, with `/health`, lazy account startup and sampling lifecycle.
- `core/config.py`: server-only paper parameters; live/brokerage configuration rejected.
- `core/container.py`: paper engine, yfinance provider and paper service only.
- `services/paper_trading.py`: market eligibility, calendar, quote collection and account queries.
- `tools/market.py`, `tools/trading.py`, `tools/account.py`: fixed public tool contract.
- `api_server.py`, `tools/intelligence.py`, `tools/research.py`: disabled legacy entrypoints.

No OAuth, Railway, dashboard or broker service runs in this phase.
