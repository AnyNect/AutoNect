"""Test that feedback/chat POSTs survive a server restart (durable retry).

When a command restarts AutoNect, the /ws/execute socket dies and the
server goes down. The POST carrying that command's output to the AI
(/api/ai-feedback) -- and the next /api/chat send -- would fail, losing
the output and stalling the AI loop. postWithRetry() retries with
exponential backoff until the new server answers.

These tests stub fetch() in the browser to simulate an outage, then a
recovery, and assert the POST eventually succeeds.

    AUTONECT_TEST_URL=http://127.0.0.1:9000 .venv/bin/python -m pytest tests/test_restart_retry.py -v
"""
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

URL = os.environ.get("AUTONECT_TEST_URL", "http://127.0.0.1:9000/")

sync_playwright = None
try:
    from playwright.sync_api import sync_playwright  # noqa: F401
except Exception:  # pragma: no cover
    pass


def _server_up(url: str) -> bool:
    import urllib.request
    try:
        urllib.request.urlopen(url, timeout=2)
        return True
    except Exception:
        return False


pytestmark = pytest.mark.skipif(
    sync_playwright is None or not _server_up(URL),
    reason="no reachable AutoNect server at AUTONECT_TEST_URL (default :9000)",
)


@pytest.fixture(scope="module")
def page():
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        pg = browser.new_page()
        pg.goto(URL, wait_until="domcontentloaded")
        pg.wait_for_function("typeof postWithRetry === 'function'", timeout=10000)
        yield pg
        browser.close()


def test_retries_then_succeeds(page):
    res = page.evaluate(
        """async () => {
            const _orig = window.fetch;
            let calls = 0;
            window.fetch = async (url, opts) => {
                calls++;
                if (calls < 4) throw new TypeError('Failed to fetch');  // server down
                return new Response(JSON.stringify({ok:true}), {
                    status: 200, headers: {'Content-Type':'application/json'}
                });
            };
            try {
                const r = await postWithRetry('/api/ai-feedback', {x:1}, 20000);
                return { calls, status: r.status };
            } finally {
                window.fetch = _orig;
            }
        }"""
    )
    assert res["calls"] == 4, res
    assert res["status"] == 200, res


def test_gives_up_after_deadline(page):
    res = page.evaluate(
        """async () => {
            const _orig = window.fetch;
            let calls = 0;
            window.fetch = async () => { calls++; throw new TypeError('Failed to fetch'); };
            let threw = false;
            try {
                await postWithRetry('/api/ai-feedback', {x:1}, 1500);
            } catch (e) {
                threw = true;
            } finally {
                window.fetch = _orig;
            }
            return { calls, threw };
        }"""
    )
    assert res["threw"] is True, res
    # should have retried a few times within 1.5s (0.5 + 1.0 backoff)
    assert res["calls"] >= 2, res


def test_retries_on_5xx_then_succeeds(page):
    # The key fix: a just-booted server answers 500 ("Provider not
    # initialized") until DeepSeek reconnects. postWithRetry must retry
    # 5xx, not just thrown network errors.
    res = page.evaluate(
        """async () => {
            const _orig = window.fetch;
            let calls = 0;
            window.fetch = async () => {
                calls++;
                if (calls < 3) {
                    return new Response(JSON.stringify({error:'Provider not initialized'}),
                        { status: 500, headers: {'Content-Type':'application/json'} });
                }
                return new Response(JSON.stringify({ok:true}),
                    { status: 200, headers: {'Content-Type':'application/json'} });
            };
            try {
                const r = await postWithRetry('/api/ai-feedback', {x:1}, 20000);
                return { calls, status: r.status };
            } finally { window.fetch = _orig; }
        }"""
    )
    assert res["calls"] == 3, res
    assert res["status"] == 200, res


def test_4xx_not_retried(page):
    # A real 4xx is returned immediately (no retry loop).
    res = page.evaluate(
        """async () => {
            const _orig = window.fetch;
            let calls = 0;
            window.fetch = async () => {
                calls++;
                return new Response(JSON.stringify({error:'bad'}),
                    { status: 400, headers: {'Content-Type':'application/json'} });
            };
            try {
                const r = await postWithRetry('/api/ai-feedback', {x:1}, 20000);
                return { calls, status: r.status };
            } finally { window.fetch = _orig; }
        }"""
    )
    assert res["calls"] == 1, res
    assert res["status"] == 400, res


def test_chat_uses_retry(page):
    # sendToAI should route /api/chat through postWithRetry (i.e. it
    # survives a transient outage).
    res = page.evaluate(
        """async () => {
            const _orig = window.fetch;
            let chatCalls = 0, outage = 2;
            window.fetch = async (url, opts) => {
                if (typeof url === 'string' && url.includes('/api/chat')) {
                    chatCalls++;
                    if (outage-- > 0) throw new TypeError('Failed to fetch');
                    return new Response(JSON.stringify({
                        answer: 'hi', thinking: '', commands: [], session_id: 's1'
                    }), { status: 200, headers: {'Content-Type':'application/json'} });
                }
                // other calls (loadChatList) just succeed emptily
                return new Response('[]', { status: 200, headers: {'Content-Type':'application/json'} });
            };
            let ok = false;
            try {
                await sendToAI('hello');
                ok = true;
            } catch (e) { ok = false; }
            finally { window.fetch = _orig; }
            return { chatCalls, ok };
        }"""
    )
    assert res["chatCalls"] >= 3, res
    assert res["ok"] is True, res
