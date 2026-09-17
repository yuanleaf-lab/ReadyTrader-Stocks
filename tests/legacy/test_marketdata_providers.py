from unittest.mock import MagicMock

import pytest

from marketdata.providers import IngestMarketDataProvider, StockMarketDataProvider, _normalize_ticker_shape, _to_timestamp_ms
from marketdata.store import InMemoryMarketDataStore


@pytest.mark.asyncio
async def test_stock_provider_conformance():
    exchange_mock = MagicMock()
    exchange_mock.fetch_ticker.return_value = {
        "symbol": "AAPL",
        "last": 150.0,
        "bid": 149.9,
        "ask": 150.1,
        "timestamp": 1234567890000,
        "exchange_id": "yfinance"
    }
    exchange_mock.fetch_ohlcv.return_value = [[1,2,3,4,5,6]]
    exchange_mock.get_exchange_name.return_value = "yfinance"
    exchange_mock.get_marketdata_capabilities.return_value = {"status": "ok"}
    
    provider = StockMarketDataProvider(exchange_provider=exchange_mock)
    
    # Ticker
    ticker = await provider.fetch_ticker("AAPL")
    assert ticker["symbol"] == "AAPL"
    assert ticker["last"] == 150.0
    assert ticker["source"] == "yfinance"

    # OHLCV
    ohlcv = await provider.fetch_ohlcv("AAPL", "1h", 100)
    assert len(ohlcv) == 1
    assert ohlcv[0][0] == 1

    # Status
    assert provider.status()["status"] == "ok"

@pytest.mark.asyncio
async def test_ingest_provider():
    store = InMemoryMarketDataStore()
    provider = IngestMarketDataProvider(store=store)
    
    # Empty
    with pytest.raises(ValueError):
        await provider.fetch_ticker("AAPL")
        
    with pytest.raises(ValueError):
        await provider.fetch_ohlcv("AAPL", "1h", 100)
        
    # Populate
    store.put_ticker(symbol="AAPL", last=200.0, bid=199.0, ask=201.0, timestamp_ms=1000, source="test", ttl_sec=60)
    store.put_ohlcv(symbol="AAPL", timeframe="1h", limit=100, ohlcv=[[1,2,3,4,5,6]], ttl_sec=60)
    
    # Now fetch
    ticker = await provider.fetch_ticker("AAPL")
    assert ticker["last"] == 200.0
    assert ticker["source"] == "test"
    
    ohlcv = await provider.fetch_ohlcv("AAPL", "1h", 100)
    assert len(ohlcv) == 1

def test_helpers():
    # _to_timestamp_ms
    assert _to_timestamp_ms({"timestamp": 123}) == 123
    assert _to_timestamp_ms({"timestamp_ms": 456}) == 456
    assert _to_timestamp_ms({"timestamp": "abc"}) is None
    
    # _normalize_ticker_shape
    res = _normalize_ticker_shape(symbol=" aapl ", last=100, bid=None, ask=None, timestamp_ms=None, source="test")
    assert res["symbol"] == "AAPL"
    assert res["last"] == 100.0
