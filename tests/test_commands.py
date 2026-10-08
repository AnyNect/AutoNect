import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.parser.commands import extract_commands

F3 = chr(96) * 3


def test_tag_form():
    sample = (
        "Here you go.\n"
        + F3 + "\n"
        "<command>\n"
        "sudo apt update\n"
        "sudo apt upgrade -y\n"
        "</command>\n"
        + F3 + "\n"
    )
    cmds = extract_commands(sample)
    assert len(cmds) == 1, cmds
    assert cmds[0]["skill"] == "command"
    assert cmds[0]["code"] == "sudo apt update\nsudo apt upgrade -y"


def test_attach_skill():
    sample = F3 + "\n<attach>\n/tmp/a.png\n/tmp/b.png\n</attach>\n" + F3
    cmds = extract_commands(sample)
    assert len(cmds) == 1
    assert cmds[0]["skill"] == "attach"
    assert cmds[0]["code"] == "/tmp/a.png\n/tmp/b.png"


def test_escaped_tag():
    sample = F3 + "\n&lt;command&gt;\nls -la\n&lt;/command&gt;\n" + F3
    cmds = extract_commands(sample)
    assert len(cmds) == 1
    assert cmds[0]["skill"] == "command"
    assert cmds[0]["code"] == "ls -la"


def test_legacy_fence_fallback():
    sample = F3 + "command\nuname -a\n" + F3
    cmds = extract_commands(sample)
    assert len(cmds) == 1
    assert cmds[0]["skill"] == "command"
    assert cmds[0]["code"] == "uname -a"


def test_unknown_skill_dropped():
    sample = "<unknown>\nx\n</unknown>"
    assert extract_commands(sample) == []


def test_mixed_skills_order():
    sample = (
        F3 + "\n<command>\necho hi\n</command>\n" + F3 + "\n"
        + F3 + "\n<attach>\n/tmp/shot.png\n</attach>\n" + F3 + "\n"
    )
    cmds = extract_commands(sample)
    assert [c["skill"] for c in cmds] == ["command", "attach"]


def test_embedded_closing_tag_not_truncated():
    """A literal closing tag inside the payload (heredoc) must
    not truncate the command; the real close is the last one."""
    L = chr(60); G = chr(62); S = chr(47); N = chr(10)
    close = L + S + "command" + G
    payload = "cat <<" + chr(39) + "EOF" + chr(39) + N + close + N + "EOF" + N + "echo done"
    sample = F3 + N + L + "command" + G + N + payload + N + close + N + F3 + N
    cmds = extract_commands(sample)
    assert len(cmds) == 1
    assert cmds[0]["code"] == payload


def test_md_escaped_underscore_in_tag():
    U = chr(95); B = chr(92)
    payload = "echo a" + B + U + "b"
    tag = F3 + chr(10) + "<command>" + chr(10) + payload + chr(10) + "</command>" + chr(10) + F3
    cmds = extract_commands(tag)
    assert len(cmds) == 1, cmds
    assert cmds[0]["code"] == "echo a" + U + "b", cmds


def test_md_escaped_underscore_in_fence():
    U = chr(95); B = chr(92)
    payload = "echo a" + B + U + "b"
    body = '<command>' + chr(10) + payload + chr(10) + '</command>'
    sample = F3 + chr(10) + body + chr(10) + F3
    cmds = extract_commands(sample)
    assert len(cmds) == 1, cmds
    assert cmds[0]["code"] == "echo a" + U + "b", cmds


def test_regex_backslash_preserved():
    B = chr(92)
    payload = "grep 1" + B + ".2 file"
    tag = F3 + chr(10) + "<command>" + chr(10) + payload + chr(10) + "</command>" + chr(10) + F3
    cmds = extract_commands(tag)
    assert len(cmds) == 1, cmds
    assert cmds[0]["code"] == payload, cmds


def test_bare_tag_in_prose_is_not_a_command():
    # Fence-only since 2026-10-08: a tag written in prose (e.g. while
    # explaining the syntax) must NOT execute.
    o = '<' + "command" + '>'
    c = '</' + "command" + '>'
    prose = "To run, write " + o + "ls -la" + c + " in a fence."
    assert extract_commands(prose) == []


def test_bare_tag_own_line_in_prose_is_not_a_command():
    o = '<' + "command" + '>'
    c = '</' + "command" + '>'
    text = "Syntax:" + chr(10) + o + "ls -la" + c + chr(10) + "Use it."
    assert extract_commands(text) == []


def test_command_language_fence_extracts():
    sample = F3 + "command" + chr(10) + "echo hi" + chr(10) + F3
    out = extract_commands(sample)
    assert len(out) == 1, out
    assert out[0]["skill"] == "command"
    assert out[0]["code"] == "echo hi"


def test_four_backtick_fence_holds_nested_triple():
    F4 = chr(96)+chr(96)+chr(96)+chr(96)
    payload = "echo " + chr(96)+chr(96)+chr(96) + " nested"
    sample = F4 + "command" + chr(10) + payload + chr(10) + F4
    out = extract_commands(sample)
    assert len(out) == 1, out
    assert out[0]["code"] == payload, out


def test_queuecommand_language_sets_queued():
    sample = F3 + "queuecommand" + chr(10) + "sleep 5" + chr(10) + F3
    out = extract_commands(sample)
    assert len(out) == 1, out
    assert out[0]["skill"] == "command"
    assert out[0].get("queued") is True


def test_unknown_fence_language_dropped():
    sample = F3 + "python" + chr(10) + "print(1)" + chr(10) + F3
    assert extract_commands(sample) == []

