"""Paper-only SQLite ledger. All monetary values are canonical Decimal TEXT.

No network calls happen inside a transaction. The service supplies validated
quotes, and the ledger rechecks freshness, holdings and risk while holding the
SQLite write lock. No brokerage, deposit or limit-order entrypoint exists.
"""
import hashlib
import json
import secrets
import sqlite3
from contextlib import contextmanager
from datetime import timedelta
from decimal import Decimal, localcontext
from pathlib import Path

from core.risk import RiskGuardian
from core.values import ZERO, PaperError, aware, failure, money, number, text, utcnow


class PaperTradingEngine:
    def __init__(self, db_path='data/paper.db', *, initial_cash='10000', fixed_fee='0.01',
                 fee_rate='0.0001', slippage_bps='5', limits=None, quote_max_age=180,
                 clock=utcnow, calendar=None):
        self.db_path = str(db_path)
        self.clock = clock
        self.calendar = calendar
        self.fixed_fee = number(fixed_fee, 'fixed_fee', exact=True)
        self.fee_rate = number(fee_rate, 'fee_rate')
        self.slippage_bps = number(slippage_bps, 'slippage_bps')
        if self.fee_rate > 1 or self.slippage_bps >= 10000:
            raise ValueError('fee_rate must be <=1 and slippage_bps <10000.')
        if not isinstance(quote_max_age, int) or not 1 <= quote_max_age <= 900:
            raise ValueError('quote_max_age must be 1..900 seconds.')
        self.quote_max_age = quote_max_age
        self.risk = RiskGuardian(limits)
        capital = number(initial_cash, 'initial_cash', positive=True, exact=True)
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self._initialize(capital)

    @contextmanager
    def _connection(self, write=False):
        conn = sqlite3.connect(self.db_path, timeout=15, isolation_level=None)
        conn.row_factory = sqlite3.Row
        conn.execute('PRAGMA busy_timeout=15000')
        conn.execute('PRAGMA foreign_keys=ON')
        try:
            conn.execute('BEGIN IMMEDIATE' if write else 'BEGIN')
            yield conn
            conn.commit()
        except BaseException:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _initialize(self, capital):
        with sqlite3.connect(self.db_path, timeout=15) as conn:
            conn.execute('PRAGMA journal_mode=WAL')
        with self._connection(True) as conn:
            tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            if 'accounts' not in tables and tables & {'balances', 'orders', 'equity_snapshots'}:
                raise ValueError('legacy paper database detected; preserve it and use a new database. Explicit audited migration is required.')
            version = conn.execute('PRAGMA user_version').fetchone()[0]
            if version not in (0, 1):
                raise ValueError('Unsupported paper database version.')
            for statement in (
                '''CREATE TABLE IF NOT EXISTS accounts (
                    generation INTEGER PRIMARY KEY, initial_cash TEXT NOT NULL, cash TEXT NOT NULL,
                    realized_pnl TEXT NOT NULL, fees TEXT NOT NULL, slippage TEXT NOT NULL,
                    created_at TEXT NOT NULL, active INTEGER NOT NULL CHECK(active IN (0,1)))''',
                'CREATE UNIQUE INDEX IF NOT EXISTS one_active_account ON accounts(active) WHERE active=1',
                '''CREATE TABLE IF NOT EXISTS balances (
                    generation INTEGER NOT NULL REFERENCES accounts(generation), symbol TEXT NOT NULL,
                    quantity TEXT NOT NULL, cost_basis TEXT NOT NULL, opened_at TEXT NOT NULL,
                    PRIMARY KEY(generation,symbol))''',
                '''CREATE TABLE IF NOT EXISTS orders (
                    id INTEGER PRIMARY KEY AUTOINCREMENT, client_order_id TEXT UNIQUE NOT NULL,
                    generation INTEGER NOT NULL REFERENCES accounts(generation), request_hash TEXT NOT NULL,
                    timestamp TEXT NOT NULL, side TEXT NOT NULL, symbol TEXT NOT NULL,
                    quantity TEXT NOT NULL, rationale TEXT NOT NULL, status TEXT NOT NULL,
                    response TEXT NOT NULL)''',
                '''CREATE TABLE IF NOT EXISTS equity_snapshots (
                    id INTEGER PRIMARY KEY AUTOINCREMENT, generation INTEGER NOT NULL REFERENCES accounts(generation),
                    timestamp TEXT NOT NULL, equity TEXT NOT NULL, portfolio TEXT NOT NULL)''',
                '''CREATE TABLE IF NOT EXISTS asset_prices (
                    symbol TEXT PRIMARY KEY, price TEXT NOT NULL, as_of TEXT NOT NULL, fetched_at TEXT NOT NULL)''',
                '''CREATE TABLE IF NOT EXISTS reset_authorizations (
                    token_hash TEXT PRIMARY KEY, generation INTEGER NOT NULL REFERENCES accounts(generation),
                    expires_at TEXT NOT NULL, used INTEGER NOT NULL DEFAULT 0)''',
                'CREATE INDEX IF NOT EXISTS snapshots_generation ON equity_snapshots(generation,id)',
                'CREATE INDEX IF NOT EXISTS orders_generation ON orders(generation,id)',
            ):
                conn.execute(statement)
            if not conn.execute('SELECT 1 FROM accounts').fetchone():
                conn.execute('INSERT INTO accounts VALUES (1,?,?,?,?,?,?,1)',
                             (text(capital), text(capital), text(0), text(0), text(0), aware(self.clock()).isoformat()))
                self._snapshot(conn, self._state(conn), {}, self.clock())
            elif not conn.execute('SELECT 1 FROM accounts WHERE active=1').fetchone():
                raise ValueError('Database has no active account; refusing to initialize funds again.')
            conn.execute('PRAGMA user_version=1')

    def _state(self, conn):
        account = dict(conn.execute('SELECT * FROM accounts WHERE active=1').fetchone())
        account['positions'] = {r['symbol']: dict(r) for r in conn.execute(
            'SELECT * FROM balances WHERE generation=?', (account['generation'],))}
        return account

    def state(self):
        with self._connection() as conn:
            return self._state(conn)

    def request(self, side, symbol, quantity, client_order_id, rationale):
        if side not in ('buy', 'sell'):
            raise PaperError('invalid_side', 'Only buy and sell are supported.')
        # Metadata-based eligibility is enforced by the service/provider; this
        # syntax gate independently prevents currency pairs and cash-as-stock.
        import re
        if not isinstance(symbol, str):
            raise PaperError('invalid_symbol', 'Stock symbol is required.')
        symbol = symbol.strip().upper()
        if not re.fullmatch(r'[A-Z]{1,5}(?:-[A-Z])?', symbol) or symbol == 'USD':
            raise PaperError('invalid_symbol', 'Use a US common-stock ticker, not a pair or derivative.')
        qty = number(quantity, 'quantity', positive=True, exact=True)
        if not isinstance(client_order_id, str) or not re.fullmatch(r'[A-Za-z0-9_.:-]{1,100}', client_order_id):
            raise PaperError('invalid_client_order_id', 'client_order_id must be 1..100 safe identifier characters.')
        if not isinstance(rationale, str) or len(rationale) > 2000:
            raise PaperError('invalid_rationale', 'rationale must be text, at most 2000 characters.')
        request = {'side': side, 'symbol': symbol, 'quantity': text(qty),
                   'client_order_id': client_order_id, 'rationale': rationale}
        request['request_hash'] = hashlib.sha256(json.dumps(request, sort_keys=True).encode()).hexdigest()
        return request

    def _replay(self, conn, request):
        row = conn.execute('SELECT request_hash,response FROM orders WHERE client_order_id=?',
                           (request['client_order_id'],)).fetchone()
        if row:
            if row['request_hash'] != request['request_hash']:
                return failure('idempotency_conflict', 'client_order_id already identifies a different request.')
            return json.loads(row['response'])
        return None

    def replay(self, request):
        with self._connection() as conn:
            return self._replay(conn, request)

    def _record(self, conn, request, generation, result, now):
        cursor = conn.execute('''INSERT INTO orders
            (client_order_id,generation,request_hash,timestamp,side,symbol,quantity,rationale,status,response)
            VALUES (?,?,?,?,?,?,?,?,?,?)''',
            (request['client_order_id'], generation, request['request_hash'], aware(now).isoformat(),
             request['side'], request['symbol'], request['quantity'], request['rationale'],
             'filled' if result['ok'] else 'rejected', json.dumps(result)))
        if result['ok']:
            result['data']['order_id'] = cursor.lastrowid
        else:
            result['error']['order_id'] = cursor.lastrowid
        conn.execute('UPDATE orders SET response=? WHERE id=?', (json.dumps(result), cursor.lastrowid))
        return result

    def reject(self, request, generation, code, message):
        try:
            with self._connection(True) as conn:
                replay = self._replay(conn, request)
                if replay is not None:
                    return replay
                if self._state(conn)['generation'] != generation:
                    return failure('account_changed', 'Account was reset; submit a new request explicitly.')
                return self._record(conn, request, generation, failure(code, message), self.clock())
        except sqlite3.Error:
            return failure('storage_error', 'Could not persist request; retry with the same client_order_id.')

    def _quotes(self, state, quotes, now, *, fresh, extra=()):
        needed = set(state['positions']) | set(extra)
        if not needed <= quotes.keys():
            raise PaperError('state_changed', 'Holdings changed during quote collection; fetch all quotes again.')
        marks = {}
        for symbol in needed:
            q = quotes[symbol]
            if q.symbol != symbol:
                raise PaperError('invalid_quote', 'Quote symbol does not match holding.')
            px = number(q.price, 'price', positive=True)
            source_time, fetched = aware(q.as_of), aware(q.fetched_at)
            age = (aware(now) - source_time).total_seconds()
            if age < -5 or fetched > aware(now) + timedelta(seconds=5) or source_time > fetched + timedelta(seconds=5):
                raise PaperError('invalid_quote', 'Quote has an invalid future timestamp.')
            if fresh and (age > self.quote_max_age or (aware(now)-fetched).total_seconds() > self.quote_max_age):
                raise PaperError('stale_quote', 'Reference quote is too old for execution.')
            if fresh and source_time.astimezone(__import__('zoneinfo').ZoneInfo('America/New_York')).date() != aware(now).astimezone(
                    __import__('zoneinfo').ZoneInfo('America/New_York')).date():
                raise PaperError('stale_quote', 'Quote is not from the current trading session.')
            if fresh:
                if self.calendar is None:
                    from marketdata.calendar import USMarketCalendar
                    self.calendar = USMarketCalendar()
                if not self.calendar.is_open(source_time):
                    raise PaperError('invalid_quote', 'Reference quote is outside the US regular trading session.')
            marks[symbol] = px
        return marks

    def _portfolio(self, state, quotes, marks, now):
        positions = []
        for symbol, holding in sorted(state['positions'].items()):
            qty, cost = Decimal(holding['quantity']), Decimal(holding['cost_basis'])
            value = money(qty * marks[symbol])
            positions.append({'symbol': symbol, 'quantity': text(qty), 'cost_basis': text(cost),
                              'average_cost': text(cost / qty), 'reference_price': str(marks[symbol]),
                              'market_value': text(value), 'unrealized_pnl': text(value-cost),
                              'quote_as_of': aware(quotes[symbol].as_of).isoformat()})
        gross = sum((Decimal(p['market_value']) for p in positions), ZERO)
        unrealized = sum((Decimal(p['unrealized_pnl']) for p in positions), ZERO)
        stale = any((aware(now)-aware(quotes[s].as_of)).total_seconds() > self.quote_max_age for s in state['positions'])
        return {'mode': 'paper', 'currency': 'USD', 'generation': state['generation'],
                'initial_cash': state['initial_cash'], 'cash': state['cash'], 'positions': positions,
                'market_value': text(gross), 'equity': text(Decimal(state['cash'])+gross),
                'realized_pnl': state['realized_pnl'], 'unrealized_pnl': text(unrealized),
                'fees': state['fees'], 'slippage_cost': state['slippage'],
                'valuation_at': aware(now).isoformat(), 'stale': stale,
                'valuation_basis': 'latest available regular-session reference prices; excludes dividends'}

    def _snapshot(self, conn, state, quotes, now):
        marks = self._quotes(state, quotes, now, fresh=False)
        portfolio = self._portfolio(state, quotes, marks, now)
        conn.execute('INSERT INTO equity_snapshots(generation,timestamp,equity,portfolio) VALUES(?,?,?,?)',
                     (state['generation'], aware(now).isoformat(), portfolio['equity'], json.dumps(portfolio)))
        for symbol, price in marks.items():
            q = quotes[symbol]
            conn.execute('INSERT OR REPLACE INTO asset_prices VALUES(?,?,?,?)',
                         (symbol, str(price), aware(q.as_of).isoformat(), aware(q.fetched_at).isoformat()))
        return portfolio

    def execute(self, *, side, symbol, quantity, client_order_id, rationale, quotes, generation):
        try:
            request = self.request(side, symbol, quantity, client_order_id, rationale)
        except PaperError as exc:
            return failure(exc.code, exc.message)
        try:
            with self._connection(True) as conn, localcontext() as ctx:
                ctx.prec = 50
                replay = self._replay(conn, request)
                if replay is not None:
                    return replay
                state = self._state(conn)
                if state['generation'] != generation:
                    return failure('account_changed', 'Account reset while obtaining quotes; request was not executed.')
                now = aware(self.clock())
                try:
                    if self.calendar is None:
                        from marketdata.calendar import USMarketCalendar
                        self.calendar = USMarketCalendar()
                    if not self.calendar.is_open(now):
                        raise PaperError('market_closed', 'Only the US regular trading session is supported.')
                    marks = self._quotes(state, quotes, now, fresh=True, extra=(request['symbol'],))
                    values = self._calculate(state, request, marks)
                except PaperError as exc:
                    if exc.code == 'state_changed':
                        return failure(exc.code, exc.message)
                    return self._record(conn, request, generation, failure(exc.code, exc.message), now)
                qty, cost, cash, pnl, fee, slippage, fill, gross = values
                sym = request['symbol']
                if qty == 0:
                    conn.execute('DELETE FROM balances WHERE generation=? AND symbol=?', (generation, sym))
                else:
                    opened = state['positions'].get(sym, {}).get('opened_at', now.isoformat())
                    conn.execute('INSERT OR REPLACE INTO balances VALUES(?,?,?,?,?)',
                                 (generation, sym, text(qty), text(cost), opened))
                conn.execute('UPDATE accounts SET cash=?,realized_pnl=?,fees=?,slippage=? WHERE generation=?',
                             (text(cash), text(Decimal(state['realized_pnl'])+pnl), text(Decimal(state['fees'])+fee),
                              text(Decimal(state['slippage'])+slippage), generation))
                data = {'mode': 'paper', 'status': 'filled', 'generation': generation,
                        'client_order_id': client_order_id, 'side': side, 'symbol': sym,
                        'quantity': request['quantity'], 'rationale': rationale,
                        'reference_price': str(marks[sym]), 'quote_as_of': aware(quotes[sym].as_of).isoformat(),
                        'fill_price': text(fill), 'gross_value': text(gross), 'fee': text(fee),
                        'slippage_cost': text(slippage), 'slippage_bps': str(self.slippage_bps),
                        'fixed_fee': str(self.fixed_fee), 'fee_rate': str(self.fee_rate),
                        'realized_pnl': text(pnl), 'cash_after': text(cash), 'filled_at': now.isoformat()}
                result = self._record(conn, request, generation, {'ok': True, 'data': data}, now)
                self._snapshot(conn, self._state(conn), quotes, now)
                return result
        except sqlite3.Error:
            return failure('storage_error', 'Transaction was not confirmed; retry with the same client_order_id.')

    def _calculate(self, state, request, marks):
        sym, side = request['symbol'], request['side']
        quantity = Decimal(request['quantity'])
        holding = state['positions'].get(sym, {})
        owned, cost = Decimal(holding.get('quantity', '0')), Decimal(holding.get('cost_basis', '0'))
        cash = Decimal(state['cash'])
        fill = money(marks[sym] * (1 + (self.slippage_bps / 10000) * (1 if side == 'buy' else -1)))
        gross = money(quantity * fill)
        if fill <= 0 or gross <= 0:
            raise PaperError('trade_too_small', 'Trade is below ledger monetary precision.')
        fee = money(self.fixed_fee + gross * self.fee_rate)
        slippage = money(abs(fill-marks[sym]) * quantity)
        pnl = ZERO
        if side == 'buy':
            if cash < gross + fee:
                raise PaperError('insufficient_cash', 'Cash does not cover the fill and all fees.')
            cash -= gross + fee
            new_qty, new_cost = owned+quantity, cost+gross+fee
            total_before = sum((money(Decimal(p['quantity'])*marks[s]) for s, p in state['positions'].items()), ZERO)
            equity_before = Decimal(state['cash']) + total_before
            symbol_value = money(new_qty * marks[sym])
            total_after = total_before - money(owned * marks[sym]) + symbol_value
            self.risk.validate_buy(equity_before=equity_before, equity_after=cash+total_after,
                                   trade_value=gross+fee, symbol_value=symbol_value, total_value=total_after)
        else:
            if owned < quantity:
                raise PaperError('insufficient_position', 'Cannot sell more than the owned shares.')
            if cash + gross - fee < 0:
                raise PaperError('insufficient_cash', 'Cash and sale proceeds do not cover fees.')
            allocated_cost = cost if quantity == owned else money(cost * quantity / owned)
            new_qty, new_cost = owned-quantity, cost-allocated_cost
            cash += gross-fee
            pnl = gross-fee-allocated_cost
        return new_qty, new_cost, cash, pnl, fee, slippage, fill, gross

    def valuate(self, quotes, generation, *, fresh=False, snapshot=True):
        with self._connection(True) as conn, localcontext() as ctx:
            ctx.prec = 50
            state = self._state(conn)
            if generation != state['generation']:
                raise PaperError('account_changed', 'Account was reset during valuation.')
            now = aware(self.clock())
            marks = self._quotes(state, quotes, now, fresh=fresh)
            result = self._portfolio(state, quotes, marks, now)
            # Stale marks can be displayed explicitly, never added as new curve observations.
            if snapshot and not result['stale']:
                self._snapshot(conn, state, quotes, now)
            return result

    def orders(self, limit=100, offset=0, *, generation=None, filled_only=False):
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 500:
            raise PaperError('invalid_limit', 'limit must be 1..500.')
        if isinstance(offset, bool) or not isinstance(offset, int) or offset < 0:
            raise PaperError('invalid_offset', 'offset must be nonnegative.')
        with self._connection() as conn:
            generation = generation if generation is not None else self._state(conn)['generation']
            suffix = " AND status='filled'" if filled_only else ''
            rows = conn.execute('SELECT * FROM orders WHERE generation=?'+suffix+' ORDER BY id DESC LIMIT ? OFFSET ?',
                                (generation, limit, offset))
            return [{**dict(row), 'response': json.loads(row['response'])} for row in rows]

    def performance(self, curve_limit=500):
        if not isinstance(curve_limit, int) or not 1 <= curve_limit <= 1000:
            raise PaperError('invalid_limit', 'curve_limit must be 1..1000.')
        with self._connection() as conn, localcontext() as ctx:
            ctx.prec = 50
            state = self._state(conn)
            rows = list(conn.execute('SELECT * FROM equity_snapshots WHERE generation=? ORDER BY id', (state['generation'],)))
            peak, max_dd = ZERO, ZERO
            for row in rows:
                eq = Decimal(row['equity'])
                peak = max(peak, eq)
                max_dd = max(max_dd, (peak-eq)/peak if peak else ZERO)
            latest = json.loads(rows[-1]['portfolio'])
            equity = Decimal(latest['equity'])
            return {**latest, 'current_drawdown_pct': str((peak-equity)/peak if peak else ZERO),
                    'max_drawdown_pct': str(max_dd), 'total_pnl': text(equity-Decimal(state['initial_cash'])),
                    'return_pct': str((equity-Decimal(state['initial_cash']))/Decimal(state['initial_cash'])),
                    'sample_count': len(rows), 'drawdown_basis': 'observed complete equity snapshots, not continuous market history',
                    'equity_curve': [{'timestamp': r['timestamp'], 'equity': r['equity']} for r in rows[-curve_limit:]]}

    def authorize_reset(self, ttl_seconds=300):
        if not isinstance(ttl_seconds, int) or not 1 <= ttl_seconds <= 600:
            raise ValueError('Reset authorization TTL must be 1..600 seconds.')
        token = secrets.token_urlsafe(32)
        with self._connection(True) as conn:
            state = self._state(conn)
            conn.execute('INSERT INTO reset_authorizations VALUES(?,?,?,0)',
                         (hashlib.sha256(token.encode()).hexdigest(), state['generation'],
                          (aware(self.clock())+timedelta(seconds=ttl_seconds)).isoformat()))
        return token

    def reset(self, authorization):
        if not isinstance(authorization, str) or len(authorization) > 200:
            return failure('reset_not_authorized', 'A one-use server-issued reset authorization is required.')
        try:
            with self._connection(True) as conn:
                state = self._state(conn)
                token_hash = hashlib.sha256(authorization.encode()).hexdigest()
                row = conn.execute('SELECT * FROM reset_authorizations WHERE token_hash=?', (token_hash,)).fetchone()
                now = aware(self.clock()).isoformat()
                if not row or row['used'] or row['generation'] != state['generation'] or row['expires_at'] <= now:
                    return failure('reset_not_authorized', 'Reset authorization is missing, expired, used or belongs to an old account cycle.')
                conn.execute('UPDATE reset_authorizations SET used=1 WHERE generation=?', (state['generation'],))
                conn.execute('UPDATE accounts SET active=0 WHERE active=1')
                generation = state['generation']+1
                capital = state['initial_cash']
                conn.execute('INSERT INTO accounts VALUES(?,?,?,?,?,?,?,1)',
                             (generation, capital, capital, text(0), text(0), text(0), now))
                self._snapshot(conn, self._state(conn), {}, self.clock())
                return {'ok': True, 'data': {'generation': generation, 'initial_cash': capital,
                                             'history': 'Previous account cycles retained.'}}
        except sqlite3.Error:
            return failure('storage_error', 'Reset could not be confirmed; inspect account state before authorizing another reset.')
