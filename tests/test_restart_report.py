"""Test that a restart report is forwarded to the AI automatically.

scripts/restart.sh writes its report to $AUTONECT_STATUS. The server
exposes it at GET /api/restart-report; the frontend's checkRestartReport()
fetches it and feeds it to the AI via /api/ai-feedback, so a self-restart
continues the loop with no human step.

    AUTONECT_TEST_URL=http://127.0.0.1:9000 .venv/bin/python -m pytest tests/test_restart_report.py -v
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


def test_restart_report_endpoint_exists():
    import json, urllib.request
    with urllib.request.urlopen(URL.rstrip("/") + "/api/restart-report", timeout=5) as r:
        d = json.loads(r.read().decode())
    assert "content" in d  # may be null if no report pending


def test_checkRestartReport_forwards_content():
    with sync_playwright() as pw:
        b = pw.chromium.launch(headless=True)
        pg = b.new_page()
        pg.goto(URL, wait_until="domcontentloaded")
        pg.wait_for_function("typeof checkRestartReport === 'function'", timeout=10000)
        res = pg.evaluate(
            """async () => {
                const _orig = window.fetch;
                let forwarded = null, acked = false;
                window.fetch = async (url, opts) => {
                    if (url.includes('/api/restart-report/ack')) { acked = true;
                        return new Response('{"ok":true}', {status:200, headers:{'Content-Type':'application/json'}}); }
                    if (url.includes('/api/restart-report')) {
                        return new Response(JSON.stringify({content: 'RESULT: UP after ~10s', mtime: 1}),
                            {status:200, headers:{'Content-Type':'application/json'}});
                    }
                    if (url.includes('/api/ai-feedback')) {
                        forwarded = JSON.parse(opts.body);
                        return new Response(JSON.stringify({answer:'ok', thinking:'', commands:[]}),
                            {status:200, headers:{'Content-Type':'application/json'}});
                    }
                    return new Response('[]', {status:200, headers:{'Content-Type':'application/json'}});
                };
                try {
                    await checkRestartReport();
                    return { forwarded, acked };
                } finally { window.fetch = _orig; }
            }"""
        )
        assert res["acked"] is True, res
        assert res["forwarded"] is not None, res
        assert "RESULT: UP" in res["forwarded"]["stdout"], res
        b.close()


def test_checkRestartReport_noop_when_empty():
    with sync_playwright() as pw:
        b = pw.chromium.launch(headless=True)
        pg = b.new_page()
        pg.goto(URL, wait_until="domcontentloaded")
        pg.wait_for_function("typeof checkRestartReport === 'function'", timeout=10000)
        res = pg.evaluate(
            """async () => {
                const _orig = window.fetch;
                let forwarded = false;
                window.fetch = async (url, opts) => {
                    if (url.includes('/api/restart-report/ack'))
                        return new Response('{"ok":true}', {status:200, headers:{'Content-Type':'application/json'}});
                    if (url.includes('/api/restart-report'))
                        return new Response('{"content":null}', {status:200, headers:{'Content-Type':'application/json'}});
                    if (url.includes('/api/ai-feedback')) { forwarded = true;
                        return new Response('{}', {status:200, headers:{'Content-Type':'application/json'}}); }
                    return new Response('[]', {status:200, headers:{'Content-Type':'application/json'}});
                };
                try {
                    // shrink the poll window so the test is fast
                    await checkRestartReport();
                    return { forwarded };
                } finally { window.fetch = _orig; }
            }"""
        )
        # with content:null the poll gives up after ~12s and nothing is forwarded
        assert res["forwarded"] is False, res
        b.close()
