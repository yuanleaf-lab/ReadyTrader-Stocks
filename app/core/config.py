"""Validated server-only configuration; no live execution switch exists."""
import os
from dataclasses import dataclass, field
from decimal import Decimal

from core.risk import RiskLimits
from core.values import number


@dataclass(frozen=True)
class Settings:
    db_path: str = 'data/paper.db'
    initial_cash: Decimal = Decimal('10000')
    fixed_fee: Decimal = Decimal('0.01')
    fee_rate: Decimal = Decimal('0.0001')
    slippage_bps: Decimal = Decimal('5')
    quote_max_age: int = 180
    limits: RiskLimits = field(default_factory=RiskLimits)
    approved_symbols: tuple[str, ...] = ('AAPL', 'MSFT')

    @classmethod
    def from_env(cls):
        if os.getenv('PAPER_MODE', 'true').strip().lower() != 'true' or os.getenv('LIVE_TRADING_ENABLED', 'false').strip().lower() != 'false':
            raise ValueError('This build is permanently Paper-only. Remove live-mode configuration.')
        prefixes = ('ALPACA_', 'TRADIER_', 'IBKR_', 'SCHWAB_', 'ETRADE_', 'ROBINHOOD_')
        if any(key.startswith(prefixes) and value for key, value in os.environ.items()):
            raise ValueError('Brokerage configuration is forbidden in the Paper-only build. Remove brokerage variables.')
        def dec(env, default, positive=False):
            return number(os.getenv(env, default), env.lower(), positive=positive)
        return cls(
            db_path=os.getenv('PAPER_DB_PATH', 'data/paper.db'),
            initial_cash=dec('PAPER_INITIAL_CASH', '10000', True),
            fixed_fee=dec('PAPER_FIXED_FEE', '0.01'),
            fee_rate=dec('PAPER_FEE_RATE', '0.0001'),
            slippage_bps=dec('PAPER_SLIPPAGE_BPS', '5'),
            quote_max_age=int(os.getenv('PAPER_QUOTE_MAX_AGE_SECONDS', '180')),
            approved_symbols=tuple(s.strip().upper() for s in os.getenv('PAPER_APPROVED_SYMBOLS', 'AAPL,MSFT').split(',') if s.strip()),
            limits=RiskLimits(dec('PAPER_MAX_TRADE_PCT', '0.10', True),
                              dec('PAPER_MAX_SYMBOL_PCT', '0.25', True),
                              dec('PAPER_MAX_TOTAL_PCT', '0.80', True)),
        )
