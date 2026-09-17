# Local paper tool reference

| Tool | Inputs | Result |
| --- | --- | --- |
| get_stock_price | symbol | Reference price, actual source time, fetch time, staleness |
| get_stock_history | symbol, timeframe=1d, limit=100 | Unadjusted OHLCV with ISO timestamps |
| search_symbol | query, limit=10 | Eligible ordinary stocks only |
| get_portfolio | none | Cash, holdings, cost basis, reference equity, unrealized/realized PnL |
| get_cash_balance | none | USD cash, original capital, cycle |
| buy | symbol, quantity, client_order_id, rationale='' | Filled paper market order or explicit failure |
| sell | symbol, quantity, client_order_id, rationale='' | Owned-share sale or explicit failure |
| get_orders | limit=100, offset=0, generation=null | Filled and rejected orders; optional archived cycle |
| get_trade_history | limit=100, offset=0, generation=null | Filled orders with fees/slippage/rationale |
| get_performance | curve_limit=500 | Latest complete sampled equity/PnL, max/current drawdown and bounded curve |
| get_risk_status | none | Real-valued allocation, limits, market-open and stale status |
| reset_paper_account | authorization | New cycle at unchanged original principal |

Quantity is shares (decimal string preferred), never dollar notional. Cash and
accounting values return decimal strings. Buy/sell reject invalid or more-than-eight
place quantities, old quotes, non-regular sessions, unsupported securities, excess
positions and insufficient fee-inclusive cash. AI cannot choose prices, side,
fees, policy, account ID, initial principal or reset authorization issuance.

Order page size is 1..500, curve size 1..1000. Percentage fields are fractions
(e.g. 0.10 means 10%). All application failures return `ok:false`; inspect that
field before describing a trade as filled. Reuse request IDs after uncertain results.
