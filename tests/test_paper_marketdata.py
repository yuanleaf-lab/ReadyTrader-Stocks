"""Offline tests at the yfinance response boundary and real NYSE calendar."""
import importlib
import json
from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace

import pandas as pd
import pytest


def adapter():
    return importlib.import_module("marketdata.exchange_provider")


def frame(price=123.45, timestamp="2025-09-17T14:00:00Z"):
    return pd.DataFrame({"Open": [123.0], "High": [125.0], "Low": [122.0],
                         "Close": [price], "Volume": [100]},
                        index=pd.DatetimeIndex([timestamp]))


def ticker(monkeypatch, *, info=None, history=None, splits=None):
    module = adapter()
    metadata = {"symbol": "AAPL", "quoteType": "EQUITY", "currency": "USD",
                "exchange": "NMS", "shortName": "Apple Inc.", "country": "United States"}
    if info is not None:
        metadata.update(info)
    calls = []

    def read_history(**kwargs):
        calls.append(kwargs)
        if kwargs.get("actions"):
            data = frame(timestamp="2025-09-17T00:00:00Z")
            data["Stock Splits"] = 0.0
            data["Dividends"] = 0.75
            if splits is not None:
                data = pd.DataFrame({"Stock Splits": splits, "Dividends": 0.0})
            return data
        return frame() if history is None else history

    fake = SimpleNamespace(info=metadata, history=read_history,
                           splits=pd.Series(dtype=float) if splits is None else splits)
    monkeypatch.setattr(module.yf, "Ticker", lambda symbol: fake)
    return module, calls


def test_quote_preserves_source_time_and_uses_unadjusted_regular_minutes(monkeypatch):
    module, calls = ticker(monkeypatch)
    result = module.ExchangeProvider(approved_symbols={"AAPL"}).fetch_quote(" aapl ")
    assert result.symbol == "AAPL"
    assert result.price == Decimal("123.45")
    assert result.as_of == datetime(2025, 9, 17, 14, tzinfo=timezone.utc)
    assert result.fetched_at.utcoffset() is not None
    assert calls == [{"period": "1d", "interval": "1m", "auto_adjust": False,
                      "prepost": False, "actions": False}]
    with pytest.raises((AttributeError, TypeError)):
        result.price = Decimal("1")


@pytest.mark.parametrize("symbol", ["", "BTC-USD", "AAPL/USDT", "^GSPC", "AAPL240920C00100000", "AAPL;", None])
def test_rejects_non_stock_symbol_syntax(symbol):
    with pytest.raises(ValueError):
        adapter().normalize_symbol(symbol)


def test_normalizes_class_share_syntax():
    assert adapter().normalize_symbol(" brk.b ") == "BRK-B"


@pytest.mark.parametrize("info", [
    {"currency": "EUR"}, {"exchange": "LSE"}, {"quoteType": "ETF"},
    {"shortName": "Example ADR"}, {"longName": "Example Depositary Shares"},
    {"longName": "Example Preferred Stock"}, {"shortName": "Example Warrants"},
    {"shortName": "Example Units"}, {"quoteType": None}, {"currency": None},
    {"symbol": "OTHER"}, {"isETF": True},
])
def test_approval_does_not_bypass_instrument_restrictions(monkeypatch, info):
    module, _ = ticker(monkeypatch, info=info)
    with pytest.raises(ValueError):
        module.ExchangeProvider(approved_symbols={"AAPL"}).fetch_quote("AAPL")


def test_equity_label_alone_is_ambiguous(monkeypatch):
    module, _ = ticker(monkeypatch)
    with pytest.raises(ValueError, match="common"):
        module.ExchangeProvider().fetch_quote("AAPL")


def test_explicit_common_stock_metadata_is_accepted(monkeypatch):
    module, _ = ticker(monkeypatch, info={"securityType": "COMMON_STOCK"})
    assert module.ExchangeProvider().fetch_quote("AAPL").price == Decimal("123.45")


@pytest.mark.parametrize("price", [0, -1, float("nan"), float("inf"), "bad", True])
def test_invalid_quote_price_fails_closed(monkeypatch, price):
    module, _ = ticker(monkeypatch, history=frame(price))
    with pytest.raises(ValueError):
        module.ExchangeProvider(approved_symbols={"AAPL"}).fetch_quote("AAPL")


@pytest.mark.parametrize("timestamp", ["2026-09-17T14:00:00", "2200-01-01T00:00:00Z", pd.NaT])
def test_invalid_quote_timestamp_fails_closed(monkeypatch, timestamp):
    module, _ = ticker(monkeypatch, history=frame(timestamp=timestamp))
    with pytest.raises(ValueError):
        module.ExchangeProvider(approved_symbols={"AAPL"}).fetch_quote("AAPL")


def test_empty_price_history_fails_closed(monkeypatch):
    module, _ = ticker(monkeypatch, history=pd.DataFrame())
    with pytest.raises(ValueError):
        module.ExchangeProvider(approved_symbols={"AAPL"}).fetch_quote("AAPL")


