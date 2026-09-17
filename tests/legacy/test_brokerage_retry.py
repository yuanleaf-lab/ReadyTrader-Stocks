import pytest

from execution.retry import with_retry


def test_with_retry_retries_transient_and_then_succeeds(monkeypatch):
    calls = {"n": 0}

    def fn():
        calls["n"] += 1
        if calls["n"] < 2:
            raise ConnectionError("temporary network issue")
        return "ok"

    # avoid real sleep in test
    monkeypatch.setattr("execution.retry.time.sleep", lambda _: None)
    monkeypatch.setenv("BROKERAGE_RETRY_MAX_ATTEMPTS", "3")
    out = with_retry("op", fn)
    assert out == "ok"
    assert calls["n"] == 2

def test_with_retry_does_not_retry_non_transient(monkeypatch):
    calls = {"n": 0}

    def fn():
        calls["n"] += 1
        # Generic exception that should NOT be retried based on our simplified logic
        # (Only strings containing timeout, network, etc. are retried)
        raise ValueError("unsupported operation")

    monkeypatch.setattr("execution.retry.time.sleep", lambda _: None)
    monkeypatch.setenv("BROKERAGE_RETRY_MAX_ATTEMPTS", "3")
    with pytest.raises(Exception) as e:
        with_retry("op", fn)
    assert "op failed after 1 attempt(s)" in str(e.value)
    assert calls["n"] == 1
