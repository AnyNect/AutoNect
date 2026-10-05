"""Extract embedded script bodies from a shell command.

Two forms are scanned:

  1. Inline -c:       python -c "import os; ..."
                      bash -c '...'
  2. Heredoc:         python - <<'PY'  ... PY
                      bash <<EOF     ... EOF
                      bash <<-EOF    ... EOF   (leading tabs stripped)

The bodies are handed to the policy layer (policy.py) as text to scan
for dangerous patterns. Missing a body is a security hole: obfuscated
code that runs inside a heredoc would otherwise be invisible.

Heredoc matching is deliberately permissive on the CLOSER (leading
tabs and trailing spaces allowed) because we would rather scan one
extra body than miss a real one; a false positive here just means an
extra pattern scan, not a wrong verdict.
"""
import re

# python -c "..."  /  bash -c '...'  etc. Single source of the -c form.
_C_RE = re.compile(r'-\s*c\s+(["\'])(.*?)(?<!\\)\1', re.DOTALL)

# Heredoc opener: <<EOF  <<'EOF'  <<"EOF"  <<-EOF. The marker is a
# shell word; the closer must repeat it alone on a line (leading tabs
# are allowed because <<- strips them; we allow them for the plain form
# too, since a scan is cheap and strictness only costs misses).
_HEREDOC_RE = re.compile(
    r"<<(?P<dash>-?)[ \t]*"
    r"(?P<q>['\"]?)(?P<marker>[A-Za-z_][A-Za-z0-9_]*)(?P=q)"
    r"[^\n]*\n"
    r"(?P<body>.*?)"
    r"\n[ \t]*(?P=marker)[ \t]*(?=\n|$)",
    re.DOTALL,
)

def extract_embedded_scripts(command: str) -> list[str]:
    """Return a list of code strings found in -c or heredoc constructs."""
    scripts = []
    for match in _C_RE.finditer(command):
        scripts.append(match.group(2))
    for match in _HEREDOC_RE.finditer(command):
        body = match.group("body")
        if body.strip():
            scripts.append(body)
    return scripts
