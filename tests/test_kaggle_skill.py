"""Tests for the kaggle skill and its queued routing.

No Kaggle credentials exist here, so the handler's clean-error path is
what we assert. Nothing hits the network.
"""
from src.skills import kaggle

def _tag(name, body):
    return "<" + name + ">\n" + body + "\n</" + name + ">"

# ── handler ─────────────────────────────────────────────────────────

def test_bin_resolves_to_a_kaggle_executable():
    b = kaggle.kaggle_bin()
    assert b, "kaggle binary not found"
    assert b.endswith("kaggle")

def test_empty_payload_errors():
    r = kaggle.handle("", {})
    assert r["ok"] is False
    assert "empty" in r["error"].lower()

def test_missing_credentials_is_a_clean_error_not_a_raise():
    r = kaggle.handle("kernels list", {})
    assert r["ok"] is False
    assert isinstance(r["error"], str)

def test_bad_quoting_is_caught():
    r = kaggle.handle("kernels list 'unterminated", {})
    assert r["ok"] is False

# ── remote-GPU helpers ──────────────────────────────────────────────

def test_build_metadata_has_all_required_keys():
    m = kaggle.build_kernel_metadata("me", "my-kernel", "train.py")
    for k in ("id", "title", "code_file", "language", "kernel_type",
              "is_private", "enable_gpu", "enable_internet",
              "dataset_sources", "competition_sources",
              "kernel_sources", "model_sources"):
        assert k in m, k
    assert m["id"] == "me/my-kernel"
    assert m["enable_gpu"] == "true"   # string, not bool

def test_build_metadata_booleans_are_strings():
    m = kaggle.build_kernel_metadata("me", "k", "train.py",
                                     enable_gpu=False, is_private=False)
    assert m["enable_gpu"] == "false"
    assert m["is_private"] == "false"
    assert isinstance(m["enable_gpu"], str)

def test_write_kernel_dir_creates_files(tmp_path):
    m = kaggle.build_kernel_metadata("me", "k", "train.py")
    r = kaggle.write_kernel_dir(str(tmp_path / "kern"), "print('hi')", m)
    assert r["ok"] is True, r
    assert (tmp_path / "kern" / "train.py").read_text() == "print('hi')"
    assert (tmp_path / "kern" / "kernel-metadata.json").exists()

# ── parser + queued routing (the tests that were missing) ────────────

def test_parser_marks_queuekaggle_as_queued_kaggle():
    from src.parser.commands import extract_commands
    out = extract_commands(_tag("queuekaggle", "kernels list -m"))
    assert len(out) == 1
    assert out[0]["skill"] == "kaggle"
    assert out[0].get("queued") is True

def test_server_imports_kaggle_module():
    # Regression: server.py used _kaggle in _queued_skill_command but
    # never imported it -- a NameError that reached the live server
    # (2026-10-03). Importing the module catches it.
    from src.web import server
    assert hasattr(server, "_kaggle")

def test_queued_skill_command_maps_kaggle_to_a_bash_line():
    from src.web import server
    line = server._queued_skill_command("kaggle", "kernels list")
    assert line is not None
    assert line.endswith("kaggle kernels list")

def test_queued_skill_command_unknown_skill_is_none():
    from src.web import server
    assert server._queued_skill_command("banana", "x") is None

def test_dispatcher_routes_queued_kaggle_to_a_running_job():
    # Full path: parsed tag -> _dispatch_skills -> a live background job.
    from src.web.server import _extract_response
    from src.skills import queue_runner
    answer = ("Launching.\n\n```\n" + _tag("queuekaggle", "kernels list -m")
              + "\n```\n")
    _, _, commands = _extract_response(
        {"thinking": "", "answer": answer, "commands": []}, session_id="t")
    q = [c for c in commands if c.get("skill") == "queue"]
    assert len(q) == 1, commands
    assert q[0]["result"].get("status") == "running"
    queue_runner.drain_injections()
