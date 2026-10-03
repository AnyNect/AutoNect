"""Static shell-syntax gate.

The security policy (policy.py) decides whether a command is DANGEROUS.
This module answers a different question: is the command even VALID? A
line with an unterminated quote is not unsafe -- guard.evaluate() returns
"allow" for it -- yet the shell can never run it. That class of mistake
is the most-repeated AI failure in this project (the Raji' apostrophe,
four times). `bash -n` parses without executing and catches it.
"""
import logging
import subprocess

logger = logging.getLogger(__name__)

def check_bash_syntax(code: str) -> str:
    """Return bash's parse error for code, or "" when the code parses.

    `bash -n` runs no command; it only reads and parses. A non-zero exit
    with a "syntax error" / "unexpected EOF" message means the code can
    never execute, so nothing downstream should try.
    """
    if not code or not code.strip():
        return ""
    try:
        proc = subprocess.run(
            ["bash", "-n"],
            input=code,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.SubprocessError) as e:
        # Fail open: a missing or broken bash must not block everything.
        logger.warning("bash -n could not run: %s", e)
        return ""
    # Treat EITHER signal as a failure. A truncated heredoc (an
    # unterminated <<EOF) makes bash -n exit 0 while still writing
    # "warning: here-document ... delimited by end-of-file" to stderr;
    # an unterminated quote or dangling pipe gives rc!=0. Checking only
    # rc let the truncated heredoc through -- which then hung the PTY
    # waiting for a terminator that never came (2026-10-03).
    stderr = (proc.stderr or "").strip()
    if proc.returncode == 0 and not stderr:
        return ""
    return stderr or (proc.stdout or "bash: syntax error").strip()
