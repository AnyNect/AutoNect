
# ── remote-GPU helpers ──

def test_build_metadata_has_all_required_keys():
    from src.skills import kaggle
    m = kaggle.build_kernel_metadata("me", "my-kernel", "train.py")
    for k in ("id", "title", "code_file", "language", "kernel_type",
              "is_private", "enable_gpu", "enable_internet",
              "dataset_sources", "competition_sources",
              "kernel_sources", "model_sources"):
        assert k in m, k
    assert m["id"] == "me/my-kernel"
    assert m["enable_gpu"] == "true"  # string, not bool

def test_build_metadata_booleans_are_strings():
    from src.skills import kaggle
    m = kaggle.build_kernel_metadata("me", "k", "train.py",
                                     enable_gpu=False, is_private=False)
    assert m["enable_gpu"] == "false"
    assert m["is_private"] == "false"
    assert isinstance(m["enable_gpu"], str)

def test_write_kernel_dir_creates_files(tmp_path):
    from src.skills import kaggle
    m = kaggle.build_kernel_metadata("me", "k", "train.py")
    r = kaggle.write_kernel_dir(str(tmp_path / "kern"), "print('hi')", m)
    assert r["ok"] is True, r
    assert (tmp_path / "kern" / "train.py").read_text() == "print('hi')"
    assert (tmp_path / "kern" / "kernel-metadata.json").exists()
