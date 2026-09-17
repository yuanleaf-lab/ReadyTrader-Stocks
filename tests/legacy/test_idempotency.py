import os
from unittest.mock import patch

import pytest

from common.idempotency import IdempotencyStore


@pytest.fixture
def store(tmp_path):
    with patch.dict(os.environ, {"IDEMPOTENCY_DB_PATH": str(tmp_path / "idem.db")}):
        s = IdempotencyStore()
        return s

def test_idempotency_set_get_mem(store):
    store.set("k1", {"res": "ok"})
    # Get from mem
    assert store.get("k1") == {"res": "ok"}
    # Get from db by clearing mem
    store.clear()
    assert store.get("k1") == {"res": "ok"}
    
def test_idempotency_empty_key(store):
    store.set("", {"a": 1})
    assert store.get("") is None
    
def test_idempotency_invalid_payload(store):
    with pytest.raises(TypeError):
        store.set("k2", "not a dict")
        
def test_idempotency_persistence_check(tmp_path):
    path = str(tmp_path / "p.db")
    with patch.dict(os.environ, {"IDEMPOTENCY_DB_PATH": path}):
        s = IdempotencyStore()
        s.set("k", {"p": 1})
        
        # New instance
        s2 = IdempotencyStore()
        assert s2.get("k") == {"p": 1}

def test_idempotency_bad_json_in_db(tmp_path):
    path = str(tmp_path / "bad.db")
    with patch.dict(os.environ, {"IDEMPOTENCY_DB_PATH": path}):
        s = IdempotencyStore()
        s._get_conn() # Init DB
        
        import sqlite3
        conn = sqlite3.connect(path)
        conn.execute("INSERT INTO idempotency(key, payload_json, created_at_ms, updated_at_ms) VALUES(?, ?, ?, ?)", ("kbad", "not json", 0, 0))
        conn.commit()
        conn.close()
        
        assert s.get("kbad") is None

def test_no_db_path():
    with patch.dict(os.environ, {}, clear=True):
        # Default is data/idempotency.db
        with patch("common.idempotency.os.makedirs", side_effect=OSError):
             # Force _db_path to fail or mock it
             pass
    
    # Just mock _db_path to return empty
    with patch.object(IdempotencyStore, "_db_path", return_value=""):
         s = IdempotencyStore()
         s.set("k", {"a": 1})
         assert s.get("k") == {"a": 1} # in mem
         s.clear()
         assert s.get("k") is None # no persistence
