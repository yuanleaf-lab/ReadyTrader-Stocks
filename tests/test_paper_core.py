from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from decimal import Decimal as D
from types import SimpleNamespace

import pytest

from core.paper import PaperTradingEngine
from core.risk import RiskLimits

NOW = datetime(2026, 9, 17, 15, 0, tzinfo=timezone.utc)


def make_engine(tmp_path, **options):
    options.setdefault('limits', RiskLimits(D(1), D(1), D(1)))
    return PaperTradingEngine(str(tmp_path / 'paper.db'), initial_cash='1000',
                              fixed_fee='0', fee_rate='0', slippage_bps='0',
                              clock=lambda: NOW, **options)


def quote(price='100', as_of=NOW, symbol='AAPL'):
    return SimpleNamespace(symbol=symbol, price=D(price), as_of=as_of, fetched_at=NOW)


def trade(engine, side='buy', quantity='1', key='one', price='100', symbol='AAPL'):
    return engine.execute(side=side, symbol=symbol, quantity=quantity, client_order_id=key,
                          rationale='test thesis', quotes={symbol: quote(price, symbol=symbol)},
                          generation=engine.state()['generation'])


def test_initialization_and_restart_never_refund(tmp_path):
    engine = make_engine(tmp_path)
    assert engine.state()['cash'] == '1000.00000000'
    assert trade(engine)['ok']
    restarted = PaperTradingEngine(str(tmp_path / 'paper.db'), initial_cash='90000', clock=lambda: NOW)
    assert restarted.state()['cash'] == '900.00000000'
    assert restarted.state()['initial_cash'] == '1000.00000000'


def test_fractional_buy_and_no_intermediate_drawdown(tmp_path):
    engine = make_engine(tmp_path)
    assert trade(engine, quantity='0.125')['ok']
    state = engine.state()
    assert state['cash'] == '987.50000000'
    assert state['positions']['AAPL']['quantity'] == '0.12500000'
    portfolio = engine.valuate({'AAPL': quote()}, state['generation'])
    assert portfolio['equity'] == '1000.00000000'
    assert D(engine.performance()['max_drawdown_pct']) == 0
    assert all(D(p['equity']) == 1000 for p in engine.performance()['equity_curve'])


def test_partial_and_full_sell_pnl(tmp_path):
    e = make_engine(tmp_path)
    assert trade(e, quantity='2')['ok']
    assert trade(e, side='sell', quantity='0.5', price='120', key='sell1')['ok']
    p = e.valuate({'AAPL': quote('120')}, e.state()['generation'])
    assert D(p['cash']) == 860
    assert D(p['realized_pnl']) == 10
    assert D(p['unrealized_pnl']) == 30
    assert D(p['equity']) == 1040
    assert trade(e, side='sell', quantity='1.5', price='120', key='sell2')['ok']
    assert e.state()['positions'] == {}
    assert D(e.state()['cash']) == 1040
    assert D(e.performance()['realized_pnl']) == 40


@pytest.mark.parametrize('quantity', ['0', '-1', 'NaN', 'Infinity', '-Infinity', '1e9999', '0.000000001'])
def test_invalid_quantity_cannot_mutate(tmp_path, quantity):
    e = make_engine(tmp_path)
    assert trade(e, quantity=quantity)['ok'] is False
    assert e.state()['cash'] == '1000.00000000'
    assert e.state()['positions'] == {}


@pytest.mark.parametrize('side,quantity,code', [('buy', '11', 'insufficient_cash'), ('sell', '1', 'insufficient_position')])
def test_insufficient_balances_are_failures(tmp_path, side, quantity, code):
    e = make_engine(tmp_path)
    result = trade(e, side=side, quantity=quantity)
    assert result['ok'] is False
    assert result['error']['code'] == code
    assert e.state()['cash'] == '1000.00000000'


def test_fee_slippage_and_cost_basis(tmp_path):
    e = PaperTradingEngine(str(tmp_path / 'paper.db'), initial_cash='1000', fixed_fee='1',
                           fee_rate='0.001', slippage_bps='10', clock=lambda: NOW, limits=RiskLimits(D(1), D(1), D(1)))
    buy = trade(e, quantity='2')['data']
    assert D(buy['fill_price']) == D('100.1')
    assert D(buy['fee']) == D('1.2002')
    assert D(buy['slippage_cost']) == D('0.2')
    assert D(e.state()['cash']) == D('798.5998')
    assert D(e.state()['positions']['AAPL']['cost_basis']) == D('201.4002')
    sell = trade(e, side='sell', quantity='2', price='110', key='sell')['data']
    assert D(sell['fill_price']) == D('109.89')
    assert D(sell['realized_pnl']) == D('17.16002')
    assert D(e.state()['cash']) == D('1017.16002')


