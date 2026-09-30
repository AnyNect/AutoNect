"""Regression tests for the message-queue bypass (issue #7).

With Auto-Allow ON, a message queued while a command group ran used to
fire the moment the last command's feedback resolved -- even though the
AI's reply to that feedback had just spawned a NEW command group. The
user message then raced the auto-executed commands, producing
interleaved command/feedback loops.

The fix is client-side (src/web/static/script.js): a message queues
while Auto-Allow has pending command work (unresolved group, queued
command, executing command, or in-flight feedback).

These tests drive a RUNNING AutoNect instance in a headless browser and
evaluate the gate functions directly. Point them at a throwaway instance
(the :9000 test instance) so they do not disturb the live :8000 session:

    AUTONECT_TEST_URL=http://127.0.0.1:9000 .venv/bin/python -m pytest tests/test_queue_gate.py -v

They skip if no server is reachable.
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


# (autoAllow, groupUnresolved, execQueueLen, isExecuting, isProcessing, isPaused, expectQueue)
GATE_CASES = [
    (False, False, 0, False, False, False, False),  # idle, AA off -> direct
    (False, False, 0, False, True, False, True),    # processing -> queue
    (False, False, 0, False, False, True, True),    # paused -> queue
    (True, True, 0, False, False, False, True),     # AA on, unresolved group -> queue
    (True, False, 2, False, False, False, True),    # AA on, exec queue -> queue
    (True, False, 0, True, False, False, True),     # AA on, executing -> queue
    (True, False, 0, False, False, False, False),   # AA on, all clear -> direct
    (True, True, 0, False, True, False, True),      # AA on, group + processing -> queue
]


@pytest.fixture(scope="module")
def page():
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        pg = browser.new_page()
        pg.goto(URL, wait_until="domcontentloaded")
        pg.wait_for_function("typeof shouldQueueMessage === 'function'", timeout=10000)
        pg.wait_for_function("typeof hasPendingCommandWork === 'function'", timeout=10000)
        yield pg
        browser.close()


@pytest.mark.parametrize(
    "aa,grp,qlen,ex,proc,paused,expect", GATE_CASES
)
def test_should_queue_gate(page, aa, grp, qlen, ex, proc, paused, expect):
    res = page.evaluate(
        """([aa, grp, qlen, ex, proc, paused]) => {
            autoAllowEnabled = aa;
            activeCommandGroup = grp ? { resolved: false } : null;
            commandExecutionQueue = new Array(qlen).fill({});
            isCommandExecuting = ex;
            isProcessing = proc;
            isPaused = paused;
            const q = shouldQueueMessage();
            const p = hasPendingCommandWork();
            autoAllowEnabled = false; activeCommandGroup = null;
            commandExecutionQueue = []; isCommandExecuting = false;
            isProcessing = false; isPaused = false;
            return { q, p };
        }""",
        [aa, grp, qlen, ex, proc, paused],
    )
    assert res["q"] is expect


def test_pending_work_ignores_autallow_flag(page):
    # hasPendingCommandWork is independent of the Auto-Allow toggle.
    res = page.evaluate(
        """() => {
            autoAllowEnabled = false;
            activeCommandGroup = { resolved: false };
            const p = hasPendingCommandWork();
            activeCommandGroup = null;
            return p;
        }"""
    )
    assert res is True


def test_handleSend_queues_when_group_pending(page):
    res = page.evaluate(
        """() => {
            autoAllowEnabled = true;
            activeCommandGroup = { resolved: false, total: 2, completed: 0, outputs: [], historical: false };
            commandExecutionQueue = []; isCommandExecuting = false;
            isProcessing = false; isPaused = false; taskQueue = [];
            promptInput.value = 'queued while commands pending';
            let directSent = false;
            const _orig = executeTask; executeTask = () => { directSent = true; };
            handleSend();
            executeTask = _orig;
            const queued = taskQueue.length;
            const first = taskQueue[0] || null;
            activeCommandGroup = null; autoAllowEnabled = false; taskQueue = []; promptInput.value = '';
            return { directSent, queued, first };
        }"""
    )
    assert res["directSent"] is False
    assert res["queued"] == 1
    assert res["first"] == "queued while commands pending"


def test_handleSend_direct_when_idle(page):
    res = page.evaluate(
        """() => {
            autoAllowEnabled = false;
            activeCommandGroup = null; commandExecutionQueue = []; isCommandExecuting = false;
            isProcessing = false; isPaused = false; taskQueue = [];
            promptInput.value = 'go direct';
            let directSent = false;
            const _orig = executeTask; executeTask = () => { directSent = true; };
            handleSend();
            executeTask = _orig;
            const queued = taskQueue.length;
            promptInput.value = ''; taskQueue = [];
            return { directSent, queued };
        }"""
    )
    assert res["directSent"] is True
    assert res["queued"] == 0


def test_processNextQueueTask_defers_when_group_pending(page):
    res = page.evaluate(
        """() => {
            autoAllowEnabled = true;
            activeCommandGroup = { resolved: false };
            taskQueue = ['hello'];
            isProcessing = false; isPaused = false;
            let drained = false;
            const _orig = executeTask; executeTask = () => { drained = true; };
            processNextQueueTask();
            const stillQueued = taskQueue.length;
            executeTask = _orig;
            autoAllowEnabled = false; activeCommandGroup = null; taskQueue = [];
            return { drained, stillQueued };
        }"""
    )
    assert res["drained"] is False
    assert res["stillQueued"] == 1


def test_processNextQueueTask_drains_when_clear(page):
    res = page.evaluate(
        """() => {
            autoAllowEnabled = true;
            activeCommandGroup = null;
            commandExecutionQueue = []; isCommandExecuting = false;
            taskQueue = ['drain me'];
            isProcessing = false; isPaused = false;
            let drained = false;
            const _orig = executeTask; executeTask = () => { drained = true; };
            processNextQueueTask();
            const stillQueued = taskQueue.length;
            executeTask = _orig;
            autoAllowEnabled = false; taskQueue = [];
            return { drained, stillQueued };
        }"""
    )
    assert res["drained"] is True
    assert res["stillQueued"] == 0


def test_feedback_spawning_new_group_keeps_message_queued(page):
    """The exact issue #7 scenario: a group resolves, its feedback reply
    spawns a NEW unresolved group, and a queued message must NOT drain."""
    res = page.evaluate(
        """() => {
            autoAllowEnabled = true;
            activeCommandGroup = { resolved: false, total: 1, completed: 0, outputs: [], historical: false };
            commandExecutionQueue = []; isCommandExecuting = false;
            isProcessing = false; isPaused = false; taskQueue = [];
            promptInput.value = 'must stay queued';
            const _orig = executeTask; executeTask = () => { window.__drained = true; };
            handleSend();
            window.__drained = false;

            isProcessing = false;
            activeCommandGroup = { resolved: false, total: 1, completed: 0, outputs: [], historical: false };
            commandExecutionQueue = []; isCommandExecuting = false;

            processNextQueueTask();
            const drained = window.__drained;
            const stillQueued = taskQueue.length;
            executeTask = _orig;
            activeCommandGroup = null; autoAllowEnabled = false; taskQueue = []; promptInput.value = '';
            return { drained, stillQueued };
        }"""
    )
    assert res["drained"] is False
    assert res["stillQueued"] == 1


def test_pending_feedback_blocks_drain(page):
    """An in-flight /api/ai-feedback request counts as pending work."""
    res = page.evaluate(
        """() => {
            autoAllowEnabled = true;
            activeCommandGroup = null; commandExecutionQueue = []; isCommandExecuting = false;
            pendingFeedback = 1;
            const pending = hasPendingCommandWork();
            const queue = shouldQueueMessage();
            pendingFeedback = 0;
            autoAllowEnabled = false;
            return { pending, queue };
        }"""
    )
    assert res["pending"] is True
    assert res["queue"] is True
