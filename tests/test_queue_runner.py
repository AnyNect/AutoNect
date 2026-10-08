"""Tests for the queue* skill (background shell jobs).

Cover:
  - parser: queue-prefixed command -> skill=command, queued=True
  - parser: bare command stays queued=False
  - parser: unknown base after the queue prefix is dropped
  - runner: launch starts a process, output is captured on completion
  - runner: drain returns the block once, then empty
  - runner: non-zero exit code survives to the block
"""
import time

from src.parser.commands import extract_commands
from src.skills import queue_runner

def _tag(name, body):
    # Fence-only since 2026-10-08: a bare tag is no longer a command.
    F = "```"
    return F + "\n<" + name + ">\n" + body + "\n</" + name + ">\n" + F

def _wait_done(job_id, timeout=10.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        st = queue_runner.status(job_id)
        if st and st["done"]:
            return st
        time.sleep(0.05)
    return queue_runner.status(job_id)

# ── parser ─────────────────────────────────────────────────────────

def test_queuecommand_parses_to_command_with_queued_flag():
    out = extract_commands(_tag("queuecommand", "echo hi"))
    assert len(out) == 1
    assert out[0]["skill"] == "command"
    assert out[0].get("queued") is True

def test_bare_command_has_no_queued_flag():
    out = extract_commands(_tag("command", "echo hi"))
    assert len(out) == 1
    assert out[0]["skill"] == "command"
    assert out[0].get("queued") is not True

def test_queue_prefix_on_unknown_skill_is_dropped():
    assert extract_commands(_tag("queuebanana", "x")) == []

def test_queueattach_degrades_to_plain_attach():
    # attach has no background form (path validation is instant).
    # A queue prefix must degrade to a plain attach, NOT mark it
    # queued -- the dispatcher drops a queued attach for lack of a
    # runner, so the old queued=True form silently lost the file
    # request (bug fixed 2026-10-06).
    out = extract_commands(_tag("queueattach", "/tmp/x"))
    assert len(out) == 1
    assert out[0]["skill"] == "attach"
    assert out[0].get("queued") is not True
    # And the dispatcher must keep it (not drop it).
    from src.web.server import _dispatch_skills
    kept = _dispatch_skills(out, "t")
    assert len(kept) == 1, kept
    assert kept[0]["skill"] == "attach"

# ── runner ─────────────────────────────────────────────────────────

def test_launch_captures_stdout_and_stderr_one_shot_drain():
    r = queue_runner.launch("echo hello-queue; echo err-line >&2")
    assert r["status"] == "running" and r["job_id"]
    st = _wait_done(r["job_id"])
    assert st and st["done"], "job never finished: %r" % st
    assert st["exit_code"] == 0

    block = queue_runner.drain_injections()
    assert "[BACKGROUND JOB COMPLETE]" in block
    assert "hello-queue" in block
    assert "err-line" in block
    assert r["job_id"] in block
    # one-shot: a second drain returns nothing
    assert queue_runner.drain_injections() == ""

def test_nonzero_exit_code_survives_to_the_block():
    r = queue_runner.launch("exit 7")
    st = _wait_done(r["job_id"])
    assert st and st["done"]
    assert st["exit_code"] == 7
    block = queue_runner.drain_injections()
    assert "exit     7" in block

def test_unknown_job_id_returns_none():
    assert queue_runner.status("nope") is None

# ── idle-flush support ─────────────────────────────────────────────

def test_requeue_puts_block_back_at_the_front():
    # drain once, requeue, drain again returns the same block
    r = queue_runner.launch("echo requeue-probe")
    st = _wait_done(r["job_id"])
    assert st and st["done"]
    block = queue_runner.drain_injections()
    assert "requeue-probe" in block
    assert queue_runner.drain_injections() == ""
    queue_runner.requeue_injections(block)
    assert queue_runner.pending_count() == 1
    again = queue_runner.drain_injections()
    assert again == block

def test_requeue_ignores_empty():
    before = queue_runner.pending_count()
    queue_runner.requeue_injections("")
    assert queue_runner.pending_count() == before

def test_on_complete_callback_fires():
    got = []
    queue_runner.set_on_complete(lambda job: got.append(job.get("job_id")))
    try:
        r = queue_runner.launch("echo cb-probe")
        st = _wait_done(r["job_id"])
        assert st and st["done"]
        # callback runs on the watcher thread just before/after the
        # block is queued; give it a moment
        for _ in range(40):
            if got:
                break
            time.sleep(0.05)
        assert r["job_id"] in got
    finally:
        queue_runner.set_on_complete(None)
        queue_runner.drain_injections()
