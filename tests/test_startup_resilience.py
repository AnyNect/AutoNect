"""A transient DeepSeek connect failure must not kill the server.

Regression for 2026-10-16: one ERR_NETWORK_CHANGED during startup
raised out of the lifespan handler, uvicorn logged "Application startup
failed. Exiting.", and the whole app went down -- taking the local
research engine and the command path with it. The browser is a flaky
dependency and must be treated as one.

These are source-level assertions (the same style as
test_script_js_handles_research): the lifespan is async and wires the
real browser, so pinning the CONTRACT in the source is the pragmatic
guard until a heavier integration harness exists.
"""
from pathlib import Path

SERVER = Path("src/web/server.py").read_text()
PROVIDER = Path("src/ai/providers/deepseek.py").read_text()


def test_lifespan_does_not_reraise_on_connect_failure():
    # The old code did:  except Exception: logger.exception(...); raise
    # which aborts startup. Find the lifespan connect block and assert it
    # carries a retry loop and no bare re-raise of the connect error.
    i = SERVER.index("provider = DeepSeekProvider()")
    block = SERVER[i:i + 2000]
    assert "for attempt in range(1, 4)" in block, "no connect retry loop"
    assert "_connected" in block, "no degraded-state flag"
    # The specific anti-pattern we removed:
    assert "Failed to connect DeepSeek provider" not in SERVER
    assert 'starting in degraded state' in block


def test_degraded_start_is_advertised_not_fatal():
    assert "AnyNect started WITHOUT DeepSeek (degraded)" in SERVER


def test_connect_retries_navigation():
    i = PROVIDER.index("def connect(self):")
    block = PROVIDER[i:i + 2000]
    assert "for attempt in range(1, 4)" in block, "no navigation retry"
    assert "Navigation attempt %d/3 failed" in block
