import json
from unittest.mock import patch

# If FastMCP wraps them, we might need to access `.fn` or just call them if they act as proxies.
# Assuming standard python decorators, they are callable.
from app.core.config import settings
from app.core.container import global_container

# Import the specific functions from the new modules
from app.tools.trading import place_stock_order, start_brokerage_private_ws


def test_fetch_price():
    # This was tested in test_market_tools? We can skip or reimplement.
    pass


                
def test_place_stock_order_requires_approval():
    with patch.object(settings, 'EXECUTION_APPROVAL_MODE', 'approve_each'):
        with patch.object(global_container, 'risk_guardian') as mock_risk:
            mock_risk.validate_trade.return_value = {"allowed": True, "needs_confirmation": False}
            
            res_str = place_stock_order("AAPL", "buy", 1.0)
            res = json.loads(res_str)
            
            assert res["ok"] is True
            assert res["data"]["status"] == "pending_approval"

def test_place_stock_order_paper_mode():
    with patch.object(settings, 'PAPER_MODE', True):
        with patch.object(settings, 'EXECUTION_APPROVAL_MODE', 'auto'):
            with patch.object(global_container, 'paper_engine') as mock_engine:
                with patch.object(global_container, 'risk_guardian') as mock_risk:
                    mock_engine.execute_trade.return_value = "Paper Trade Executed"
                    mock_risk.validate_trade.return_value = {"allowed": True, "needs_confirmation": False}
                    
                    res_str = place_stock_order("AAPL", "buy", 1.0)
                    res = json.loads(res_str)
                    
                    assert res["ok"] is True
                    assert res["data"]["venue"] == "paper"
                    assert "Paper Trade Executed" in res["data"]["result"]

def test_private_ws_paper_mode_blocked():
     with patch.object(settings, 'PAPER_MODE', True):
         res_str = start_brokerage_private_ws("alpaca")
         res = json.loads(res_str)
         assert res["ok"] is False
         assert res["error"]["code"] == "paper_mode_not_supported"

def test_private_ws_alpaca_ws():
    with patch.object(settings, 'PAPER_MODE', False):
        res_str = start_brokerage_private_ws("alpaca")
        res = json.loads(res_str)
        assert res["ok"] is True
        assert res["data"]["mode"] == "ws"
        assert res["data"]["brokerage"] == "alpaca"
