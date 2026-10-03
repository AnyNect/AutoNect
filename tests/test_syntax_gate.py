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
