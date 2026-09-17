# ReadyTrader Paper Core

Streamable HTTP MCP for simulated USD US common-stock trading. There is no live mode,
broker connection, deposit, limit order, short, margin, option or crypto tool.
All orders use virtual funds. The local endpoint is `/mcp`; Railway, OAuth and
ChatGPT setup remain outside this implementation phase.

## Local setup

Python 3.12:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.lock.txt -r requirements-dev.txt
.\.venv\Scripts\python.exe -m pytest -o addopts='' -q
.\.venv\Scripts\python.exe -m app.main
```

The server listens on `0.0.0.0:${PORT}`, defaulting to port `8000`; use
`http://127.0.0.1:8000/mcp` locally and `GET /health` for a non-authenticated
service/database readiness check. `PORT` must be an integer from 1 to 65535.

Set variables explicitly in the launching process (see `env.example`). An `.env`
file is not automatically loaded. Do not supply brokerage credentials. Live-mode
or brokerage variables cause startup failure; they cannot change this build into
real trading. Runtime imports do not create an account; service startup does.

## Server policy defaults

| Setting | Default |
| --- | --- |
| Database | `data/paper.db` |
| Initial virtual USD | 10000, used only on FIRST creation |
| Fixed execution fee | USD 0.01 |
| Proportional fee | 0.0001 of fill notional (0.01%) |
| Adverse slippage | 5 basis points (0.05%) |
| Maximum buy debit / pre-trade equity | 10% |
| Maximum single-stock value / post-trade equity | 25% |
| Maximum total holdings / post-trade equity | 80% |
| Maximum execution quote age | 180 seconds |
| Operator-reviewed symbols for ambiguous metadata | AAPL, MSFT |

These are simulator defaults, not investment recommendations. All policy is
server-controlled. Tools cannot override prices, fees, limits or principal.
Market metadata must still be USD/EQUITY/on a supported US exchange and must not
identify a derivative, preferred share, depositary receipt or fund. The approved
symbol list does NOT override conflicting metadata. Explicit common-stock
metadata may qualify other symbols; ambiguous instruments require operator
review. This intentionally does not claim all Yahoo EQUITY instruments are common
stocks. Search filters by the same rules.

## Tool contract

Exactly twelve tools are registered: `get_stock_price`, `get_stock_history`,
`search_symbol`, `get_portfolio`, `get_cash_balance`, `buy`, `sell`, `get_orders`,
`get_trade_history`, `get_performance`, `get_risk_status`, `reset_paper_account`.
See `docs/TOOLS.md` for inputs and behavior. All success responses contain
`ok: true, data: ...`; all application failures contain `ok: false, error: ...`.
A rejected order is never reported as a fill. MCP input-schema validation may
also return a protocol tool error before the function runs.

`quantity` means SHARES, supports up to 8 decimal places, and must be positive
and finite. Decimal strings are preferred. Money, costs and quantities are stored
as exact canonical decimal TEXT in SQLite, never binary floating-point balances.
Ledger values use 8 decimal places and round half-even. Tiny orders whose notional
rounds to zero are rejected. Outputs return decimal strings.

Every buy/sell requires `client_order_id`. Retry the same operation with exactly
the same ID and arguments; a changed payload with that ID is rejected. Filled and
persisted rejected requests replay their original result, including across restart
and reset. A replay after reset does not place an order in the new account cycle.
Infrastructure failures may require retry with the SAME ID; never blindly use a
new ID after a timeout. Cash/position/order/equity writes are one SQLite transaction.

## Accounting and risk

Buy fill = reference x (1 + slippage_bps/10000). Sell fill uses minus.
Fee = fixed fee + fill notional x fee_rate. Buy cash debit includes fees; sell
cash credit deducts fees. Slippage is recorded separately for analysis but is
already embedded in the fill price, never charged again.

Weighted-average remaining cost includes buy fees. Partial sells remove their
proportionate cost; the final sell removes all remaining cost. Realized PnL is
net sale proceeds minus removed cost. Unrealized PnL is reference market value
minus remaining cost. Equity is cash plus current reference market values.

Buy limits use freshly valued equity, prospective cumulative symbol holdings and
all holdings, including fees/slippage. Sells are not blocked by buy allocation
limits; cash and owned quantity constraints always apply. Risk and balance checks
are repeated inside the SQLite write transaction. There is no margin credit.

Snapshots are recorded only after a completed transaction, never between its
cash and holdings updates. Queries with fresh complete marks also record snapshots;
a local background sampler runs every 300 seconds during regular sessions while
the MCP process is alive. Maximum drawdown scans all persisted observations, even
when only the last bounded portion of the curve is returned. Current drawdown is
separate. Missing/stale observations are not fabricated or zero-filled. No sample
is guaranteed at the exact closing auction; gaps across downtime remain gaps.

## Account lifecycle

Initial capital is persisted once. Changing PAPER_INITIAL_CASH, restarting or
upgrading never tops up an existing account. Reset restores the persisted original
principal in a new cycle, retaining the old orders and curve. Reset takes no amount.

Run `python -m tools.authorize_paper_reset` locally as the server operator, type the
explicit authorization phrase, then pass its one-use five-minute token to the reset
tool. The token is stored hashed, bound to the account cycle and consumed atomically.
There is no MCP tool that can obtain a reset authorization. Reset archives all past
account cycles and does not erase global client_order_id history.

Old upstream SQLite schemas are rejected without destructive migration. Preserve
old databases separately and start with a new path, or implement and verify an
explicit migration; old incomplete PnL cannot be trusted or silently reconstructed.

## Simulation limits

- yfinance supplies minute reference data, not guaranteed live bid/ask or liquidity.
  Bad, missing, stale or ambiguous data rejects execution. No executed-price fallback.
- NYSE calendar regular hours include holidays, weekends, DST and early closes.
  Calendar availability is not a full individual-stock halt feed.
- Fills are all-or-nothing at the configured reference/slippage model, with immediate
  simulated reuse of sale proceeds. No order book, partial fills or T+1 settlement.
- Splits detected since acquisition block valuation and trading until reconciliation;
  automatic corporate-action adjustment is not implemented. Dividends are excluded.
- Closed-session portfolio queries can display explicitly stale reference marks;
  they do not add fake fresh curve points. Missing marks return failure.
- This phase is a local single-account Streamable HTTP service. Do not expose it
  publicly without the next phase's authentication and deployment verification.

## Verification and archived code

The active tests are the paper suite plus retained common/audit utility tests.
`tests/legacy` holds upstream tests for removed features and superseded contracts;
it is explicitly excluded, not presented as passing coverage. Legacy frontend,
strategy/intelligence research and examples remain reference source only; the MCP
does not load them. Brokerage modules and the old Web API/WebSocket entrypoints
are permanent failure stubs, with no brokerage SDK in the runtime dependency set.
The local Docker recipe packages only the paper runtime; deployment is not performed.
