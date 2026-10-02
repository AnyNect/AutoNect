"""Extract executable skill requests from an AI response.

Preferred format: a skill tag inside a plain code fence.

    <command>
    echo hi
    </command>

The tag name is the skill (command, attach, kaggle, ...). Bare tags are
eaten by markdownify when the DeepSeek answer is converted HTML ->
markdown, so tags must be inside a fence (or entity-escaped); the regex
handles both raw and &lt;...&gt; forms.

Legacy ```command fences are still accepted as a fallback.

Each match returns:
    skill  - the skill name (command, attach, kaggle, ...)
    code   - the payload, stripped
    raw    - the exact match
"""
import re
from typing import Dict, List

KNOWN_SKILLS = {"command", "attach", "kaggle"}

_TAG_RE = re.compile(
    r"(?:<|&lt;)([a-zA-Z_][\w-]*)(?:>|&gt;)\s*\n"
    r"([\s\S]*?)"
    r"\n?\s*(?:<|&lt;)/\1\s*(?:>|&gt;)",
    re.DOTALL,
)

_FENCE_RE = re.compile(
    r"```command\s*\n(.*?)```",
    re.DOTALL,
)


def extract_commands(text: str) -> List[Dict[str, str]]:
    commands: List[Dict[str, str]] = []
    seen = set()

    for match in _TAG_RE.finditer(text):
        skill = match.group(1).lower()
        if skill not in KNOWN_SKILLS:
            continue
        code = match.group(2).strip()
        if not code:
            continue
        key = (skill, code)
        if key in seen:
            continue
        seen.add(key)
        commands.append({"skill": skill, "code": code, "raw": match.group(0)})

    if commands:
        return commands

    for match in _FENCE_RE.finditer(text):
        code = match.group(1).strip()
        if not code:
            continue
        key = ("command", code)
        if key in seen:
            continue
        seen.add(key)
        commands.append({"skill": "command", "code": code, "raw": match.group(0)})
    return commands
