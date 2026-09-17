# Paper-only core implementation plan

> Execute the approved user specification in this session with test-driven development and independent review. No commits, pushes, deployment, OAuth or remote transport work.

**Goal:** A local, permanently paper-only MCP with exactly twelve tools and reliable accounting.

**Architecture:** Keep FastMCP tool modules, PaperTradingEngine, RiskGuardian and the yfinance adapter. A single paper service orchestrates trusted quotes and calendar checks; SQLite owns atomic ledger updates and persisted idempotency. All brokerage modules are disabled independently of environment settings.

**Tech stack:** Python 3.12, FastMCP 2.14.1, SQLite, Decimal, yfinance, pandas-market-calendars, pytest.

## Binding scope

- Twelve tools: get_stock_price, get_stock_history, search_symbol, get_portfolio, get_cash_balance, buy, sell, get_orders, get_trade_history, get_performance, get_risk_status, reset_paper_account.
- Only USD US common stocks, regular hours, fresh finite positive reference prices and quantities. No deposit, limits, shorting, leverage, options, crypto or broker credentials.
- One initialization per database; immutable initial capital; reset requires one-use server authorization and archives old sessions. Decimal strings are persisted and returned.
- Atomic cash/position/order/snapshot writes, persistent request idempotency, all failures explicit. Risk uses current marks and prospective holdings; sells reduce risk.
- Defaults for local testing: initial USD 10000, fixed fee USD 0.01 plus 0.0001 of notional, slippage 5 bps, trade cap 10%, symbol cap 25%, gross cap 80%, quote max age 180 seconds. These are configurable server-side, not recommendations.
- Legacy nonempty paper databases fail closed with a migration message; never reinterpret unreliable old accounting.
- No commit/push/deploy; work in new clone branch paper-only-core.

## Tasks and verification

1. Cut startup paths and establish tests. Files: app/main.py, app/core/{config,container}.py, app/tools/*.py, execution/*, app/api_server.py, requirements*.txt, tests/conftest.py. Assert exact tool allowlist and no broker imports; reject live env and disable old entrypoints. Run failing tests before implementations.
2. Atomic ledger. Files: core/paper.py, core/risk.py, core/values.py, tests/test_paper_core.py. Test init/restart, fractions, sells/full exit, invalid quantities, insufficient cash/holdings, fees, slippage, idempotency conflict/replay/restart, rollback, concurrent orders, persisted costs and snapshots. Use BEGIN IMMEDIATE and TEXT Decimal values; no network in write transaction. Fee/cost rounding to 8 decimal USD places; quantities at most 8 decimal places. Inspect hand-computed results.
3. Market and calendar. Files: marketdata/exchange_provider.py, marketdata/calendar.py, marketdata/__init__.py, tests/test_paper_marketdata.py. Interface: StockQuote(symbol, price: Decimal, as_of: aware datetime, fetched_at: aware datetime); ExchangeProvider.fetch_quote(symbol), fetch_ohlcv(symbol,timeframe,limit), search_symbol(query,limit). Validate type via security metadata, USD, US exchange and explicit common-stock quote type; deny ambiguous instruments. Calendar.is_open(datetime) and require_open(datetime). Fail closed for missing/invalid metadata, stale/missing prices, corporate actions. Test offline fixtures including holidays/DST/early close.
4. Orchestration and risk. Files: app/services/paper_trading.py, core/risk.py. Quote held symbols plus order symbol, validate again under transaction, require same account generation and held-symbol set, cap buys based on true equity and prospective exposure, permit liquidation. Normalize failures to {ok:false,error:{code,message}}. Required idempotency key checked before market lookup so completed retries work after hours. No SQL mutation on unknown infrastructure failures.
5. Queries/MCP/lifecycle. Files: app/tools/{market,trading,account}.py, app/main.py, tools/authorize_paper_reset.py. Mark-to-market valuation, weighted cost, realized/unrealized PnL, sampled curve/current and maximum drawdown, cash, paginated orders/trades. Lifecycle sampling on regular sessions without WebSocket. Reset authorization unavailable as an MCP tool.
6. Review and local verification. Files: README.md, app/README.md, docs/TOOLS.md, RUNBOOK.md, env.example, .github/workflows/ci.yml, pyproject.toml, .dockerignore, Dockerfile. Keep local stdio. Archive obsolete tests distinctly, run whole active pytest suite, lint changed runtime, pip check and stdio MCP smoke. Independently review concurrency, idempotency/reset boundaries, metadata validation and exact registration. Report limitations honestly.

## Progress

- Planning: approved design carried forward; fresh clone at 7167c15, clean baseline. No pre-existing user changes.
- Baseline dependencies not installed; only minimal paper dependencies will be installed into .venv (no brokerage SDKs).
