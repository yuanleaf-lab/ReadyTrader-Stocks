"""Account queries expose no funding or configuration mutation."""


def register_account_tools(mcp, service):
    @mcp.tool(annotations={'readOnlyHint': True})
    def get_portfolio() -> dict:
        """Paper USD cash, fractional holdings, weighted costs and reference-price equity. May report stale marks."""
        return service().get_portfolio()

    @mcp.tool(annotations={'readOnlyHint': True})
    def get_cash_balance() -> dict:
        """Available simulated USD cash and the immutable initial principal. No real funds."""
        return service().get_cash_balance()

    @mcp.tool(annotations={'readOnlyHint': True})
    def get_orders(limit: int = 100, offset: int = 0, generation: int | None = None) -> dict:
        """Paper market orders including explicit rejections. Optionally inspect an archived account cycle."""
        return service().get_orders(limit, offset, generation)

    @mcp.tool(annotations={'readOnlyHint': True})
    def get_trade_history(limit: int = 100, offset: int = 0, generation: int | None = None) -> dict:
        """Completed paper fills with rationale, fees, slippage and realized PnL. No limit orders."""
        return service().get_trade_history(limit, offset, generation)

    @mcp.tool(annotations={'readOnlyHint': True})
    def get_performance(curve_limit: int = 500) -> dict:
        """Realized/unrealized paper PnL, reference-price equity and sampled maximum drawdown; excludes dividends."""
        return service().get_performance(curve_limit)

    @mcp.tool(annotations={'readOnlyHint': True})
    def get_risk_status() -> dict:
        """Current paper exposure, server limits, quote staleness and US regular-session availability."""
        return service().get_risk_status()
