import numpy as np
import pandas as pd

from intelligence.technical_analysis import calculate_indicators


def test_calculate_indicators():
    # Generate simple data
    # 100 periods
    close = np.linspace(100, 200, 100)
    volume = np.random.randint(100, 1000, 100)
    df = pd.DataFrame({
        "close": close,
        "high": close + 1,
        "low": close - 1,
        "volume": volume
    })
    
    df_out = calculate_indicators(df)
    
    assert "rsi" in df_out.columns
    assert "bb_high" in df_out.columns
    assert "macd" in df_out.columns
    assert "ema_20" in df_out.columns
    assert "vwap" in df_out.columns
    
    # Check values exist (after warmup)
    assert not pd.isna(df_out["rsi"].iloc[-1])
    assert not pd.isna(df_out["ema_20"].iloc[-1])
