from app.core.config import settings
from app.core.container import global_container


def test_config_loading():
    assert settings.PROJECT_NAME == "ReadyTrader-Stocks"
    assert global_container.exchange_provider is not None
