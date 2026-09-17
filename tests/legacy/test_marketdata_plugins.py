import json

from marketdata.plugins import load_marketdata_plugins


def test_load_marketdata_plugins_static_json_file(tmp_path, monkeypatch):
    feed = tmp_path / "feed.json"
    feed.write_text(json.dumps({"BTC/USDT": {"last": 50000, "timestamp_ms": 123}}))
    monkeypatch.setenv(
        "MARKETDATA_PLUGINS_JSON",
        json.dumps(
            [
                {
                    "class": "marketdata.plugin_examples:StaticJsonFileProvider",
                    "provider_id": "file_feed",
                    "kwargs": {"path": str(feed)},
                }
            ]
        ),
    )
    providers = load_marketdata_plugins()
    assert len(providers) == 1
    p = providers[0]
    t = p.fetch_ticker("BTC/USDT")
    assert t["last"] == 50000.0
    assert t["source"] == "file"

