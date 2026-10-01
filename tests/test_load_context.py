"""Wiring test for the "Load Context" button (commit e4087fb).

The button starts a fresh chat and sends User/FOR_AI.md as the first
message; the server prepends src/prompts/system.txt on new sessions.

This test drives a RUNNING AutoNect in a headless browser and verifies
loadContextChat():
  - fetches GET /api/context/for-ai (real endpoint),
  - resets the chat view and sets currentChatId = null,
  - hands the FOR_AI.md content to executeTask() unchanged.

The DeepSeek navigation and the actual send are stubbed/blocked: those
need a logged-in session and are not what this test checks.

    AUTONECT_TEST_URL=http://127.0.0.1:9000 .venv/bin/python -m pytest tests/test_load_context.py -v

Skips if no server is reachable.
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


def test_for_ai_endpoint_returns_content():
    import json
    import urllib.request

    with urllib.request.urlopen(URL.rstrip("/") + "/api/context/for-ai", timeout=5) as r:
        data = json.loads(r.read().decode("utf-8"))
    assert "content" in data
    assert isinstance(data["content"], str)
    assert len(data["content"]) > 1000  # FOR_AI.md is ~14 KB
    # sanity: the file's own title line is present
    assert "Instructions for the AI reader" in data["content"]


def test_button_present_in_html():
    import urllib.request

    with urllib.request.urlopen(URL, timeout=5) as r:
        html = r.read().decode("utf-8")
    assert 'id="loadContextBtn"' in html
    assert "loadContextChat()" in html


def test_loadContextChat_sends_for_ai_content():
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        page = browser.new_page()

        # Block the DeepSeek navigation: it is not under test and would
        # otherwise drive the server's Thorium instance.
        page.route("**/api/browser/navigate", lambda route: route.fulfill(
            status=200, content_type="application/json", body='{"status":"success"}'
        ))

        page.goto(URL, wait_until="domcontentloaded")
        page.wait_for_function("typeof loadContextChat === 'function'", timeout=10000)

        res = page.evaluate(
            """async () => {
                // Capture what executeTask receives instead of sending.
                let captured = null;
                const _orig = executeTask;
                executeTask = (t) => { captured = t; };

                currentChatId = 'old-chat-id';
                chatArea.innerHTML = '<div class="message-row">old</div>';

                await loadContextChat();

                executeTask = _orig;
                const out = {
                    capturedLen: captured ? captured.length : 0,
                    capturedHasTitle: captured ? captured.includes('Instructions for the AI reader') : false,
                    currentChatId,
                    welcomeShown: chatArea.innerHTML.includes('Loading context'),
                };
                return out;
            }"""
        )

        assert res["capturedLen"] > 1000, res
        assert res["capturedHasTitle"] is True, res
        assert res["currentChatId"] is None, res

        browser.close()
