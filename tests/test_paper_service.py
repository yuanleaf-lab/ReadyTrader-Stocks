import importlib
from datetime import timedelta
from decimal import Decimal as D

import pytest

from core.risk import RiskLimits
from tests.test_paper_core import NOW, make_engine, quote, trade


class Feed:
    def __init__(self):
        self.prices = {'AAPL': '100', 'MSFT': '100'}
        self.as_of = NOW

    def fetch_quote(self, symbol):
        if symbol not in self.prices:
            raise ValueError('Not an eligible common stock')
        return quote(self.prices[symbol], self.as_of, symbol)

    def check_corporate_actions(self, symbol, since):
        pass


def service(tmp_path, **options):
    module = importlib.import_module('app.services.paper_trading')
    engine = make_engine(tmp_path, **options)
    return module.PaperTradingService(engine, Feed())


def test_service_buys_and_replays_after_close_without_quote(tmp_path):
    s = service(tmp_path)
    first = s.buy('AAPL', '0.25', 'request', 'thesis')
    assert first['ok']
    s.engine.clock = lambda: NOW + timedelta(days=2)
    s.provider.prices.clear()
    assert s.buy('AAPL', '0.25', 'request', 'thesis') == first


@pytest.mark.parametrize('symbol', ['BTC-USD', 'SPY', 'AAPL240119C00100000', '^GSPC', 'EURUSD=X', 'USDT', 'NOPE'])
def test_non_stocks_fail(tmp_path, symbol):
    s = service(tmp_path)
    assert s.buy(symbol, '1', 'invalid')['ok'] is False
    assert D(s.engine.state()['cash']) == 1000


@pytest.mark.parametrize('when', [NOW.replace(hour=12), NOW+timedelta(days=2), NOW.replace(month=12, day=25)])
def test_closed_weekend_holiday_fail(tmp_path, when):
    s = service(tmp_path)
    s.engine.clock = lambda: when
    assert s.buy('AAPL', '1', 'closed')['error']['code'] == 'market_closed'


def test_service_stale_quote_never_uses_executed_price(tmp_path):
    s = service(tmp_path)
    assert s.buy('AAPL', '1', 'first')['ok']
    s.provider.as_of = NOW-timedelta(minutes=10)
    assert s.buy('AAPL', '1', 'second')['error']['code'] == 'stale_quote'
    assert D(s.engine.state()['cash']) == 900


def test_trade_limit_uses_real_equity(tmp_path):
    e = make_engine(tmp_path, limits=RiskLimits(D('.05'), D('1'), D('1')))
    assert trade(e, quantity='.6')['error']['code'] == 'trade_limit'


def test_cumulative_symbol_limit_cannot_be_split_around(tmp_path):
    e = make_engine(tmp_path, limits=RiskLimits(D('1'), D('.15'), D('1')))
    assert trade(e)['ok']
    assert trade(e, key='second')['error']['code'] == 'symbol_limit'


def test_total_limit_accounts_for_other_symbols(tmp_path):
    s = service(tmp_path, limits=RiskLimits(D('1'), D('1'), D('.15')))
    assert s.buy('AAPL', '1', 'one')['ok']
    assert s.buy('MSFT', '1', 'two')['error']['code'] == 'total_limit'


def test_full_sell_not_blocked_by_buy_risk_limits(tmp_path):
    s = service(tmp_path, limits=RiskLimits(D('.1'), D('.2'), D('.8')))
    assert s.buy('AAPL', '1', 'one')['ok']
    assert s.buy('AAPL', '1', 'two')['ok']
    assert s.sell('AAPL', '2', 'exit')['ok']


def test_queries_use_current_prices_and_preserve_rationale(tmp_path):
    s = service(tmp_path)
    assert s.buy('AAPL', '1', 'one', 'A reason')['ok']
    s.provider.prices['AAPL'] = '120'
    p = s.get_portfolio()['data']
    assert D(p['equity']) == 1020
    assert D(p['unrealized_pnl']) == 20
    assert s.get_trade_history()['data']['trades'][0]['rationale'] == 'A reason'
    assert D(s.get_performance()['data']['equity']) == 1020


def test_missing_holdings_price_fails_instead_of_zero_valuation(tmp_path):
    s = service(tmp_path)
    assert s.buy('AAPL', '1', 'one')['ok']
    del s.provider.prices['AAPL']
    assert s.get_portfolio()['ok'] is False
    assert s.buy('MSFT', '1', 'two')['ok'] is False


def test_failed_order_is_audited_and_idempotent(tmp_path):
    s = service(tmp_path)
    result = s.buy('AAPL', '11', 'failed', 'too large')
    assert result['ok'] is False
    s.provider.prices['AAPL'] = '1'
    assert s.buy('AAPL', '11', 'failed', 'too large') == result
    assert s.get_orders()['data']['orders'][0]['status'] == 'rejected'


def test_live_env_never_enables_real_trading(monkeypatch):
    monkeypatch.setenv('PAPER_MODE', 'false')
    from app.core.config import Settings
    with pytest.raises(ValueError, match='[Pp]aper'):
        Settings.from_env()
