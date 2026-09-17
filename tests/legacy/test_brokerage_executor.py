import os
from unittest.mock import MagicMock, patch

from execution.alpaca_service import AlpacaBrokerage


@patch("execution.alpaca_service._ALPACA_PY_AVAILABLE", True)
@patch("execution.alpaca_service.TradingClient")
def test_alpaca_brokerage_init(mock_client):
    with patch.dict(os.environ, {"ALPACA_API_KEY": "key", "ALPACA_API_SECRET": "secret"}):
        brokerage = AlpacaBrokerage()
        assert brokerage.is_available() is True
        mock_client.assert_called_once()

@patch("execution.alpaca_service._ALPACA_PY_AVAILABLE", True)
@patch("execution.alpaca_service.MarketOrderRequest")
@patch("execution.alpaca_service.TimeInForce", **{"FILL_OR_KILL": "fok", "GTC": "gtc"})
@patch("execution.alpaca_service.OrderSide", **{"BUY": "buy", "SELL": "sell"})
@patch("execution.alpaca_service.TradingClient")
def test_alpaca_brokerage_place_order(mock_client, mock_side, mock_tif, mock_req):
    with patch.dict(os.environ, {"ALPACA_API_KEY": "key", "ALPACA_API_SECRET": "secret"}):
        mock_instance = MagicMock()
        mock_client.return_value = mock_instance
        
        mock_order = MagicMock()
        mock_order.id = "alpaca_1"
        mock_order.client_order_id = "abc"
        mock_order.status = "open"
        mock_order.symbol = "AAPL"
        mock_order.side = "buy"
        mock_order.qty = "5"
        mock_order.type = "market"
        
        mock_instance.submit_order.return_value = mock_order
        
        brokerage = AlpacaBrokerage()
        res = brokerage.place_order(symbol="AAPL", side="buy", qty=5)
        
        assert res["id"] == "alpaca_1"
        assert res["symbol"] == "AAPL"
        assert res["qty"] == 5.0
        mock_instance.submit_order.assert_called_once()

@patch("execution.alpaca_service._ALPACA_PY_AVAILABLE", True)
@patch("execution.alpaca_service.TradingClient")
def test_alpaca_brokerage_get_balance(mock_client):
    with patch.dict(os.environ, {"ALPACA_API_KEY": "key", "ALPACA_API_SECRET": "secret"}):
        mock_instance = MagicMock()
        mock_client.return_value = mock_instance
        
        mock_account = MagicMock()
        mock_account.equity = "100000.0"
        mock_account.cash = "50000.0"
        mock_account.buying_power = "200000.0"
        mock_instance.get_account.return_value = mock_account
        
        brokerage = AlpacaBrokerage()
        res = brokerage.get_account_balance()
        
        assert res["equity"] == 100000.0
        assert res["cash"] == 50000.0

