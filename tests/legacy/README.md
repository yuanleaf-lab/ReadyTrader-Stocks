# Archived upstream tests

These tests cover the removed brokerage, intelligence, backtest, websocket,
multi-provider, approval and former paper API contracts. They are retained as
upstream reference, not silently skipped tests of supported functionality.
The active `tests/test_paper_*` suite replaces paper/runtime coverage; shared
utility/audit tests remain active. `pytest` excludes this directory explicitly.
Do not re-enable old execution paths to make these tests pass.
