
import pandas as pd

from core.stress_test import run_synthetic_stress_test
from marketdata.synthetic import generate_synthetic_ohlcv


def test_synthetic_market_determinism():
    a = generate_synthetic_ohlcv(seed=123, length=200, timeframe="1h", start_price=100.0)
    b = generate_synthetic_ohlcv(seed=123, length=200, timeframe="1h", start_price=100.0)

    df_a = a["df"][["open", "high", "low", "close", "volume"]].round(8)
    df_b = b["df"][["open", "high", "low", "close", "volume"]].round(8)
    pd.testing.assert_frame_equal(df_a, df_b)
    assert a["meta"]["seed"] == b["meta"]["seed"]


def test_run_synthetic_stress_outputs_artifacts_and_seeds():
    strategy = """
PARAMS = {\"max_alloc_pct\": 0.05, \"debounce_bars\": 0}
def on_candle(close, rsi, state):
    # simple: buy if oversold, sell if overbought
    if rsi < 30: return 'buy'
    if rsi > 70: return 'sell'
    return 'hold'
"""
    out = run_synthetic_stress_test(
        strategy_code=strategy,
        config={"master_seed": 7, "scenarios": 25, "length": 200, "timeframe": "1h"},
    )
    assert "summary" in out and "artifacts" in out
    summary = out["summary"]
    assert summary["master_seed"] == 7
    assert len(summary["seeds"]) == 25
    assert "scenario_metrics_csv" in out["artifacts"]
    assert "worst_drawdown_equity_csv" in out["artifacts"]

