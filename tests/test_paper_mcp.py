import importlib
import json
import os
import socket
import subprocess
import sys
import time
from pathlib import Path
from urllib.request import Request, urlopen

import pytest

EXPECTED = {'get_stock_price', 'get_stock_history', 'search_symbol', 'get_portfolio', 'get_cash_balance',
            'buy', 'sell', 'get_orders', 'get_trade_history', 'get_performance', 'get_risk_status', 'reset_paper_account'}


@pytest.mark.asyncio
async def test_exact_mcp_tools_and_no_external_execution_parameters():
    module = importlib.import_module('app.main')
    tools = await module.mcp.get_tools()
    assert set(tools) == EXPECTED
    for name in ('buy', 'sell'):
        parameters = tools[name].parameters['properties']
        assert set(parameters) == {'symbol', 'quantity', 'client_order_id', 'rationale'}
    assert set(tools['reset_paper_account'].parameters['properties']) == {'authorization'}


@pytest.mark.parametrize('module', ['execution.alpaca_service', 'execution.tradier_service', 'execution.ibkr_service',
                                  'execution.retail_services', 'marketdata.ws_streams', 'app.api_server'])
def test_old_execution_modules_cannot_be_imported(module):
    with pytest.raises(RuntimeError, match='[Pp]aper'):
        importlib.import_module(module)


def test_mcp_import_does_not_create_account_or_load_brokers(tmp_path):
    env = dict(os.environ, PAPER_DB_PATH=str(tmp_path/'untouched.db'))
    result = subprocess.run([sys.executable, '-c',
        "import sys; import app.main; assert not any(n.startswith(('execution.', 'intelligence.', 'strategy.')) for n in sys.modules)"],
        env=env, capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr
    assert not (tmp_path/'untouched.db').exists()


@pytest.mark.asyncio
async def test_mcp_real_engine_buy_failure_and_query(tmp_path):
    from fastmcp import Client

    from app.main import create_mcp
    from tests.test_paper_service import service
    s = service(tmp_path)
    async with Client(create_mcp(s, sampling=False)) as client:
        tools = await client.list_tools()
        assert {t.name for t in tools} == EXPECTED
        result = await client.call_tool('buy', {'symbol':'AAPL', 'quantity':'0.25', 'client_order_id':'mcp', 'rationale':'test'})
        assert result.data['ok'] is True
        failed = await client.call_tool('sell', {'symbol':'AAPL', 'quantity':'1', 'client_order_id':'bad'})
        assert failed.data['ok'] is False
        cash = await client.call_tool('get_cash_balance', {})
        assert cash.data['data']['cash'] == '975.00000000'


@pytest.mark.asyncio
async def test_market_data_outage_has_a_specific_mcp_failure(tmp_path):
    from fastmcp import Client

    from app.main import create_mcp
    from tests.test_paper_service import service
    s = service(tmp_path)
    s.provider.fetch_quote = lambda _symbol: (_ for _ in ()).throw(RuntimeError('upstream unavailable'))
    async with Client(create_mcp(s, sampling=False)) as client:
        result = await client.call_tool('get_stock_price', {'symbol': 'AAPL'})
        assert result.data['ok'] is False
        assert result.data['error']['code'] == 'market_data_unavailable'


def test_real_http_process_starts_streamable_mcp_and_preserves_initial_funds(tmp_path):
    db = str(tmp_path / 'stdio.db')
    with socket.socket() as listener:
        listener.bind(('127.0.0.1', 0))
        port = listener.getsockname()[1]
    for initial in ('1234', '999999'):
        env = dict(os.environ, PAPER_DB_PATH=db, PAPER_INITIAL_CASH=initial, PORT=str(port))
        process = subprocess.Popen([sys.executable, '-m', 'app.main'], cwd=Path(__file__).resolve().parents[1], env=env,
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        try:
            deadline = time.monotonic() + 15
            while True:
                if process.poll() is not None:
                    _out, err = process.communicate(timeout=1)
                    pytest.fail(f'HTTP MCP exited during startup: {err}')
                try:
                    with urlopen(f'http://127.0.0.1:{port}/health', timeout=1) as response:
                        assert response.status == 200
                        break
                except OSError:
                    if time.monotonic() >= deadline:
                        pytest.fail('HTTP MCP did not expose /health within 15 seconds.')
                    time.sleep(.1)
            endpoint = f'http://127.0.0.1:{port}/mcp'

            def rpc(payload, session_id=None):
                headers = {'Accept': 'application/json, text/event-stream', 'Content-Type': 'application/json'}
                if session_id:
                    headers['Mcp-Session-Id'] = session_id
                request = Request(endpoint, data=json.dumps(payload).encode(), headers=headers, method='POST')
                with urlopen(request, timeout=10) as response:
                    return response.status, json.loads(response.read()), response.headers

            status, initialized, headers = rpc({
                'jsonrpc': '2.0', 'id': 1, 'method': 'initialize',
                'params': {'protocolVersion': '2025-03-26', 'capabilities': {},
                           'clientInfo': {'name': 'process-test', 'version': '1.0'}},
            })
            assert status == 200
            session_id = headers['Mcp-Session-Id']
            assert initialized['result']['serverInfo']['name'] == 'ReadyTrader-Paper'
            assert rpc({'jsonrpc': '2.0', 'method': 'notifications/initialized'}, session_id)[0] == 202
            assert {tool['name'] for tool in rpc({'jsonrpc': '2.0', 'id': 2, 'method': 'tools/list'}, session_id)[1]['result']['tools']} == EXPECTED
            result = rpc({'jsonrpc': '2.0', 'id': 3, 'method': 'tools/call',
                          'params': {'name': 'get_cash_balance', 'arguments': {}}}, session_id)[1]
            assert result['result']['structuredContent']['data']['cash'] == '1234.00000000'
        except Exception as exc:
            process.terminate()
            _out, err = process.communicate(timeout=10)
            pytest.fail(f'HTTP MCP client connection failed: {exc}\nServer stderr:\n{err}')
        finally:
            if process.poll() is not None:
                continue
            process.terminate()
            process.wait(timeout=10)
