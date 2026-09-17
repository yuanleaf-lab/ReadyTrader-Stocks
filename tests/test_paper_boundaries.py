from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from decimal import Decimal as D

import pytest

from core.values import PaperError
from tests.test_paper_core import NOW, make_engine, quote, trade
from tests.test_paper_service import service


def test_concurrent_oversell_cannot_go_short(tmp_path):
    e = make_engine(tmp_path)
    assert trade(e)['ok']
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda key: trade(e, side='sell', key=key), ['sell1', 'sell2']))
    assert sum(r['ok'] for r in results) == 1
    assert e.state()['positions'] == {}
    assert D(e.state()['cash']) == 1000


def test_quote_collection_racing_reset_cannot_spend_new_account(tmp_path):
    s = service(tmp_path)
    old_fetch = s.provider.fetch_quote
    def fetch(symbol):
        token = s.engine.authorize_reset()
        assert s.engine.reset(token)['ok']
        return old_fetch(symbol)
    s.provider.fetch_quote = fetch
    assert s.buy('AAPL', '1', 'raced')['error']['code'] == 'account_changed'
    assert s.engine.state()['positions'] == {}
    assert D(s.engine.state()['cash']) == 1000


def test_reset_token_expiration(tmp_path):
    e = make_engine(tmp_path)
    token = e.authorize_reset(ttl_seconds=10)
    e.clock = lambda: NOW+timedelta(seconds=11)
    assert e.reset(token)['error']['code'] == 'reset_not_authorized'
    assert e.state()['generation'] == 1


def test_all_reset_tokens_invalidated_on_reset(tmp_path):
    e = make_engine(tmp_path)
    one, two = e.authorize_reset(), e.authorize_reset()
    assert e.reset(one)['ok']
    assert e.reset(two)['ok'] is False


def test_failed_snapshot_rolls_back_order_and_balances(tmp_path):
    import sqlite3
    e = make_engine(tmp_path)
    with sqlite3.connect(e.db_path) as conn:
        conn.execute("CREATE TRIGGER reject_snap BEFORE INSERT ON equity_snapshots BEGIN SELECT RAISE(ABORT,'failure'); END")
    assert trade(e)['ok'] is False
    assert D(e.state()['cash']) == 1000
    assert e.state()['positions'] == {}
    assert e.orders() == []


def test_weighted_cost_partial_sales_reconcile_to_equity(tmp_path):
    e = make_engine(tmp_path)
    assert trade(e, quantity='1')['ok']
    assert trade(e, quantity='1', price='120', key='two')['ok']
    assert trade(e, side='sell', quantity='.5', price='130', key='sell')['ok']
    p = e.valuate({'AAPL':quote('130')}, 1)
    assert D(p['cash']) == 845
    assert D(p['positions'][0]['cost_basis']) == 165
    assert D(p['realized_pnl']) == 10
    assert D(p['unrealized_pnl']) == 30
    assert D(p['equity']) == 1040


def test_stale_read_does_not_add_fake_curve_point(tmp_path):
    s = service(tmp_path)
    assert s.buy('AAPL','1','first')['ok']
    before = s.engine.performance()['sample_count']
    s.engine.clock = lambda: NOW+timedelta(days=2)
    p = s.get_portfolio()
    assert p['ok'] and p['data']['stale']
    assert s.engine.performance()['sample_count'] == before


@pytest.mark.parametrize('bad_price', ['NaN', 'Infinity', '0', '-1'])
def test_invalid_reference_cannot_modify_ledger(tmp_path, bad_price):
    e = make_engine(tmp_path)
    assert trade(e, price=bad_price)['ok'] is False
    assert D(e.state()['cash']) == 1000


def test_future_or_naive_quote_rejected(tmp_path):
    e = make_engine(tmp_path)
    for index, stamp in enumerate((NOW+timedelta(seconds=30), NOW.replace(tzinfo=None))):
        result=e.execute(side='buy',symbol='AAPL',quantity='1',client_order_id=str(index),rationale='',
                         quotes={'AAPL':quote(as_of=stamp)},generation=1)
        assert result['ok'] is False
    assert D(e.state()['cash']) == 1000


def test_premarket_quote_cannot_be_used_for_execution(tmp_path):
    e = make_engine(tmp_path)
    premarket = NOW.replace(hour=13, minute=29)
    fresh_now = NOW.replace(hour=13, minute=31)
    e.clock = lambda: fresh_now
    premarket_quote = quote(as_of=premarket)
    premarket_quote.fetched_at = fresh_now
    result = e.execute(side='buy', symbol='AAPL', quantity='1', client_order_id='premarket',
                       rationale='', quotes={'AAPL': premarket_quote}, generation=1)
    assert result['error']['code'] == 'invalid_quote'
    assert D(e.state()['cash']) == 1000


def test_quotes_for_other_holdings_required(tmp_path):
    e = make_engine(tmp_path)
    assert trade(e)['ok']
    assert trade(e, symbol='MSFT', key='second')['error']['code'] == 'state_changed'
    assert D(e.state()['cash']) == 900


def test_corporate_action_error_blocks_trade_and_performance(tmp_path):
    s = service(tmp_path)
    assert s.buy('AAPL','1','first')['ok']
    def split(symbol, since):
        raise ValueError('Split needs reconciliation')
    s.provider.check_corporate_actions = split
    assert s.sell('AAPL','1','sell')['ok'] is False
    assert s.get_performance()['ok'] is False
    assert D(s.engine.state()['positions']['AAPL']['quantity']) == 1


@pytest.mark.parametrize('variable,value', [('PAPER_MODE','false'), ('LIVE_TRADING_ENABLED','true'),('ALPACA_API_KEY','dummy'),
                                          ('PAPER_FEE_RATE','NaN'),('PAPER_MAX_TOTAL_PCT','1.1')])
def test_forbidden_or_invalid_configuration(monkeypatch, variable, value):
    from app.core.config import Settings
    monkeypatch.setenv(variable,value)
    with pytest.raises(ValueError):
        Settings.from_env()


def test_invalid_pagination_is_explicit_failure(tmp_path):
    s = service(tmp_path)
    assert s.get_orders(limit=0)['error']['code'] == 'invalid_limit'
    assert s.get_orders(offset=-1)['error']['code'] == 'invalid_offset'


def test_supplying_nan_quantity_never_escapes_as_exception(tmp_path):
    s = service(tmp_path)
    assert s.buy('AAPL', float('nan'), 'nan')['error']['code'] == 'invalid_quantity'
    assert s.sell('AAPL', float('inf'), 'inf')['error']['code'] == 'invalid_quantity'


def test_valuation_missing_mark_is_explicit_not_zero(tmp_path):
    e = make_engine(tmp_path)
    assert trade(e)['ok']
    with pytest.raises(PaperError, match='Holdings changed'):
        e.valuate({},1)
