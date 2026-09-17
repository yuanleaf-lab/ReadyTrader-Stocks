"""Streamable HTTP boundary tests using the real FastMCP ASGI application."""
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from starlette.testclient import TestClient

from tests.test_paper_mcp import EXPECTED
from tests.test_paper_service import service


def _request(client, payload, session_id=None):
    headers = {'Accept': 'application/json, text/event-stream', 'Content-Type': 'application/json'}
    if session_id:
        headers['Mcp-Session-Id'] = session_id
    return client.post('/mcp', content=json.dumps(payload), headers=headers)


def _initialize(client):
    response = _request(client, {
        'jsonrpc': '2.0', 'id': 1, 'method': 'initialize',
        'params': {'protocolVersion': '2025-03-26', 'capabilities': {},
                   'clientInfo': {'name': 'paper-http-test', 'version': '1.0'}},
    })
    assert response.status_code == 200
    body = response.json()
    assert body['result']['serverInfo']['name'] == 'ReadyTrader-Paper'
    return response.headers['mcp-session-id']


def test_http_port_defaults_and_rejects_invalid_values(monkeypatch):
    from app.main import resolve_http_port

    monkeypatch.delenv('PORT', raising=False)
    assert resolve_http_port() == 8000
    monkeypatch.setenv('PORT', '4567')
    assert resolve_http_port() == 4567
    monkeypatch.setenv('PORT', '0')
    with pytest.raises(ValueError, match='PORT'):
        resolve_http_port()


@pytest.mark.parametrize('environment', [
    {'PAPER_MODE': 'false'},
    {'PAPER_DB_PATH': 'database-path-is-a-directory'},
])
def test_http_process_fails_clearly_for_unsafe_startup(tmp_path, environment):
    repo = Path(__file__).resolve().parents[1]
    env = dict(os.environ, PORT='47999', **environment)
    if environment.get('PAPER_DB_PATH') == 'database-path-is-a-directory':
        env['PAPER_DB_PATH'] = str(tmp_path)
    result = subprocess.run([sys.executable, '-m', 'app.main'], cwd=repo, env=env,
                            capture_output=True, text=True, timeout=30)
    assert result.returncode != 0
    assert 'Paper-only MCP startup failed:' in result.stderr


def test_streamable_http_health_initialize_and_allowed_tools(tmp_path):
    from app.main import create_http_app

    with TestClient(create_http_app(service(tmp_path), sampling=False)) as client:
        health = client.get('/health')
        assert health.status_code == 200
        assert health.json() == {'ok': True, 'status': 'ok', 'mode': 'paper', 'paper_only': True, 'database': 'ok'}

        session_id = _initialize(client)
        initialized = _request(client, {'jsonrpc': '2.0', 'method': 'notifications/initialized'}, session_id)
        assert initialized.status_code == 202

        tools = _request(client, {'jsonrpc': '2.0', 'id': 2, 'method': 'tools/list'}, session_id)
        assert {tool['name'] for tool in tools.json()['result']['tools']} == EXPECTED

        for request_id, name, arguments in (
            (3, 'get_cash_balance', {}),
            (4, 'get_portfolio', {}),
            (5, 'get_stock_price', {'symbol': 'AAPL'}),
        ):
            result = _request(client, {'jsonrpc': '2.0', 'id': request_id, 'method': 'tools/call',
                                       'params': {'name': name, 'arguments': arguments}}, session_id)
            assert result.status_code == 200
            payload = result.json()['result']['structuredContent']
            assert payload['ok'] is True

        missing = _request(client, {'jsonrpc': '2.0', 'id': 6, 'method': 'tools/call',
                                    'params': {'name': 'place_limit_order', 'arguments': {}}}, session_id)
        assert missing.status_code == 200
        missing_content = missing.json()['result']['content']
        assert missing_content[0]['type'] == 'text'
        assert 'Unknown tool' in missing_content[0]['text']
