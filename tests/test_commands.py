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
    sample = "&lt;command&gt;\nls -la\n&lt;/command&gt;"
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
