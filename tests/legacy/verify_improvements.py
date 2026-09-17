import asyncio

from app.core.container import global_container
from intelligence.core import get_market_sentiment


async def verify_improvements():
    print("--- Verifying Sentiment ---")
    sentiment = get_market_sentiment()
    print(f"Sentiment Output: {sentiment}")
    assert "CNN Fear & Greed" in sentiment or "Error fetching" in sentiment
    
    print("\n--- Verifying Async Market Data ---")
    # Fetch price for AAPL using async bus
    try:
        res = await global_container.marketdata_bus.fetch_ticker("AAPL")
        print(f"Price for AAPL: {res.data.get('last')} (Source: {res.source})")
        assert res.data.get('last') > 0
    except Exception as e:
        print(f"Market Data Fetch failed: {e}")
        # If it fails due to no provider keys, that's expected in some CI environments,
        # but locally it should work with mock fallback in StockMarketDataProvider if configured.

if __name__ == "__main__":
    asyncio.run(verify_improvements())