def test_history_is_json_safe_and_unadjusted(monkeypatch):
    module, calls = ticker(monkeypatch)
    result = module.ExchangeProvider(approved_symbols={"AAPL"}).fetch_ohlcv("AAPL")
    assert result == [{"timestamp": "2025-09-17T14:00:00+00:00", "open": 123.0,
                       "high": 125.0, "low": 122.0, "close": 123.45, "volume": 100.0}]
    json.dumps(result, allow_nan=False)
    assert calls[0]["interval"] == "1d"
    assert calls[0]["auto_adjust"] is False
    assert calls[0]["prepost"] is False


@pytest.mark.parametrize("kwargs", [{"timeframe": "2x"}, {"limit": 0}, {"limit": True}, {"limit": 1001}])
def test_history_rejects_invalid_arguments(monkeypatch, kwargs):
    module, calls = ticker(monkeypatch)
    with pytest.raises(ValueError):
        module.ExchangeProvider(approved_symbols={"AAPL"}).fetch_ohlcv("AAPL", **kwargs)
    assert not calls


def test_history_rejects_nonfinite_ohlc(monkeypatch):
    history = frame()
    history.loc[:, "High"] = float("inf")
    module, _ = ticker(monkeypatch, history=history)
    with pytest.raises(ValueError):
        module.ExchangeProvider(approved_symbols={"AAPL"}).fetch_ohlcv("AAPL")


def test_search_filters_with_full_metadata_and_disables_news(monkeypatch):
    module = adapter()
    calls = []

    def search(query, **kwargs):
        calls.append(kwargs)
        return SimpleNamespace(quotes=[{"symbol": "SPY"}, {"symbol": "AAPL"}, {"symbol": "AAPL"}])

    def get_ticker(symbol):
        return SimpleNamespace(info={"symbol": symbol, "quoteType": "ETF" if symbol == "SPY" else "EQUITY",
                                    "currency": "USD", "exchange": "NMS", "shortName": symbol})

    monkeypatch.setattr(module.yf, "Search", search)
    monkeypatch.setattr(module.yf, "Ticker", get_ticker)
    result = module.ExchangeProvider(approved_symbols={"AAPL", "SPY"}).search_symbol("Apple")
    assert [item["symbol"] for item in result] == ["AAPL"]
    assert calls[0]["news_count"] == 0
    json.dumps(result, allow_nan=False)


def test_splits_since_acquisition_fail_closed(monkeypatch):
    module, _ = ticker(monkeypatch, splits=pd.Series([4.0], index=pd.DatetimeIndex(["2026-09-17T00:00:00Z"])))
    provider = module.ExchangeProvider(approved_symbols={"AAPL"})
    with pytest.raises(ValueError, match="split"):
        provider.check_corporate_actions("AAPL", datetime(2026, 9, 16, tzinfo=timezone.utc))
    provider.check_corporate_actions("AAPL", datetime(2026, 9, 18, tzinfo=timezone.utc))


def test_split_check_requires_explicit_error_and_action_history(monkeypatch):
    module, calls = ticker(monkeypatch)
    module.ExchangeProvider(approved_symbols={"AAPL"}).check_corporate_actions(
        "AAPL", datetime(2025, 9, 16, tzinfo=timezone.utc))
    assert calls and calls[0]["raise_errors"] is True
    assert calls[0]["actions"] is True
    assert calls[0]["auto_adjust"] is False


@pytest.mark.parametrize("data", [pd.DataFrame(), frame()])
def test_split_check_rejects_unverifiable_response(monkeypatch, data):
    module, _ = ticker(monkeypatch)
    fake = module.yf.Ticker("AAPL")
    fake.history = lambda **kwargs: data
    with pytest.raises(ValueError):
        module.ExchangeProvider(approved_symbols={"AAPL"}).check_corporate_actions(
            "AAPL", datetime(2025, 9, 16, tzinfo=timezone.utc))


@pytest.mark.parametrize("timestamp, expected", [
    ("2026-09-17T13:29:59+00:00", False), ("2026-09-17T13:30:00+00:00", True),
    ("2026-09-17T19:59:59+00:00", True), ("2026-09-17T20:00:00+00:00", False),
    ("2026-09-19T15:00:00+00:00", False), ("2026-12-25T15:00:00+00:00", False),
    ("2026-11-27T17:59:59+00:00", True), ("2026-11-27T18:00:00+00:00", False),
    ("2026-01-05T14:29:59+00:00", False), ("2026-01-05T14:30:00+00:00", True),
])
def test_real_nyse_schedule_holidays_dst_and_early_close(timestamp, expected):
    calendar = importlib.import_module("marketdata.calendar").USMarketCalendar()
    moment = datetime.fromisoformat(timestamp)
    assert calendar.is_open(moment) is expected
    if expected:
        calendar.require_open(moment)
    else:
        with pytest.raises(ValueError):
            calendar.require_open(moment)


def test_calendar_rejects_naive_time():
    calendar = importlib.import_module("marketdata.calendar").USMarketCalendar()
    with pytest.raises(ValueError):
        calendar.is_open(datetime(2026, 9, 17, 14))
