"""Extract executable skill requests from an AI response.

FENCE-ONLY (2026-10-08): a skill tag is recognised ONLY inside a code
fence. A tag written in loose prose is plain text, never a command. The
former bare-tag pass was removed: a tag written while explaining the
syntax (e.g. in prose about the tag itself) was being executed.

Accepted forms:
 1. command-language fence -- three backticks, then the word command, then
 the raw shell text. Survives the HTML to Markdown pass byte-exact and
 is the form the system prompt requests.
 2. plain fence wrapping a skill tag -- the tag name is the skill.
 Used by attach/kaggle/research and by historical chats.
 3. legacy three-backtick command fence.

Background jobs: a skill name may be prefixed with queue (a queued shell
command is the word queue immediately followed by command). The prefix is
stripped and the entry gains queued: True.

Each match returns: skill, code (the payload), raw (the exact match), and
queued: True when the tag carried the queue prefix.
"""
import re
from typing import Dict, List

KNOWN_SKILLS = {"command", "attach", "kaggle", "research"}
# Only these have a background form. attach is instantaneous (path
# validation), so a queue prefix on it degrades to plain attach
# instead of being dropped by the dispatcher (bug 2026-10-06).
BACKGROUNDABLE_SKILLS = {"command", "kaggle"}


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
