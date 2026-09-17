from unittest.mock import MagicMock, patch

import pytest

from execution.retail_services import EtradeBrokerage, RobinhoodBrokerage, SchwabBrokerage


def test_schwab_brokerage_not_configured():
    with patch.dict("os.environ", {}, clear=True):
        schwab = SchwabBrokerage()
        assert not schwab.is_available()
        
        with pytest.raises(RuntimeError):
            schwab.place_order("AAPL", "buy", 10)

def test_schwab_brokerage_configured():
    with patch.dict("os.environ", {"SCHWAB_ACCESS_TOKEN": "token"}):
        schwab = SchwabBrokerage()
        assert schwab.is_available()
        
        # Test Place Order
        with patch("execution.retail_services.requests.post") as mock_post:
             with patch.dict("os.environ", {"SCHWAB_ACCOUNT_HASH": "hash"}):
                 mock_resp = MagicMock()
                 mock_resp.headers = {"Location": "orders/123"}
                 mock_resp.json.return_value = {}
                 mock_post.return_value = mock_resp
                 
                 res = schwab.place_order("AAPL", "buy", 10)
                 assert res["status"] == "submitted"
                 assert res["id"] == "123"

def test_etrade_brokerage():
    with patch.dict("os.environ", {}, clear=True):
         et = EtradeBrokerage()
         assert not et.is_available()
    
    # Mock _OAUTH_LIB_AVAILABLE
    with patch("execution.retail_services._OAUTH_LIB_AVAILABLE", True):
        with patch.dict("os.environ", {
            "ETRADE_CONSUMER_KEY": "k",
            "ETRADE_CONSUMER_SECRET": "s",
            "ETRADE_RESOURCE_OWNER_KEY": "rk",
            "ETRADE_RESOURCE_OWNER_SECRET": "rs"
        }):
             et = EtradeBrokerage()
             assert et.is_available()
             # Should fail gracefully on balance check if session fails or mocks not set
             # But here session is created.
             # We won't test full oauth flow, just instantiation and availability
             assert et.session is not None

def test_robinhood_brokerage():
    with patch.dict("os.environ", {}, clear=True):
         rh = RobinhoodBrokerage()
         assert not rh.is_available()
         
    with patch("execution.retail_services._ROBINHOOD_LIB_AVAILABLE", True):
        with patch.dict("os.environ", {"ROBINHOOD_USER": "u", "ROBINHOOD_PASS": "p"}):
             rh = RobinhoodBrokerage()
             assert rh.is_available()
