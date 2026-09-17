"""Paper-only Streamable HTTP MCP entry point; deployment/auth remain external."""
import os
from contextlib import asynccontextmanager

import uvicorn
from fastmcp import FastMCP
from starlette.responses import JSONResponse

from app.core.container import get_service
from app.tools.account import register_account_tools
from app.tools.market import register_market_tools
from app.tools.trading import register_trading_tools


def create_mcp(service=None, *, sampling=True):
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

    server = FastMCP('ReadyTrader-Paper', lifespan=lifespan,
                     instructions=('Permanently paper-only US common-stock simulator. No real money, brokers, deposits or leverage. '
                                   'Quantity is shares. Never fabricate reset authorization. Preserve client_order_id on retries.'))
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


def create_http_app(service=None, *, sampling=True):
    """Build the sole remote transport at /mcp, with an independent health route."""
    resolve = (lambda: service) if service is not None else get_service
    server = create_mcp(service, sampling=sampling)
    app = server.http_app(path='/mcp', transport='streamable-http', json_response=True)

    async def health(_request):
        try:
            resolve().engine.state()
        except Exception:
            return JSONResponse({'ok': False, 'status': 'unavailable', 'mode': 'paper', 'paper_only': True,
                                 'database': 'unavailable'}, status_code=503)
        return JSONResponse({'ok': True, 'status': 'ok', 'mode': 'paper', 'paper_only': True, 'database': 'ok'})

    app.add_route('/health', health, methods=['GET'])
    return app


def run_http_server():
    """Fail before binding when Paper-only configuration or SQLite is unusable."""
    try:
        service = get_service()
        service.engine.state()
        port = resolve_http_port()
    except Exception as exc:
        raise SystemExit(f'Paper-only MCP startup failed: {exc}') from exc
    uvicorn.run(create_http_app(service), host='0.0.0.0', port=port, log_level='info')


mcp = create_mcp()

if __name__ == '__main__':
    run_http_server()
