from unittest.mock import MagicMock, patch

import pandas as pd

from marketdata.exchange_provider import ExchangeProvider


def test_ticker_cache_hits():
    # Mocking yfinance since we don't pass exchanges anymore
    with patch("yfinance.Ticker") as mock_ticker:
        mock_inst = MagicMock()
        mock_inst.history.return_value = pd.DataFrame({
            "Open": [100.0], "High": [110.0], "Low": [90.0], "Close": [105.0], "Volume": [1000.0]
        }, index=[pd.Timestamp.now()])
        mock_ticker.return_value = mock_inst
        
        provider = ExchangeProvider()
        ticker = provider.fetch_ticker("AAPL")
        assert ticker["last"] == 105.0
        
        # Second call should hit cache (mock_ticker called once)
        provider.fetch_ticker("AAPL")
        assert mock_ticker.call_count == 1

def test_fetch_ohlcv_formatting():
    with patch("yfinance.Ticker") as mock_ticker:
        mock_inst = MagicMock()
        mock_inst.history.return_value = pd.DataFrame({
            "Open": [100.0], "High": [110.0], "Low": [90.0], "Close": [105.0], "Volume": [1000.0]
        }, index=[pd.Timestamp.now()])
        mock_ticker.return_value = mock_inst
        
        provider = ExchangeProvider()
        ohlcv = provider.fetch_ohlcv("AAPL", timeframe="1h", limit=1)
        assert len(ohlcv) == 1
        assert len(ohlcv[0]) == 6 # [ts, o, h, l, c, v]
        assert ohlcv[0][4] == 105.0
