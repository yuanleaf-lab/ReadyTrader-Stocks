import time


def test_ws_stream_restart_after_stop():
    """
    Regression test:
    Streams must be restartable after stop() (the stop flag must be cleared on start()).
    """

    # Import locally so the test doesn't accidentally import network code paths elsewhere.
    from marketdata.ws_streams import _WsStream  # type: ignore

    class DummyStream(_WsStream):
        async def _run_async(self) -> None:  # pragma: no cover
            # keep running until stop is requested
            import asyncio

            while not self._stop.is_set():
                await asyncio.sleep(0.01)

    s = DummyStream()
    s.start()
    time.sleep(0.05)
    assert s.status()["running"] is True

    s.stop()
    time.sleep(0.02)
    assert s.status()["running"] is False

    # restart should work
    s.start()
    time.sleep(0.05)
    assert s.status()["running"] is True

    s.stop()
    assert s.status()["running"] is False

