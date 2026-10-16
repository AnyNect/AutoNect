"""Tests for the 2026-10-16 skill-form unification.

The canonical skill form is the LANGUAGE fence (a fence whose language
is the skill name). The legacy tag-in-a-plain-fence form is accepted
for old chats but is no longer what the prompt asks for. These tests
lock in:

  - queueresearch is backgroundable (it used to degrade to a blocking
    inline run because BACKGROUNDABLE_SKILLS omitted research)
  - a message may MIX a language fence and a legacy tag; both are
    extracted, in source order
  - a language fence is not double-counted by the legacy tag pass
  - the browser extractor's per-block `lang` routes to the right skill
    through _extract_response
"""
from src.parser.commands import (
    extract_commands, _make_entry, BACKGROUNDABLE_SKILLS,
)

F = chr(96) * 3


def _lang_fence(lang, body):
    return F + lang + "\n" + body + "\n" + F


def _tag(name, body):
    return F + "\n<" + name + ">\n" + body + "\n</" + name + ">\n" + F


# ── queue backgroundability ─────────────────────────────────────────

def test_research_is_backgroundable():
    assert "research" in BACKGROUNDABLE_SKILLS


def test_queueresearch_sets_queued_true():
    out = extract_commands(_lang_fence("queueresearch", "mode: run\nquery: x"))
    assert len(out) == 1, out
    assert out[0]["skill"] == "research"
    assert out[0].get("queued") is True


def test_queueresearch_legacy_tag_sets_queued_true():
    out = extract_commands(_tag("queueresearch", "mode: run\nquery: x"))
    assert len(out) == 1, out
    assert out[0]["skill"] == "research"
    assert out[0].get("queued") is True


def test_plain_research_is_not_queued():
    out = extract_commands(_lang_fence("research", "mode: probe\nquery: x"))
    assert len(out) == 1, out
    assert out[0]["skill"] == "research"
    assert out[0].get("queued") is not True


# ── mixed forms ─────────────────────────────────────────────────────

def test_mixed_language_fence_and_legacy_tag_both_extract():
    text = (
        _lang_fence("command", "ls -la") + "\n"
        + _tag("attach", "/tmp/shot.png") + "\n"
    )
    out = extract_commands(text)
    assert [e["skill"] for e in out] == ["command", "attach"], out


def test_mixed_order_is_source_order():
    text = (
        _tag("attach", "/tmp/a.png") + "\n"
        + _lang_fence("command", "uname -a") + "\n"
    )
    out = extract_commands(text)
    assert [e["skill"] for e in out] == ["attach", "command"], out


def test_language_fence_not_double_counted_by_tag_pass():
    # A ```command fence's body is `ls -la` -- no tag inside, so the
    # legacy pass must not invent a second entry.
    out = extract_commands(_lang_fence("command", "ls -la"))
    assert len(out) == 1, out


def test_attach_language_fence_works():
    out = extract_commands(_lang_fence("attach", "/tmp/a.png\n/tmp/b.png"))
    assert len(out) == 1, out
    assert out[0]["skill"] == "attach"
    assert out[0]["code"] == "/tmp/a.png\n/tmp/b.png"


def test_kaggle_language_fence_works():
    out = extract_commands(_lang_fence("kaggle", "kernels list -m"))
    assert len(out) == 1, out
    assert out[0]["skill"] == "kaggle"
    assert out[0]["code"] == "kernels list -m"


# ── _make_entry language routing ────────────────────────────────────

def test_make_entry_resolves_every_skill_language():
    for lang, skill in (
        ("command", "command"), ("queuecommand", "command"),
        ("attach", "attach"), ("queueattach", "attach"),
        ("kaggle", "kaggle"), ("queuekaggle", "kaggle"),
        ("research", "research"), ("queueresearch", "research"),
    ):
        e = _make_entry(lang, "payload", "")
        assert e is not None, lang
        assert e["skill"] == skill, (lang, e)


def test_make_entry_drops_unknown_language():
    assert _make_entry("python", "print(1)", "") is None
    assert _make_entry("bash", "ls", "") is None


# ── _extract_response: browser lang → skill ─────────────────────────

def test_extract_response_routes_lang_to_skill():
    from src.web.server import _extract_response
    _, _, cmds = _extract_response(
        {"thinking": "", "answer": "",
         "commands": [{"lang": "research", "code": "mode: probe\nquery: x",
                       "raw": ""}]},
        session_id="t",
    )
    assert len(cmds) == 1, cmds
    assert cmds[0]["skill"] == "research"


def test_extract_response_defaults_langless_block_to_command():
    from src.web.server import _extract_response
    _, _, cmds = _extract_response(
        {"thinking": "", "answer": "",
         "commands": [{"code": "uname -a", "raw": "uname -a"}]},
        session_id="t",
    )
    assert len(cmds) == 1, cmds
    assert cmds[0]["skill"] == "command"


def test_extract_response_unknown_lang_falls_back_to_command():
    from src.web.server import _extract_response
    _, _, cmds = _extract_response(
        {"thinking": "", "answer": "",
         "commands": [{"lang": "python", "code": "print(1)", "raw": ""}]},
        session_id="t",
    )
    assert len(cmds) == 1, cmds
    assert cmds[0]["skill"] == "command"
