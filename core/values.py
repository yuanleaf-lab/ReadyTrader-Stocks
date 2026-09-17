"""Shared exact values and explicit, JSON-safe failures for the paper ledger."""
from datetime import datetime, timezone
from decimal import ROUND_HALF_EVEN, Decimal, InvalidOperation, localcontext

UNIT = Decimal('0.00000001')
ZERO = Decimal(0)
MAX_VALUE = Decimal('1000000000000')


class PaperError(ValueError):
    def __init__(self, code, message):
        self.code, self.message = code, message
        super().__init__(message)


def failure(code, message):
    return {'ok': False, 'error': {'code': code, 'message': message}}


def number(value, name='value', *, positive=False, exact=False):
    try:
        if isinstance(value, bool) or len(str(value)) > 80:
            raise ValueError()
        result = Decimal(str(value))
        if not result.is_finite() or abs(result) > MAX_VALUE or result < 0 or (positive and result <= 0):
            raise ValueError()
        if exact and result != money(result):
            raise ValueError()
        return result
    except (ValueError, InvalidOperation):
        raise PaperError('invalid_' + name, f'{name} must be finite, nonnegative (positive when required), within bounds and precision.') from None


def money(value):
    with localcontext() as ctx:
        ctx.prec = 50
        return Decimal(value).quantize(UNIT, rounding=ROUND_HALF_EVEN)


def text(value):
    return format(money(value), '.8f')


def utcnow():
    return datetime.now(timezone.utc)


def aware(value):
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise PaperError('invalid_timestamp', 'A timezone-aware timestamp is required.')
    return value.astimezone(timezone.utc)
