"""Extract executable commands from an AI response.
Looks for fenced code blocks with the language tag "command":
    ```command
    some shell code
    ```
"""
import re
from typing import List, Dict

# Matches a fenced block with language "command"
_COMMAND_BLOCK_RE = re.compile(
    r"```command\s*\n(.*?)```",
    re.DOTALL,
)


def extract_commands(text: str) -> List[Dict[str, str]]:
    """Return a list of command dictionaries.
    Each dict contains:
        "code"   – the shell code inside the block (stripped)
        "raw"    – the exact match including fences
    """
    commands = []
    for match in _COMMAND_BLOCK_RE.finditer(text):
        code = match.group(1).strip()
        commands.append({
            "code": code,
            "raw": match.group(0),
        })
    return commands