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
    return "<" + name + ">\n" + body + "\n</" + name + ">"

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

def test_queueattach_parses_to_attach_with_queued_flag():
    out = extract_commands(_tag("queueattach", "/tmp/x"))
    assert len(out) == 1
    assert out[0]["skill"] == "attach"
    assert out[0].get("queued") is True

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
