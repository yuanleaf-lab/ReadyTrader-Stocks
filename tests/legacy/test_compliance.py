import json
from unittest.mock import patch

from app.core.config import settings
from app.core.container import global_container
from app.tools.trading import place_stock_order
from core.risk import RiskGuardian


def test_price_collar_violation():
    rg = RiskGuardian()
    # 10% deviation (Price 110, Last Close 100) -> Should be blocked (>5%)
    res = rg.validate_trade('buy', 'AAPL', 100.0, 10000.0, 0.0, price=110.0, last_close_price=100.0)
    assert res['allowed'] is False
    assert "Price collar violation" in res['reason']

def test_pdt_protection():
    rg = RiskGuardian()
    # 4th day trade in $10k account -> Should be blocked
    res = rg.validate_trade('buy', 'AAPL', 100.0, 10000.0, 0.0, day_trades_count=4)
    assert res['allowed'] is False
    assert "Pattern Day Trader protection" in res['reason']

def test_audit_logging_integrity(tmp_path):
    from app.core.compliance import ComplianceLedger
    audit_file = tmp_path / "audit.log"
    ledger = ComplianceLedger(log_path=str(audit_file))
    
    ledger.record_event("test_compliance", {"foo": "bar"})
    
    with open(audit_file, "r") as f:
        line = f.readline()
        data = json.loads(line)
        assert data["event_type"] == "test_compliance"
        assert data["data"]["foo"] == "bar"

def test_execution_compliance_flow():
    with patch.object(settings, 'PAPER_MODE', True):
        with patch.object(settings, 'EXECUTION_APPROVAL_MODE', 'auto'):
            with patch.object(global_container, 'paper_engine') as mock_engine:
                 with patch.object(global_container, 'risk_guardian') as mock_risk:
                     mock_engine.execute_trade.return_value = "Exec OK"
                     mock_risk.validate_trade.return_value = {"allowed": True, "needs_confirmation": False}
                     
                     res_str = place_stock_order("AAPL", "buy", 1.0, rationale="Compliance Test")
                     res = json.loads(res_str)
                     assert res["ok"] is True
