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


def _request(client, payload, session_id=None, path='/mcp'):
    headers = {'Accept': 'application/json, text/event-stream', 'Content-Type': 'application/json'}
    if session_id:
        headers['Mcp-Session-Id'] = session_id
    return client.post(path, content=json.dumps(payload), headers=headers)


def _initialize(client, path='/mcp'):
    response = _request(client, {
        'jsonrpc': '2.0', 'id': 1, 'method': 'initialize',
        'params': {'protocolVersion': '2025-03-26', 'capabilities': {},
                   'clientInfo': {'name': 'paper-http-test', 'version': '1.0'}},
    }, path=path)
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


def test_http_path_defaults_locally_and_requires_secret_on_railway(monkeypatch):
    from app.main import resolve_mcp_path

    monkeypatch.delenv('MCP_PATH', raising=False)
    monkeypatch.delenv('RAILWAY_ENVIRONMENT', raising=False)
    assert resolve_mcp_path() == '/mcp'

    secret = '/mcp-' + ('a' * 48)
    monkeypatch.setenv('MCP_PATH', secret)
    assert resolve_mcp_path() == secret

    monkeypatch.setenv('MCP_PATH', '/mcp-short')
    with pytest.raises(ValueError, match='MCP_PATH'):
        resolve_mcp_path()

    monkeypatch.delenv('MCP_PATH', raising=False)
    monkeypatch.setenv('RAILWAY_ENVIRONMENT', 'production')
    with pytest.raises(ValueError, match='MCP_PATH is required'):
        resolve_mcp_path()


@pytest.mark.parametrize('environment', [
    {'PAPER_MODE': 'false'},
    {'PAPER_DB_PATH': 'database-path-is-a-directory'},
    {'RAILWAY_ENVIRONMENT': 'production'},
])
def test_http_process_fails_clearly_for_unsafe_startup(tmp_path, environment):
    repo = Path(__file__).resolve().parents[1]
    env = dict(os.environ, PORT='47999', **environment)
    env.pop('MCP_PATH', None)
    if environment.get('PAPER_DB_PATH') == 'database-path-is-a-directory':
        env['PAPER_DB_PATH'] = str(tmp_path)
    result = subprocess.run([sys.executable, '-m', 'app.main'], cwd=repo, env=env,
                            capture_output=True, text=True, timeout=30)
    assert result.returncode != 0
    assert 'Paper-only MCP startup failed:' in result.stderr
    if environment.get('RAILWAY_ENVIRONMENT'):
        assert 'MCP_PATH is required' in result.stderr


def test_streamable_http_health_initialize_and_allowed_tools(tmp_path):
    from app.main import create_http_app

    with TestClient(create_http_app(service(tmp_path), sampling=False, auth=None, mcp_path='/mcp')) as client:
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


def test_remote_mcp_uses_secret_path_without_auth_and_health_stays_public(tmp_path):
    from app.main import create_http_app

    secret = '/mcp-' + ('b' * 48)
    with TestClient(create_http_app(service(tmp_path), sampling=False, auth=None, mcp_path=secret)) as client:
        health = client.get('/health')
        assert health.status_code == 200

        old_path = _request(client, {
            'jsonrpc': '2.0', 'id': 1, 'method': 'initialize',
            'params': {'protocolVersion': '2025-03-26', 'capabilities': {},
                       'clientInfo': {'name': 'paper-http-test', 'version': '1.0'}},
        }, path='/mcp')
        assert old_path.status_code == 404

        session_id = _initialize(client, path=secret)
        tools = _request(client, {'jsonrpc': '2.0', 'id': 3, 'method': 'tools/list'},
                         session_id=session_id, path=secret)
        assert tools.status_code == 200
        assert {tool['name'] for tool in tools.json()['result']['tools']} == EXPECTED
