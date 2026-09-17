"""Paper-only Streamable HTTP MCP entry point with a secret remote path."""
import os
import re
from contextlib import asynccontextmanager

import uvicorn
from fastmcp import FastMCP
from starlette.responses import JSONResponse

from app.core.container import get_service
from app.tools.account import register_account_tools
from app.tools.market import register_market_tools
from app.tools.trading import register_trading_tools


def resolve_mcp_path() -> str:
    """Require a long unguessable MCP path on Railway; keep /mcp for local development."""
    raw = os.getenv('MCP_PATH', '').strip()
    if raw:
        if not re.fullmatch(r'/mcp-[A-Za-z0-9_-]{32,128}', raw):
            raise ValueError('MCP_PATH must be /mcp- followed by 32..128 URL-safe characters.')
        return raw
    if os.getenv('RAILWAY_ENVIRONMENT'):
        raise ValueError('MCP_PATH is required for Railway HTTP deployment.')
    return '/mcp'


def create_mcp(service=None, *, sampling=True, auth=None):
    resolve = (lambda: service) if service is not None else get_service

    @asynccontextmanager
    async def lifespan(server):
        active = resolve()
        if sampling:
            active.start_sampling()
        try:
            yield {}
        finally:
            if sampling:
                active.stop_sampling()

    server = FastMCP(
        'ReadyTrader-Paper',
        lifespan=lifespan,
        auth=auth,
        instructions=(
            'Permanently paper-only US common-stock simulator. No real money, brokers, deposits or leverage. '
            'Quantity is shares. Never fabricate reset authorization. Preserve client_order_id on retries.'
        ),
    )
    register_market_tools(server, resolve)
    register_account_tools(server, resolve)
    register_trading_tools(server, resolve)
    return server


def resolve_http_port() -> int:
    """Read Railway's PORT convention without accepting an invalid listener."""
    raw = os.getenv('PORT', '8000')
    try:
        port = int(raw)
    except (TypeError, ValueError) as exc:
        raise ValueError('PORT must be an integer from 1 to 65535.') from exc
    if not 1 <= port <= 65535:
        raise ValueError('PORT must be an integer from 1 to 65535.')
    return port


def create_http_app(service=None, *, sampling=True, auth=None, mcp_path=None):
    """Build the unauthenticated remote transport at a secret path and public /health."""
    resolve = (lambda: service) if service is not None else get_service
    server = create_mcp(service, sampling=sampling, auth=auth)

    @server.custom_route('/health', methods=['GET'])
    async def health(_request):
        try:
            resolve().engine.state()
        except Exception:
            return JSONResponse(
                {'ok': False, 'status': 'unavailable', 'mode': 'paper', 'paper_only': True,
                 'database': 'unavailable'},
                status_code=503,
            )
        return JSONResponse(
            {'ok': True, 'status': 'ok', 'mode': 'paper', 'paper_only': True, 'database': 'ok'}
        )

    return server.http_app(path=mcp_path or resolve_mcp_path(), transport='streamable-http', json_response=True)


def run_http_server():
    """Fail before binding when Paper-only configuration, secret path, or SQLite is unusable."""
    try:
        service = get_service()
        service.engine.state()
        mcp_path = resolve_mcp_path()
        port = resolve_http_port()
    except Exception as exc:
        raise SystemExit(f'Paper-only MCP startup failed: {exc}') from exc
    uvicorn.run(create_http_app(service, auth=None, mcp_path=mcp_path),
                host='0.0.0.0', port=port, log_level='info')


# Schema/in-process test object only. The deployed HTTP entry point resolves its secret path separately.
mcp = create_mcp(auth=None)

if __name__ == '__main__':
    run_http_server()
