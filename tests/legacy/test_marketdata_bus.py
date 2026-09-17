import json

import pytest

from marketdata.bus import MarketDataBus


class FakeProvider:
    def __init__(self, provider_id: str, ticker: dict | None = None, err: Exception | None = None):
        self.provider_id = provider_id
        self._ticker = ticker
        self._err = err

    async def fetch_ticker(self, symbol: str) -> dict:
        if self._err is not None:
            raise self._err
        return dict(self._ticker or {})

    async def fetch_ohlcv(self, symbol: str, timeframe: str, limit: int):
        raise ValueError("no ohlcv")

    def status(self):
        return {"provider_id": self.provider_id}


@pytest.mark.asyncio
async def test_bus_prefers_fresh_higher_priority(monkeypatch):
    # Make ws stale and ingest fresh: should pick ingest if ws is stale.
    now = 1_000_000
    monkeypatch.setattr("marketdata.bus._now_ms", lambda: now)
    monkeypatch.setenv("MARKETDATA_PROVIDER_PRIORITY_JSON", json.dumps({"exchange_ws": 0, "ingest": 1, "ccxt_rest": 2}))
    monkeypatch.setenv("MARKETDATA_MAX_AGE_MS_EXCHANGE_WS", "100")
    monkeypatch.setenv("MARKETDATA_MAX_AGE_MS_INGEST", "1000")

    ws = FakeProvider("exchange_ws", {"symbol": "AAPL", "last": 10, "timestamp_ms": now - 500})
    ingest = FakeProvider("ingest", {"symbol": "AAPL", "last": 11, "timestamp_ms": now - 10})
    rest = FakeProvider("ccxt_rest", {"symbol": "AAPL", "last": 12, "timestamp_ms": now - 5})

    bus = MarketDataBus([ws, ingest, rest])
    res = await bus.fetch_ticker("AAPL")
    assert res.source == "ingest"
    assert res.meta["stale"] is False


@pytest.mark.asyncio
async def test_bus_falls_back_when_provider_errors(monkeypatch):
    now = 1_000_000
    monkeypatch.setattr("marketdata.bus._now_ms", lambda: now)
    monkeypatch.setenv("MARKETDATA_PROVIDER_PRIORITY_JSON", json.dumps({"exchange_ws": 0, "ingest": 1}))
    ws = FakeProvider("exchange_ws", err=ValueError("down"))
    ingest = FakeProvider("ingest", {"symbol": "BTC/USDT", "last": 11, "timestamp_ms": now})
    bus = MarketDataBus([ws, ingest])
    res = await bus.fetch_ticker("AAPL")
    assert res.source == "ingest"
    assert any(c.get("provider_id") == "exchange_ws" and c.get("ok") is False for c in res.meta["candidates"])


@pytest.mark.asyncio
async def test_bus_outlier_flag(monkeypatch):
    now = 1_000_000
    monkeypatch.setattr("marketdata.bus._now_ms", lambda: now)
    monkeypatch.setenv("MARKETDATA_OUTLIER_MAX_PCT", "10.0")
    monkeypatch.setenv("MARKETDATA_OUTLIER_WINDOW_MS", "100000")

    p = FakeProvider("ingest", {"symbol": "AAPL", "last": 100, "timestamp_ms": now})
    bus = MarketDataBus([p])
    r1 = await bus.fetch_ticker("AAPL")
    assert r1.meta["outlier"] is False

    # 50% jump should be flagged vs last good
    p2 = FakeProvider("ingest", {"symbol": "AAPL", "last": 150, "timestamp_ms": now})
    bus2 = MarketDataBus([p])
    _ = await bus2.fetch_ticker("AAPL")
    bus2._providers = [p2]
    r2 = await bus2.fetch_ticker("AAPL")
    assert r2.meta["outlier"] is True
