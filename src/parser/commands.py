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

Background jobs: a skill name may be PREFIXED with queue
(for example the tag for a queued shell command is the word
"queue" immediately followed by "command"). The prefix is
stripped and the entry gains ``queued: True``; the base skill
name is unchanged, so every downstream consumer still sees the
original skill. A queue prefix on an unknown base skill is
dropped, same as an unknown skill today. The tag shape stays
flat -- one tag, one skill -- so the same regex covers it and
no nested-tag parsing is needed.

Each match returns:
    skill  - the skill name (command, attach, kaggle, ...)
    code   - the payload, stripped
    raw    - the exact match
    queued - True when the tag carried the queue prefix (omitted otherwise)
"""
import re
from typing import Dict, List

KNOWN_SKILLS = {"command", "attach", "kaggle"}
# Only these have a background form. attach is instantaneous (path
# validation), so a queue prefix on it degrades to plain attach
# instead of being dropped by the dispatcher (bug 2026-10-06).
BACKGROUNDABLE_SKILLS = {"command", "kaggle"}

_TAG_RE = re.compile(
    r"(?:<|&lt;)([a-zA-Z_][\w-]*)(?:>|&gt;)\s*"
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
        tag = match.group(1).lower()
        queued = False
        skill = tag
        if tag.startswith("queue") and tag != "queue":
            base = tag[len("queue"):]
            if base in KNOWN_SKILLS:
                skill = base
                queued = base in BACKGROUNDABLE_SKILLS
        if skill not in KNOWN_SKILLS:
            continue
        code = match.group(2).strip()
        if not code:
            continue
        key = (skill, queued, code)
        if key in seen:
            continue
        seen.add(key)
        entry = {"skill": skill, "code": code, "raw": match.group(0)}
        if queued:
            entry["queued"] = True
        commands.append(entry)

    if commands:
        return commands

    for match in _FENCE_RE.finditer(text):
        code = match.group(1).strip()
        if not code:
            continue
        key = ("command", False, code)
        if key in seen:
            continue
        seen.add(key)
        commands.append({"skill": "command", "code": code, "raw": match.group(0)})
    return commands
