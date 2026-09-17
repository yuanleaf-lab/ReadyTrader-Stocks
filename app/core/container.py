"""Lazy Paper-only composition; importing MCP tools never creates an account."""
from functools import lru_cache

from app.core.config import Settings
from app.services.paper_trading import PaperTradingService
from core.paper import PaperTradingEngine
from marketdata.exchange_provider import ExchangeProvider


@lru_cache(maxsize=1)
def get_service():
    config = Settings.from_env()
    engine = PaperTradingEngine(config.db_path, initial_cash=config.initial_cash,
                                fixed_fee=config.fixed_fee, fee_rate=config.fee_rate,
                                slippage_bps=config.slippage_bps, limits=config.limits,
                                quote_max_age=config.quote_max_age)
    return PaperTradingService(engine, ExchangeProvider(approved_symbols=config.approved_symbols))
