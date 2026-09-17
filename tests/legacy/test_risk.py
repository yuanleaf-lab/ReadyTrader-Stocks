def test_position_sizing(risk_guardian):
    # Test safe trade
    # Portfolio: 10,000. Trade: 400 (4%) -> OK
    result = risk_guardian.validate_trade('buy', 'AAPL', 400.0, 10000.0, 0.0)
    assert result['allowed'] is True

    # Test unsafe trade
    # Portfolio: 10,000. Trade: 600 (6%) -> Blocked (>5%)
    result = risk_guardian.validate_trade('buy', 'AAPL', 600.0, 10000.0, 0.0)
    assert result['allowed'] is False
    assert "Position size too large" in result['reason']

def test_falling_knife_protection(risk_guardian):
    # Test normal buy
    result = risk_guardian.validate_trade('buy', 'AAPL', 100.0, 10000.0, 0.0)
    assert result['allowed'] is True

    # Test buy with bad sentiment
    result = risk_guardian.validate_trade('buy', 'AAPL', 100.0, 10000.0, -0.6)
    assert result['allowed'] is False
    assert "Falling Knife" in result['reason']

    # Test SELL with bad sentiment (should be allowed, cutting losses)
    result = risk_guardian.validate_trade('sell', 'AAPL', 100.0, 10000.0, -0.6)
    assert result['allowed'] is True

def test_daily_loss_limit(risk_guardian):
    # Tests Daily Loss Limit (5%)
    # Case 1: No loss -> Allowed
    result = risk_guardian.validate_trade('buy', 'AAPL', 100.0, 10000.0, 0.0, daily_loss_pct=0.0)
    assert result['allowed'] is True
    
    # Case 2: Hit Limit (-5%) -> Blocked
    result = risk_guardian.validate_trade('buy', 'AAPL', 100.0, 10000.0, 0.0, daily_loss_pct=-0.05)
    assert result['allowed'] is False
    assert "Daily Loss Limit Hit" in result['reason']

def test_max_drawdown_limit(risk_guardian):
    # Tests Drawdown Limit (10%)
    # Case 1: Low Drawdown -> Allowed
    result = risk_guardian.validate_trade('buy', 'AAPL', 100.0, 10000.0, 0.0, current_drawdown_pct=0.05)
    assert result['allowed'] is True
    
    # Case 2: Hit Limit (10%) -> Blocked
    result = risk_guardian.validate_trade('buy', 'AAPL', 100.0, 10000.0, 0.0, current_drawdown_pct=0.10)
    assert result['allowed'] is False
    assert "Max Drawdown Limit" in result['reason']

def test_large_trade_confirmation(risk_guardian):
    # Trade > $5000 should set needs_confirmation=True
    result = risk_guardian.validate_trade('buy', 'AAPL', 6000.0, 200000.0, 0.0)
    assert result['allowed'] is True
    assert result['needs_confirmation'] is True

def test_paper_engine_risk_metrics_nonzero(tmp_path):
    from core.paper import PaperTradingEngine

    db = tmp_path / "paper_test.db"
    engine = PaperTradingEngine(db_path=str(db))

    # Seed with USD so equity starts > 0
    engine.deposit("agent_zero", "USD", 1000.0)
    # Buy some AAPL at $150
    engine.execute_trade("agent_zero", "buy", "AAPL", 1, 150.0, "test")

    metrics = engine.get_risk_metrics("agent_zero")
    assert "daily_pnl_pct" in metrics
    assert "drawdown_pct" in metrics
    # With snapshots present, drawdown should be >= 0, daily pnl should be finite
    assert metrics["drawdown_pct"] >= 0.0
    assert abs(metrics["daily_pnl_pct"]) < 10.0
