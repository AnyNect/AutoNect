"""Tests for the research skill: argv-only execution, no shell.

Mirrors test_kaggle_skill.py. The load-bearing property is that the
payload is parsed into an argv LIST and run with shell=False, so a tag
cannot chain commands (the A1 injection lesson).
"""
import os
from pathlib import Path
from unittest import mock

import pytest

from src.skills import research as rs
from src.parser.commands import KNOWN_SKILLS, extract_commands

def test_research_in_known_skills():
    assert "research" in KNOWN_SKILLS

def test_handler_registered():
    from src.skills import HANDLERS
    assert "research" in HANDLERS

def test_parse_probe_argv():
    assert rs._parse_payload("mode: probe\nquery: hello\nlimit: 5") == \
        ["probe", "hello", "--limit", "5", "--json"]

def test_parse_run_argv():
    assert rs._parse_payload("mode: run\nquery: hi\nbreadth: 6\ntop: 3") == \
        ["run", "hi", "--breadth", "6", "--top", "3", "--json"]

def test_parse_fetch_argv_urls():
    argv = rs._parse_payload("mode: fetch\nurls:\n  https://a.com\n  https://b.com")
    assert argv == ["fetch", "https://a.com", "https://b.com", "--json"]

def test_run_executes_argv_not_shell():
    """The critical property: subprocess gets a LIST, shell=False."""
    captured = {}

    def fake_run(cmd, **kw):
        captured["cmd"] = cmd
        captured["shell"] = kw.get("shell")
        class P: returncode = 0; stdout = '{"ok":true,"mode":"run","sources":[]}'; stderr = ""
        return P()

    with mock.patch.object(rs, "_research_bin", return_value="/usr/bin/research"), \
         mock.patch.object(rs.subprocess, "run", side_effect=fake_run):
        r = rs.handle("mode: run\nquery: test", {})
    assert isinstance(captured["cmd"], list), "must pass argv list, not a string"
    assert captured["shell"] is False
    assert "test" in captured["cmd"]

def test_injection_cannot_chain():
    """A ';' in the payload is a literal argument, never a shell chain."""
    captured = {}

    def fake_run(cmd, **kw):
        captured["cmd"] = cmd
        captured["shell"] = kw.get("shell")
        class P: returncode = 0; stdout = ""; stderr = ""
        return P()

    with mock.patch.object(rs, "_research_bin", return_value="/usr/bin/research"), \
         mock.patch.object(rs.subprocess, "run", side_effect=fake_run):
        rs.handle("mode: probe\nquery: foo; touch /tmp/pwned", {})
    # the whole payload value is ONE argv element; ';' is a literal char
    assert captured["cmd"][1] == "probe"
    assert captured["cmd"][2] == "foo; touch /tmp/pwned"
    assert captured["shell"] is False

def test_missing_binary_returns_error():
    with mock.patch.object(rs, "_research_bin", return_value=None):
        r = rs.handle("mode: probe\nquery: x", {})
    assert r["ok"] is False
    assert "not found" in r["error"]

def test_empty_payload_rejected():
    r = rs.handle("", {})
    assert r["ok"] is False

def test_parser_extracts_research_tag():
    text = "```\n<research>\nmode: probe\nquery: x\n</research>\n```"
    entries = extract_commands(text)
    assert any(e.get("skill") == "research" for e in entries), entries

def test_parse_ground_argv():
    # ground/verify are CLI subcommands, not skill modes; the skill
    # passes through run/probe/fetch only. Assert the CLI exposes them.
    import subprocess
    out = subprocess.run(["research", "--help"], capture_output=True, text=True).stdout
    for cmd in ("probe", "fetch", "run", "ground", "verify", "selftest"):
        assert cmd in out, f"{cmd} missing from CLI help"

def test_handler_returns_paths_not_files():
    """The frontend consumes result.paths (strings); files (dicts) is
    the OLD shape and silently fails to attach. Regression guard."""
    def fake_run(cmd, **kw):
        class P:
            returncode = 0
            stdout = '{"ok":true,"mode":"run","bundle_md":"/x/a.md","bundle_json":"/x/a.json","sources":[]}'
            stderr = ""
        return P()

    with mock.patch.object(rs, "_research_bin", return_value="/usr/bin/research"), \
         mock.patch.object(rs.subprocess, "run", side_effect=fake_run):
        r = rs.handle("mode: run\nquery: t", {})
    assert "paths" in r, "must return paths"
    assert "files" not in r, "must NOT return the old files key"
    assert r["paths"] == ["/x/a.md", "/x/a.json"]
    assert all(isinstance(p, str) for p in r["paths"])

def test_script_js_handles_research():
    """script.js must route the research skill to the file-delivery branch."""
    from pathlib import Path
    js = Path("src/web/static/script.js").read_text()
    assert "skill === 'research'" in js, "research not routed in script.js"

def test_queued_research_maps_to_argv():
    """queueresearch must produce an argv list (no shell)."""
    from src.web.server import _queued_skill_command
    r = _queued_skill_command("research", "mode: probe\nquery: x\nlimit: 3")
    assert isinstance(r, list), "queued research must be argv"
    assert r[0].endswith("research")
    assert r[1] == "probe"
