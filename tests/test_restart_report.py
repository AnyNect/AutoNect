"""Test the event-driven restart-report path.

scripts/restart.sh POSTs the report to /api/restart-report/publish; the
server fans it out over /ws/events to connected UIs. The frontend reacts
by forwarding it to the AI (/api/ai-feedback).

    AUTONECT_TEST_URL=http://127.0.0.1:9000 .venv/bin/python -m pytest tests/test_restart_report.py -v
"""
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))
URL = os.environ.get("AUTONECT_TEST_URL", "http://127.0.0.1:9000/")
WS = URL.replace("http://", "ws://").replace("https://", "wss://").rstrip("/")

sync_playwright = None
try:
    from playwright.sync_api import sync_playwright  # noqa: F401
except Exception:
    pass


def _server_up(u):
    import urllib.request
    try:
        urllib.request.urlopen(u, timeout=2); return True
    except Exception:
        return False


pytestmark = pytest.mark.skipif(
    sync_playwright is None or not _server_up(URL),
    reason="no reachable AutoNect server",
)


def test_publish_endpoint_exists():
    import urllib.request
    # The publish endpoint must exist (not 404). A body-less publish may
    # 200 (it falls back to the status file) or 400 (no report yet) --
    # both prove the route is wired.
    req = urllib.request.Request(URL.rstrip("/") + "/api/restart-report/publish",
                                 data=b"{}", headers={"Content-Type": "application/json"})
    try:
        code = urllib.request.urlopen(req, timeout=5).status
    except urllib.error.HTTPError as e:
        code = e.code
    assert code in (200, 400), code


def test_ws_events_receives_pushed_report():
    """A publish call must fan out to a connected /ws/events client."""
    import json, threading, urllib.request
    with sync_playwright() as pw:
        # Use Playwright's JS to open the event socket and publish, so the
        # browser-side receive path is exercised too.
        b = pw.chromium.launch(headless=True)
        pg = b.new_page()
        pg.goto(URL, wait_until="domcontentloaded")
        pg.wait_for_function("typeof connectEventSocket === 'function'", timeout=10000)
        res = pg.evaluate(
            """async () => {
                return await new Promise((resolve) => {
                    const proto = location.protocol === 'https:' ? 'wss:' : 'ws:';
                    const ws = new WebSocket(`${proto}//${location.host}/ws/events`);
                    const timer = setTimeout(() => resolve({timeout:true}), 8000);
                    ws.onmessage = (ev) => {
                        try {
                            const m = JSON.parse(ev.data);
                            if (m.type === 'restart-report') {
                                clearTimeout(timer);
                                resolve({got:true, len:(m.content||'').length});
                            }
                        } catch(e) {}
                    };
                    ws.onopen = () => {
                        fetch('/api/restart-report/publish', {
                            method:'POST', headers:{'Content-Type':'application/json'},
                            body: JSON.stringify({content:'RESULT: UP (event: DeepSeek connected)'})
                        });
                    };
                });
            }"""
        )
        assert res.get("got") is True, res
        assert res["len"] > 0, res
        b.close()
