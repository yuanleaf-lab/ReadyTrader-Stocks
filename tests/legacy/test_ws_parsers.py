import pytest

from marketdata.ws_streams import (
    parse_alpaca_ticker_message,
)


def test_parse_alpaca_ticker_message_quote():
    msg = [
        {"T": "q", "S": "AAPL", "bp": 150.1, "ap": 150.2, "t": "2021-04-01T12:00:00Z"}
    ]
    snaps = parse_alpaca_ticker_message(msg)
    assert len(snaps) == 1
    snap = snaps[0]
    assert snap["symbol"] == "AAPL"
    assert snap["bid"] == 150.1
    assert snap["ask"] == 150.2
    assert snap["last"] == pytest.approx(150.15)


def test_parse_alpaca_ticker_message_trade():
    msg = [
        {"T": "t", "S": "MSFT", "p": 250.0, "s": 100, "t": "2021-04-01T12:00:00Z"}
    ]
    snaps = parse_alpaca_ticker_message(msg)
    assert len(snaps) == 1
    snap = snaps[0]
    assert snap["symbol"] == "MSFT"
    assert snap["last"] == 250.0
    assert snap.get("bid") is None


def test_parse_alpaca_ticker_multiple():
    msg = [
        {"T": "q", "S": "AAPL", "bp": 150.0, "ap": 151.0},
        {"T": "t", "S": "TSLA", "p": 600.0}
    ]
    snaps = parse_alpaca_ticker_message(msg)
    assert len(snaps) == 2
    assert snaps[0]["symbol"] == "AAPL"
    assert snaps[1]["symbol"] == "TSLA"
