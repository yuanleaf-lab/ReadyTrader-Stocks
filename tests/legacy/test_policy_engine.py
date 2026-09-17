import os
from unittest.mock import patch

import pytest

from core.policy import PolicyEngine, PolicyError


@pytest.fixture
def policy():
    return PolicyEngine()

def test_validate_insight_backing(policy):
    mock_insight = {"insight_id": "i1", "symbol": "AAPL", "confidence": 0.9}
    
    # Matching
    score = policy.validate_insight_backing(symbol="AAPL", insight_id="i1", insights=[mock_insight])
    assert score == 0.9
    
    # Not found
    with pytest.raises(PolicyError) as exc:
        policy.validate_insight_backing(symbol="MSFT", insight_id="i1", insights=[mock_insight])
    assert exc.value.code == "insight_not_found"

def test_validate_brokerage_order_allowlist(policy):
    with patch.dict(os.environ, {"ALLOW_BROKERAGES": "alpaca,tradier"}):
        # Allowed
        policy.validate_brokerage_order(exchange_id="alpaca", symbol="AAPL", side="buy", amount=10, order_type="market")
        policy.validate_brokerage_order(exchange_id="tradier", symbol="AAPL", side="buy", amount=10, order_type="market")
        
        # Blocked
        with pytest.raises(PolicyError) as exc:
            policy.validate_brokerage_order(exchange_id="ibkr", symbol="AAPL", side="buy", amount=10, order_type="market")
        assert exc.value.code == "brokerage_not_allowed"

def test_validate_ticker_allowlist(policy):
    with patch.dict(os.environ, {"ALLOW_TICKERS": "aapl,msft"}):
        # Allowed
        policy.validate_brokerage_order(exchange_id="alpaca", symbol="AAPL", side="buy", amount=10, order_type="market")
        
        # Blocked
        with pytest.raises(PolicyError) as exc:
            policy.validate_brokerage_order(exchange_id="alpaca", symbol="TSLA", side="buy", amount=10, order_type="market")
        assert exc.value.code == "ticker_not_allowed"

def test_validate_order_limits(policy):
    with patch.dict(os.environ, {"MAX_ORDER_AMOUNT": "100.0"}):
        # Good
        policy.validate_brokerage_order(exchange_id="alpaca", symbol="AAPL", side="buy", amount=50.0, order_type="market")
        
        # Too large
        with pytest.raises(PolicyError) as exc:
            policy.validate_brokerage_order(exchange_id="alpaca", symbol="AAPL", side="buy", amount=150.0, order_type="market")
        assert exc.value.code == "order_amount_too_large"

def test_validate_brokerage_access(policy):
    with patch.dict(os.environ, {"ALLOW_BROKERAGES": "alpaca"}):
        policy.validate_brokerage_access(exchange_id="alpaca")
        
        with pytest.raises(PolicyError) as exc:
            policy.validate_brokerage_access(exchange_id="tradier")
        assert exc.value.code == "brokerage_not_allowed"