def test_fee_can_make_buy_unaffordable(tmp_path):
    e = PaperTradingEngine(str(tmp_path / 'paper.db'), initial_cash='100', fixed_fee='0.01',
                           fee_rate='0', slippage_bps='0', clock=lambda: NOW, limits=RiskLimits(D(1), D(1), D(1)))
    assert trade(e)['error']['code'] == 'insufficient_cash'
    assert D(e.state()['cash']) == 100


def test_replay_is_persistent_and_conflicting_request_rejected(tmp_path):
    e = make_engine(tmp_path)
    first = trade(e)
    assert trade(e) == first
    e2 = make_engine(tmp_path)
    assert trade(e2) == first
    assert trade(e2, quantity='2')['error']['code'] == 'idempotency_conflict'
    assert len(e2.orders()) == 1


def test_stale_quote_and_invalid_side(tmp_path):
    e = make_engine(tmp_path)
    stale = e.execute(side='buy', symbol='AAPL', quantity='1', client_order_id='stale', rationale='',
                      quotes={'AAPL': quote(as_of=NOW-timedelta(minutes=5))}, generation=1)
    assert stale['error']['code'] == 'stale_quote'
    assert trade(e, side='short')['ok'] is False


def test_max_drawdown_is_peak_to_trough(tmp_path):
    e = make_engine(tmp_path)
    assert trade(e, quantity='5')['ok']
    e.valuate({'AAPL': quote('120')}, 1)
    e.valuate({'AAPL': quote('80')}, 1)
    p = e.performance()
    assert D(p['equity']) == 900
    assert abs(D(p['max_drawdown_pct']) - D('0.181818181818181818')) < D('0.000000001')
    e.valuate({'AAPL': quote('140')}, 1)
    assert D(e.performance()['current_drawdown_pct']) == 0
    assert D(e.performance()['max_drawdown_pct']) > 0


def test_concurrent_cash_cannot_be_spent_twice(tmp_path):
    e = make_engine(tmp_path)
    def submit(i):
        return trade(make_engine(tmp_path), quantity='6', key=str(i))
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(submit, [1, 2]))
    assert sum(r['ok'] for r in results) == 1
    assert D(e.state()['cash']) == 400
    assert D(e.state()['positions']['AAPL']['quantity']) == 6


def test_concurrent_same_key_fills_once(tmp_path):
    e = make_engine(tmp_path)
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(lambda _: trade(e), range(4)))
    assert all(r == results[0] for r in results)
    assert len(e.orders()) == 1
    assert D(e.state()['cash']) == 900


def test_reset_requires_one_use_authorization_and_retains_principal(tmp_path):
    e = make_engine(tmp_path)
    prior = trade(e)
    assert e.reset('invented')['ok'] is False
    token = e.authorize_reset()
    assert e.reset(token)['ok'] is True
    assert e.reset(token)['ok'] is False
    assert e.state()['generation'] == 2
    assert D(e.state()['cash']) == 1000
    assert trade(e) == prior
    assert e.state()['positions'] == {}
    assert len(e.orders(generation=1)) == 1


def test_failed_write_rolls_back_entire_trade(tmp_path):
    import sqlite3
    e = make_engine(tmp_path)
    with sqlite3.connect(e.db_path) as conn:
        conn.execute("CREATE TRIGGER fail_order BEFORE INSERT ON orders BEGIN SELECT RAISE(ABORT, 'disk failure'); END")
    assert trade(e)['ok'] is False
    assert D(e.state()['cash']) == 1000
    assert e.state()['positions'] == {}


def test_legacy_database_not_silently_reinterpreted(tmp_path):
    import sqlite3
    with sqlite3.connect(tmp_path / 'paper.db') as conn:
        conn.execute('CREATE TABLE balances(user_id TEXT, asset TEXT, amount REAL)')
        conn.execute("INSERT INTO balances VALUES ('agent_zero','USD',12)")
    with pytest.raises(ValueError, match='legacy'):
        make_engine(tmp_path)
