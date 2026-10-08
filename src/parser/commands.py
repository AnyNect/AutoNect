"""Extract executable skill requests from an AI response.

FENCE-ONLY (2026-10-08): a skill tag is recognised ONLY inside a code
fence. A tag written in loose prose is plain text, never a command. The
former bare-tag pass was removed: a tag written while explaining the
syntax (e.g. in prose about the tag itself) was being executed.

Accepted forms:
 1. language fence -- 3 OR MORE backticks, then a skill name (command,
    queuecommand, attach, kaggle, research), then the raw payload. The
    closer is a run of the SAME length, so a payload may contain shorter
    backtick runs without ending the fence (CommonMark nesting).
 2. plain fence wrapping a skill tag -- the tag name is the skill.
    Used by attach/kaggle/research and by historical chats.

Background jobs: the queue prefix works as a fence language too
(queuecommand). The prefix is stripped and the entry gains queued:
True.
"""
import re
from typing import Dict, List

KNOWN_SKILLS = {"command", "attach", "kaggle", "research"}
# Only these have a background form. attach is instantaneous (path
# validation), so a queue prefix on it degrades to plain attach
# instead of being dropped by the dispatcher (bug 2026-10-06).
BACKGROUNDABLE_SKILLS = {"command", "kaggle"}


_FENCE_RE = re.compile(
    r"^(`{3,})[ \t]*([a-zA-Z_][\w-]*)[ 	]*\n([\s\S]*?)^\1[ \t]*$",
    re.MULTILINE,
)


# A fenced skill block: ``` ... ``` whose body starts with a skill tag.
# Inside a fence, the REAL closing tag is the LAST one, so a literal
# closing tag embedded in a payload (e.g. inside a heredoc) does not
# truncate the command. Hazard fired 2026-10-07.
_FENCED_TAG_RE = re.compile(
    r"^(`{3,})[a-zA-Z0-9_-]*[ \t]*\n"
    r"[ \t]*(?:<|&lt;)([a-zA-Z_][\w-]*)(?:>|&gt;)"
    r"([\s\S]*?)"
    r"\n?[ \t]*(?:<|&lt;)/\2\s*(?:>|&gt;)[ \t]*\n?^\1[ \t]*$",
    re.MULTILINE,
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
        entry = _make_entry(match.group(2), match.group(3), match.group(0))
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
        entry = _make_entry(match.group(2), match.group(3), match.group(0))
        if entry is None:
            continue
        key = (entry["skill"], entry.get("queued", False), entry["code"])
        if key in seen:
            continue
        seen.add(key)
        commands.append(entry)
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
