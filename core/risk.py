"""Deterministic server-side cash-equity exposure checks (no sentiment or brokers)."""
from dataclasses import dataclass
from decimal import Decimal

from core.values import PaperError, number


@dataclass(frozen=True)
class RiskLimits:
    max_trade_pct: Decimal = Decimal('0.10')
    max_symbol_pct: Decimal = Decimal('0.25')
    max_total_pct: Decimal = Decimal('0.80')

    def __post_init__(self):
        for name in ('max_trade_pct', 'max_symbol_pct', 'max_total_pct'):
            value = number(getattr(self, name), name, positive=True)
            if value > 1:
                raise ValueError(f'{name} must not exceed 1; leverage is forbidden.')
            object.__setattr__(self, name, value)


class RiskGuardian:
    def __init__(self, limits=None):
        self.limits = limits or RiskLimits()

    def validate_buy(self, *, equity_before, equity_after, trade_value, symbol_value, total_value):
        if equity_before <= 0 or equity_after <= 0:
            raise PaperError('invalid_equity', 'Positive, completely valued equity is required.')
        checks = (
            (trade_value, equity_before, self.limits.max_trade_pct, 'trade_limit'),
            (symbol_value, equity_after, self.limits.max_symbol_pct, 'symbol_limit'),
            (total_value, equity_after, self.limits.max_total_pct, 'total_limit'),
        )
        for value, equity, cap, code in checks:
            if value > equity * cap:
                raise PaperError(code, f'Buy exceeds {code}: maximum equity fraction {cap}.')

    def status(self):
        return {name: str(getattr(self.limits, name)) for name in ('max_trade_pct', 'max_symbol_pct', 'max_total_pct')}
