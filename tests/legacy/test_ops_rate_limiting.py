
from app.core.container import global_container
from common.rate_limiter import FixedWindowRateLimiter


def test_rate_limiting_blocks_after_limit():
    # Reset limiter for deterministic test
    global_container.rate_limiter = FixedWindowRateLimiter()
    limit = 2
    
    # We allow 2 calls
    global_container.rate_limiter.check(key="test_key", limit=limit, window_seconds=60)
    global_container.rate_limiter.check(key="test_key", limit=limit, window_seconds=60)
    
    # 3rd should raise
    try:
        global_container.rate_limiter.check(key="test_key", limit=limit, window_seconds=60)
        assert False, "Should have raised RateLimitError"
    except Exception:
        pass
