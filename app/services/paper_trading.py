"""The only application trade route: common stocks -> regular hours -> paper ledger."""
import logging
import threading
from datetime import datetime
from decimal import Decimal

from core.values import PaperError, aware, failure
from marketdata.calendar import USMarketCalendar

logger = logging.getLogger(__name__)


class PaperTradingService:
    def __init__(self, engine, provider):
        self.engine = engine
        self.provider = provider
        if self.engine.calendar is None:
            self.engine.calendar = USMarketCalendar()
        self._stop = threading.Event()
        self._sampler = None

    def _collect_quotes(self, state, extra=()):
        quotes = {}
        for symbol in sorted(set(state['positions']) | set(extra)):
            holding = state['positions'].get(symbol)
            if holding:
                self.provider.check_corporate_actions(symbol, datetime.fromisoformat(holding['opened_at']))
            quotes[symbol] = self.provider.fetch_quote(symbol)
        return quotes

    def buy(self, symbol, quantity, client_order_id, rationale=''):
        return self._trade('buy', symbol, quantity, client_order_id, rationale)

    def sell(self, symbol, quantity, client_order_id, rationale=''):
        return self._trade('sell', symbol, quantity, client_order_id, rationale)

    def _trade(self, side, symbol, quantity, client_order_id, rationale):
        try:
            request = self.engine.request(side, symbol, quantity, client_order_id, rationale)
            replay = self.engine.replay(request)
            if replay is not None:
                return replay
            state = self.engine.state()
            generation = state['generation']
            for _ in range(3):
                if not self.engine.calendar.is_open(aware(self.engine.clock())):
                    return self.engine.reject(request, generation, 'market_closed', 'Only US regular-session execution is supported.')
                try:
                    quotes = self._collect_quotes(state, (request['symbol'],))
                except ValueError as exc:
                    return self.engine.reject(request, generation, 'market_data_error', str(exc))
                except Exception:
                    return self.engine.reject(request, generation, 'market_data_unavailable', 'Unable to obtain validated market data.')
                result = self.engine.execute(side=side, symbol=request['symbol'], quantity=request['quantity'],
                                             client_order_id=client_order_id, rationale=rationale, quotes=quotes, generation=generation)
                if result.get('error', {}).get('code') != 'state_changed':
                    return result
                state = self.engine.state()
                if state['generation'] != generation:
                    return failure('account_changed', 'Account was reset; request was not executed.')
            return failure('state_changed', 'Concurrent holdings changes prevented valuation. Retry the same request ID.')
        except PaperError as exc:
            return failure(exc.code, exc.message)
        except Exception:
            logger.exception('Paper request failed before confirmed execution')
            return failure('service_error', 'Request could not be confirmed. Retry with the same client_order_id.')

    def _valuation(self):
        for _ in range(3):
            state = self.engine.state()
            quotes = self._collect_quotes(state)
            try:
                return self.engine.valuate(quotes, state['generation'])
            except PaperError as exc:
                if exc.code != 'state_changed':
                    raise
        raise PaperError('state_changed', 'Could not obtain a coherent portfolio valuation.')

    @staticmethod
    def _read(operation):
        try:
            return {'ok': True, 'data': operation()}
        except PaperError as exc:
            return failure(exc.code, exc.message)
        except ValueError as exc:
            return failure('market_data_error', str(exc))
        except Exception:
            logger.exception('Paper query failed')
            return failure('query_error', 'Unable to complete the query; no partial valuation was substituted.')

    def get_portfolio(self):
        return self._read(self._valuation)

    def get_cash_balance(self):
        def read():
            state = self.engine.state()
            return {'currency': 'USD', 'cash': state['cash'], 'initial_cash': state['initial_cash'], 'generation': state['generation']}
        return self._read(read)

    def get_orders(self, limit=100, offset=0, generation=None):
        return self._read(lambda: {'orders': self.engine.orders(limit, offset, generation=generation)})

    def get_trade_history(self, limit=100, offset=0, generation=None):
        return self._read(lambda: {'trades': self.engine.orders(limit, offset, generation=generation, filled_only=True)})

    def get_performance(self, curve_limit=500):
        def read():
            portfolio = self._valuation()
            metrics = self.engine.performance(curve_limit)
            if metrics['generation'] != portfolio['generation']:
                raise PaperError('account_changed', 'Account reset during performance query.')
            # A stale (typically closed-session) quote remains explicitly stale;
            # do not append it to the drawdown curve as a fresh observation.
            return {**metrics, 'latest_reference_valuation': portfolio,
                    'stale': portfolio['stale'], 'excludes_dividends': True,
                    'sampling': 'on trades, fresh queries and every 300 seconds while the local MCP is running in regular hours'}
        return self._read(read)

    def get_risk_status(self):
        def read():
            portfolio = self._valuation()
            equity = Decimal(portfolio['equity'])
            return {'mode': 'paper', 'equity': portfolio['equity'], 'stale': portfolio['stale'],
                    'market_open': self.engine.calendar.is_open(aware(self.engine.clock())),
                    'limits': self.engine.risk.status(),
                    'total_position_pct': str(Decimal(portfolio['market_value'])/equity if equity else 0),
                    'positions': [{'symbol': p['symbol'], 'equity_fraction': str(Decimal(p['market_value'])/equity if equity else 0)}
                                  for p in portfolio['positions']],
                    'shorting': False, 'leverage': False, 'options': False}
        return self._read(read)

    def reset_paper_account(self, authorization):
        return self.engine.reset(authorization)

    def start_sampling(self, interval=300):
        if self._sampler and self._sampler.is_alive():
            return
        self._stop.clear()
        def sample():
            while not self._stop.wait(interval):
                try:
                    if self.engine.calendar.is_open(aware(self.engine.clock())):
                        self._valuation()
                except Exception:
                    logger.warning('Equity sampling unavailable; leaving an explicit gap (no synthetic sample).')
        self._sampler = threading.Thread(target=sample, name='paper-equity-sampler', daemon=True)
        self._sampler.start()

    def stop_sampling(self):
        self._stop.set()
        if self._sampler:
            self._sampler.join(timeout=1)
