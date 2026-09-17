"""Paper-only Streamable HTTP MCP entry point with fail-closed remote auth."""
import os
from contextlib import asynccontextmanager

import uvicorn
from fastmcp import FastMCP
from fastmcp.server.auth.providers.jwt import StaticTokenVerifier
from starlette.responses import JSONResponse

from app.core.container import get_service
from app.tools.account import register_account_tools
from app.tools.market import register_market_tools
from app.tools.trading import register_trading_tools


_AUTH_UNSET = object()


def resolve_http_auth():
    """Require a static bearer token on Railway; allow unauthenticated local tests only."""
    token = os.getenv('MCP_AUTH_TOKEN', '').strip()
    if token:
        return StaticTokenVerifier(
            tokens={token: {'client_id': 'readytrader-paper', 'scopes': ['paper:access']}},
            required_scopes=['paper:access'],
        )
    if os.getenv('RAILWAY_ENVIRONMENT'):
        raise ValueError('MCP_AUTH_TOKEN is required for Railway HTTP deployment.')
    return None


def create_mcp(service=None, *, sampling=True, auth=_AUTH_UNSET):
    resolve = (lambda: service) if service is not None else get_service
    if auth is _AUTH_UNSET:
        auth = resolve_http_auth()

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


def create_http_app(service=None, *, sampling=True, auth=_AUTH_UNSET):
    """Build the protected remote transport at /mcp and public operational /health."""
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

    return server.http_app(path='/mcp', transport='streamable-http', json_response=True)


def run_http_server():
    """Fail before binding when Paper-only configuration, auth, or SQLite is unusable."""
    try:
        service = get_service()
        service.engine.state()
        auth = resolve_http_auth()
        port = resolve_http_port()
    except Exception as exc:
        raise SystemExit(f'Paper-only MCP startup failed: {exc}') from exc
    uvicorn.run(create_http_app(service, auth=auth), host='0.0.0.0', port=port, log_level='info')


# Schema/in-process test object only. The deployed HTTP entry point is run_http_server(),
# which always resolves fail-closed HTTP authentication separately.
mcp = create_mcp(auth=None)

if __name__ == '__main__':
    run_http_server()
