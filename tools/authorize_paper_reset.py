"""Local operator only: python -m tools.authorize_paper_reset. Never an MCP tool."""
from app.core.container import get_service


def main():
    service = get_service()
    state = service.engine.state()
    print(f"Reset will archive cycle {state['generation']} and restore USD {state['initial_cash']}.")
    if input('Type AUTHORIZE RESET to issue a one-use 5-minute token: ') != 'AUTHORIZE RESET':
        raise SystemExit('Cancelled.')
    print(service.engine.authorize_reset())


if __name__ == '__main__':
    main()
