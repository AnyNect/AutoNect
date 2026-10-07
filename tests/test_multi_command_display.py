"""Multi-command feedback must NOT claim the commands were piped.

HAZARD 4 (2026-10-07): several command blocks in one AI turn are run
SEPARATELY by the frontend (one card at a time over /ws/execute).  The
file-attach feedback header joined them with " | ", so the AI was told
`Command: A | B | C` -- reading as a real shell pipe, which it was not.
Fixed to a " ; " join (still not a shell line, but honest about the
sequence).  This test pins the honest form and the per-command body.
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.web.server import build_wrapped_commands_output

def test_per_command_body_lists_each_separately():
    cmds = [
        {"command": "head -1 a.txt", "exit_code": 0, "stdout": "A\n", "stderr": ""},
        {"command": "cat b.txt", "exit_code": 0, "stdout": "B\n", "stderr": ""},
    ]
    out = build_wrapped_commands_output(cmds)
    # Two independent wrappers, one per command.
    assert out.count("[SYSTEM_COMMAND_OUTPUT]") == 2
    assert out.count("[/SYSTEM_COMMAND_OUTPUT]") == 2
    assert "Command: head -1 a.txt" in out
    assert "Command: cat b.txt" in out
    # No pipe-join anywhere.
    assert " | " not in out

def test_no_pipe_join_in_server_source():
    """Guard: the command_display header must not re-introduce ' | '."""
    src = open(os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "src", "web", "server.py"), encoding="utf-8").read()
    assert '" | ".join' not in src, "command_display must not pipe-join"
