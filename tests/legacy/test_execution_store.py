import os
import time
from unittest.mock import patch

import pytest

from execution.store import ExecutionStore


@pytest.fixture
def store(tmp_path):
    with patch.dict(os.environ, {"EXECUTION_DB_PATH": str(tmp_path / "exec.db")}):
        s = ExecutionStore()
        return s

def test_create_get_pending(store):
    p = store.create(kind="trade", payload={"symbol": "AAPL", "amount": 10}, ttl_seconds=60)
    assert p.request_id
    assert p.confirm_token
    assert store.get(p.request_id).request_id == p.request_id
    
    pending = store.list_pending()["pending"]
    assert len(pending) == 1
    assert pending[0]["request_id"] == p.request_id

def test_expiry(store):
    store.create(kind="trade", payload={"foo": "bar"}, ttl_seconds=0.1)
    time.sleep(0.2)
    # create another valid one

# ... (skipping to next fix in same file if possible, or separate calls)

    store.create(kind="trade", payload={"foo": "baz"}, ttl_seconds=60)
    
    pending = store.list_pending()["pending"]
    # Only the fresh one should be here
    assert len(pending) == 1
    assert pending[0]["kind"] == "trade"

def test_confirm_flow(store):
    p = store.create(kind="stock_order", payload={"symbol": "AAPL", "side": "buy"})
    
    # invalid token
    with pytest.raises(ValueError, match="Invalid confirm_token"):
        store.confirm(p.request_id, "wrongtoken")
        
    # success
    p2 = store.confirm(p.request_id, p.confirm_token)
    assert p2.confirmed_at
    
    # replay
    with pytest.raises(ValueError, match="Proposal already confirmed"):
        store.confirm(p.request_id, p.confirm_token)

def test_cancel(store):
    p = store.create(kind="stock_order", payload={"symbol": "AAPL"})
    assert store.cancel(p.request_id)
    assert store.get(p.request_id).cancelled_at
    
    # Confirm cancelled?
    with pytest.raises(ValueError, match="Proposal cancelled"):
        store.confirm(p.request_id, p.confirm_token)

def test_persistence(tmp_path):
    db_path = str(tmp_path / "persist.db")
    with patch.dict(os.environ, {"EXECUTION_DB_PATH": db_path}):
        s1 = ExecutionStore()
        p = s1.create(kind="trade", payload={"a": 1})
        rid = p.request_id
        # session_id = s1._session_id
        
        # Determine if session_id check validates persistence within same session
        # Logic: `if row[8] != self._session_id: return None`
        # So persistence is PER SESSION. Restarting the app (new instance, new session) wipes pending proposals validation.
        # But we can test s1 -> s1 flow if we clear memory but keep DB
        
        s1._items.clear()
        p_loaded = s1.get(rid)
        assert p_loaded is not None
        assert p_loaded.kind == "trade"
        
        # New session
        s2 = ExecutionStore()
        # Should NOT load it
        assert s2.get(rid) is None 
