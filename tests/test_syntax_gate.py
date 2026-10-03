"""Regression tests for the static shell-syntax gate (2026-10-03).

The security policy decides whether a command is DANGEROUS. A different
question is whether it is VALID. The Raji' apostrophe bug (unquoted path
ending in ') is not unsafe -- guard.evaluate() returns "allow" -- yet
the shell can never run it. These tests pin that check.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.security.syntax import check_bash_syntax

def test_clean_command_passes():
    assert check_bash_syntax("echo hi") == ""
    assert check_bash_syntax("ls -la | wc -l") == ""
    assert check_bash_syntax("for f in a b; do echo $f; done") == ""

def test_unquoted_single_quote_fails():
    # The Raji' path bug: trailing apostrophe opens a string.
    bad = "grep -rn x /home/zizouurl/Desktop/Raji'/ | head"
    err = check_bash_syntax(bad)
    assert err, "expected a parse error"
    assert "unexpected EOF" in err or "syntax error" in err

def test_unterminated_double_quote_fails():
    assert check_bash_syntax('echo "hello') != ""

def test_dangling_pipe_fails():
    err = check_bash_syntax("ls /tmp | | wc -l")
    assert "syntax error" in err

def test_quoted_apostrophe_passes():
    # The correct form from FOR_AI.md must NOT be flagged.
    good = 'cat "/home/zizouurl/Desktop/Raji\'/ASR.md"'
    assert check_bash_syntax(good) == ""

def test_empty_is_clean():
    assert check_bash_syntax("") == ""
    assert check_bash_syntax("   \n  ") == ""

def test_truncated_heredoc_fails():
    # bash -n exits 0 but warns "here-document delimited by end-of-file".
    # Checking only the return code let this through, and the PTY then
    # hung waiting for a terminator that never came (2026-10-03).
    err = check_bash_syntax("cat <<'ZZ'\nhello\n")
    assert err, "truncated heredoc must be invalid"
    assert "here-document" in err or "end-of-file" in err

def test_python_heredoc_truncated_fails():
    err = check_bash_syntax("python3 - <<'PY'\nimport sys\n")
    assert err, "truncated python heredoc must be invalid"

def test_complete_heredoc_passes():
    assert check_bash_syntax("cat <<'A'\nhi\nA") == ""
    assert check_bash_syntax("python3 - <<'PY'\nprint(1)\nPY") == ""
