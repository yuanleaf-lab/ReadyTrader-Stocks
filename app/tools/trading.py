"""Only buy, sell and operator-authorized reset are writable MCP tools."""
from pydantic import StrictFloat, StrictStr


def register_trading_tools(mcp, service):
    @mcp.tool(annotations={'readOnlyHint': False, 'destructiveHint': False})
    def buy(symbol: str, quantity: StrictStr | StrictFloat, client_order_id: str, rationale: str = '') -> dict:
        """Buy fractional shares of an approved USD US common stock with simulated cash.

        quantity is SHARES, not dollars. Use decimal strings for exact precision.
        Reuse client_order_id for retries; never change its arguments. Server sets
        price, fees, slippage and risk limits. Regular hours only; no real brokerage exists.
        """
        return service().buy(symbol, quantity, client_order_id, rationale)

    @mcp.tool(annotations={'readOnlyHint': False, 'destructiveHint': False})
    def sell(symbol: str, quantity: StrictStr | StrictFloat, client_order_id: str, rationale: str = '') -> dict:
        """Sell owned fractional shares for simulated USD. quantity is SHARES.

        Reuse client_order_id for retries. Never shorts; fees and slippage are server-controlled. Regular hours only.
        """
        return service().sell(symbol, quantity, client_order_id, rationale)

    @mcp.tool(annotations={'readOnlyHint': False, 'destructiveHint': True})
    def reset_paper_account(authorization: str) -> dict:
        """Archive this simulation and restore its ORIGINAL principal.

        Requires a one-use authorization issued manually by the server operator;
        cannot deposit or choose capital. Never request or fabricate authorization autonomously.
        """
        return service().reset_paper_account(authorization)
