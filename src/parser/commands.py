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

KNOWN_SKILLS = {"command", "attach", "kaggle", "research"}
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


# A fenced skill block: ``` ... ``` whose body starts with a skill tag.
# Inside a fence, the REAL closing tag is the LAST one, so a literal
# closing tag embedded in a payload (e.g. inside a heredoc) does not
# truncate the command. Hazard fired 2026-10-07.
_FENCED_TAG_RE = re.compile(
    r"```[a-zA-Z0-9_-]*\s*\n"
    r"\s*(?:<|&lt;)([a-zA-Z_][\w-]*)(?:>|&gt;)"
    r"([\s\S]*?)"
    r"\n?\s*(?:<|&lt;)/\1\s*(?:>|&gt;)\s*\n?```",
    re.DOTALL,
)


def _make_entry(tag: str, raw_code: str, raw: str):
    """Build a command entry from a tag name and payload, or None."""
    tag = tag.lower()
    queued = False
    skill = tag
    if tag.startswith("queue") and tag != "queue":
        base = tag[len("queue"):]
        if base in KNOWN_SKILLS:
            skill = base
            queued = base in BACKGROUNDABLE_SKILLS
    if skill not in KNOWN_SKILLS:
        return None
    code = unescape_md(raw_code).strip()
    if not code:
        return None
    entry = {"skill": skill, "code": code, "raw": raw}
    if queued:
        entry["queued"] = True
    return entry


def extract_commands(text: str) -> List[Dict[str, str]]:
    commands: List[Dict[str, str]] = []
    seen = set()

    # 1) Fenced skill blocks first -- greedy to the LAST closing tag so an
    #    embedded literal tag cannot truncate the payload.
    for match in _FENCED_TAG_RE.finditer(text):
        entry = _make_entry(match.group(1), match.group(2), match.group(0))
        if entry is None:
            continue
        key = (entry["skill"], entry.get("queued", False), entry["code"])
        if key in seen:
            continue
        seen.add(key)
        commands.append(entry)

    if commands:
        return commands

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
        code = unescape_md(match.group(2)).strip()
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
        code = unescape_md(match.group(1)).strip()
        if not code:
            continue
        key = ("command", False, code)
        if key in seen:
            continue
        seen.add(key)
        commands.append({"skill": "command", "code": code, "raw": match.group(0)})
    return commands
# Markdown escapes the HTML-to-Markdown conversion inserts into prose
# (underscore becomes backslash-underscore; star becomes backslash-star).
# A command carrying them reaches the shell literally and breaks: bash
# warns 'stray backslash before underscore', python raises a line
# continuation error. Strip them from command payloads. Underscore only:
# a backslash before anything else (e.g. a regex dot) is meaningful and
# must be kept.
MD_ESCAPED = ('_',)

def unescape_md(s):
    for ch in MD_ESCAPED:
        s = s.replace(chr(92) + ch, ch)
    return s


def normalize_skill_fences(text: str) -> str:
    """Wrap BARE skill tags in fences so the UI strip catches them.
    
    Why: the frontend removes fenced skill blocks from the rendered
    prose by walking pre elements.  A bare tag is not inside a pre,
    so its payload renders as visible prose AND again as an executed-
    command card -- the double-render bug.  Normalising on the server
    is the single source of truth: the fenced form is what
    extract_commands already prefers and what the frontend strips.
    
    Idempotent: tags already inside a fence are left untouched.
    """
    if not text or ('<' not in text and '&lt;' not in text):
        return text
    spans = [(m.start(), m.end()) for m in _FENCED_TAG_RE.finditer(text)]
    def _inside(pos):
        for a, b in spans:
            if a <= pos < b:
                return True
        return False
    F3 = chr(96) * 3
    NL = chr(10)
    out = []
    last = 0
    for m in _TAG_RE.finditer(text):
        if _inside(m.start()):
            continue
        tag = m.group(1).lower()
        base = tag
        if tag.startswith('queue') and tag != 'queue':
            base = tag[len('queue'):]
        if base not in KNOWN_SKILLS:
            continue
        out.append(text[last:m.start()])
        raw = m.group(0)
        prefix = ''
        if out and not out[-1].endswith(NL):
            prefix = NL
        out.append(prefix + F3 + NL + raw + NL + F3)
        last = m.end()
    if not out:
        return text
    out.append(text[last:])
    return ''.join(out)
