"""Regression tests for the 2026-10-06 skill bugs.

Four bugs found and fixed:
  1. _extract_response dropped a legitimate ANSWER command whenever the
     same code also appeared in the model's THINKING text.
  2. The shell guard/syntax gate judged non-shell skill payloads
     (attach, kaggle).
  3. queueattach was marked queued and then silently dropped by the
     dispatcher (no background runner for attach). Now it degrades to a
     plain attach.  (Covered in test_queue_runner.py.)
  4. A one-line skill tag did not parse (newline after the opener was
     required).
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.parser.commands import extract_commands
from src.web.server import _extract_response, _annotate_commands_with_safety

F3 = chr(96) * 3

def _tag(name, body):
    o = "<" + name + ">"
    c = "<" + "/" + name + ">"
    return F3 + "\n" + o + "\n" + body + "\n" + c + "\n" + F3

def test_answer_command_survives_identical_thinking_text():
    thinking = "I will run " + _tag("command", "ls -la /tmp")
    answer = "Here:\n" + _tag("command", "ls -la /tmp")
    _, _, cmds = _extract_response(
        {"thinking": thinking, "answer": answer, "commands": []}, session_id="t")
    codes = [c["code"] for c in cmds if c.get("skill") == "command"]
    assert codes == ["ls -la /tmp"], cmds

def test_duplicate_answer_commands_still_collapse():
    s = _tag("command", "echo hi") + "\n" + _tag("command", "echo hi")
    out = extract_commands(s)
    assert [c["code"] for c in out] == ["echo hi"]

def test_one_line_skill_tag_parses():
    o = "<" + "command" + ">"
    c = "<" + "/" + "command" + ">"
    s = F3 + "\n" + o + "ls -la" + c + "\n" + F3
    out = extract_commands(s)
    assert len(out) == 1
    assert out[0]["code"] == "ls -la"

def test_guard_not_applied_to_non_shell_skills():
    cmds = [
        {"skill": "attach", "code": "/tmp/shot.png", "raw": ""},
        {"skill": "kaggle", "code": "kernels status u/k", "raw": ""},
    ]
    ann = _annotate_commands_with_safety(cmds, "t")
    assert all(c["safety"] == "allow" for c in ann), ann

def test_guard_still_runs_on_real_shell_commands():
    cmds = [{"skill": "command", "code": "ls -la", "raw": ""}]
    ann = _annotate_commands_with_safety(cmds, "t")
    assert ann[0]["safety"] in ("allow", "warn", "invalid")

def test_invalid_shell_command_still_flagged():
    cmds = [{"skill": "command", "code": "echo 'unterminated", "raw": ""}]
    ann = _annotate_commands_with_safety(cmds, "t")
    assert ann[0]["safety"] == "invalid", ann[0]
