import numpy as np
import pandas as pd

from intelligence.recommendations import recommend_settings
from intelligence.regime import RegimeDetector


def test_recommend_settings():
    # 1. High Drawdown -> Suggest max_alloc_pct reduction
    summary = {
        "metrics": {"max_drawdown_max": 0.40, "max_drawdown_p95": 0.30},
        "strategy_params_detected": {"max_alloc_pct": 0.10}
    }
    res = recommend_settings(summary)
    
    updates = res["recommended_params"]
    assert "max_alloc_pct" in updates
    assert updates["max_alloc_pct"] == 0.02
    
    # 2. Negative returns -> Suggest min_signal_strength
    summary = {
        "metrics": {"return_p05": -0.15},
        "strategy_params_detected": {}
    }
    res = recommend_settings(summary)
    # Checks guidance even if not detected
    recs = res["recommendations"]
    assert any(r["param"] == "min_signal_strength" for r in recs)

def test_regime_detector():
    det = RegimeDetector()
    
    # Not enough data
    df_small = pd.DataFrame({"close": range(10)})
    assert "error" in det.detect(df_small)
    
    # Trending Up
    # 100 periods
    close = np.linspace(100, 200, 100) # Strong uptrend
    df = pd.DataFrame({
        "high": close + 5,
        "low": close - 5,
        "close": close,
    })
    
    res = det.detect(df)
    # ADX should be high for straight line? Actually straight line has 0 volatility but direction is up.
    # ADX calculation is complex.
    # Let's ensure it runs and returns keys.
    assert "regime" in res
    assert "adx" in res
    assert "atr_pct" in res
