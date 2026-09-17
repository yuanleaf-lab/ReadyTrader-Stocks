"""Three bounded yfinance reference-data tools, not executable user-supplied prices."""
from core.values import PaperError, aware


def register_market_tools(mcp, service):
    @mcp.tool(annotations={'readOnlyHint': True})
    def get_stock_price(symbol: str) -> dict:
        """Latest available regular-session reference price, not guaranteed live bid/ask or an executable quote."""
        def read():
            s = service()
            try:
                q = s.provider.fetch_quote(symbol)
            except ValueError:
                raise
            except Exception as exc:
                raise PaperError('market_data_unavailable', 'Validated market data is unavailable; retry later.') from exc
            age = (aware(s.engine.clock())-aware(q.as_of)).total_seconds()
            return {'symbol': q.symbol, 'currency': 'USD', 'reference_price': str(q.price),
                    'as_of': aware(q.as_of).isoformat(), 'fetched_at': aware(q.fetched_at).isoformat(),
                    'age_seconds': age, 'stale': age > s.engine.quote_max_age,
                    'source': 'yfinance', 'price_kind': 'regular-session minute reference'}
        return service()._read(read)

    @mcp.tool(annotations={'readOnlyHint': True})
    def get_stock_history(symbol: str, timeframe: str = '1d', limit: int = 100) -> dict:
        """Bounded unadjusted OHLCV reference history for an eligible US common stock; no strategy execution."""
        return service()._read(lambda: {'symbol': symbol, 'timeframe': timeframe,
            'history': service().provider.fetch_ohlcv(symbol, timeframe, limit)})

    @mcp.tool(annotations={'readOnlyHint': True})
    def search_symbol(query: str, limit: int = 10) -> dict:
        """Find eligible USD US ordinary stocks. Does not permit funds, derivatives or change approved symbols."""
        return service()._read(lambda: {'results': service().provider.search_symbol(query, limit)})
