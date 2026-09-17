
def test_safe_execution(backtest_engine):
    # Simple strategy that should pass
    strategy = """
def on_candle(close, rsi, state):
    return 'hold'
"""
    # We mock fetch_ohlcv to avoid real network call
    backtest_engine.fetch_ohlcv = lambda *args, **kwargs: _mock_ohlcv()
    
    # We need a mock dataframe generator
    import pandas as pd
    def _mock_ohlcv():
        return pd.DataFrame({
            'timestamp': [pd.Timestamp.now()] * 100,
            'open': [100.0] * 100,
            'high': [105.0] * 100,
            'low': [95.0] * 100,
            'close': [100.0] * 100,
            'volume': [1000.0] * 100
        })

    result = backtest_engine.run(strategy, "AAPL")
    assert "error" not in result

def test_rce_prevention(backtest_engine):
    # Attempt to import os
    strategy = """
import os
def on_candle(close, rsi, state):
    return 'hold'
"""
    # Mock data fetch
    import pandas as pd
    backtest_engine.fetch_ohlcv = lambda *args, **kwargs: pd.DataFrame(
        columns=["timestamp", "open", "high", "low", "close", "volume"]
    )

    result = backtest_engine.run(strategy, "AAPL")
    assert "error" in result
    assert "Importing 'os' is forbidden" in result['error'] or "Compilation Error" in result['error']

def test_file_access_prevention(backtest_engine):
    # Attempt to open file
    strategy = """
def on_candle(close, rsi, state):
    open('/etc/passwd', 'r')
    return 'hold'
"""
    import pandas as pd
    # Ensure loop executes: provide enough candles so RSI isn't NaN
    df = pd.DataFrame(
        {
            "timestamp": pd.date_range("2020-01-01", periods=30, freq="h"),
            "open": [100.0] * 30,
            "high": [101.0] * 30,
            "low": [99.0] * 30,
            "close": list(range(100, 130)),
            "volume": [1000.0] * 30,
        }
    )
    backtest_engine.fetch_ohlcv = lambda *args, **kwargs: df

    result = backtest_engine.run(strategy, "AAPL")
    assert "error" in result
