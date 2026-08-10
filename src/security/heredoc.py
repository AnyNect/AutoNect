import re

def extract_embedded_scripts(command: str) -> list[str]:
    """Return a list of code strings found in -c or heredoc constructs."""
    scripts = []
    # Match python -c "..." , bash -c '...' etc.
    # Simple pattern: look for -c followed by quotes
    pattern = r'-\s*c\s+(["\'])(.*?)(?<!\\)\1'
    for match in re.finditer(pattern, command, re.DOTALL):
        scripts.append(match.group(2))
    # TODO: heredoc extraction (<<EOF ... EOF) – more complex, skip for brevity
    return scripts