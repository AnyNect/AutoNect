"""kaggle skill -- run a Kaggle CLI action.

Payload is kaggle arguments, e.g. "kernels status user/kernel" or
"datasets list -m". The handler runs the CLI installed in the project
venv (.venv/bin/kaggle) and returns {ok, exit_code, stdout, stderr}.

The kaggle CLI needs credentials at ~/.kaggle/kaggle.json. If it is
missing the handler returns a clear error rather than a raw traceback.
Long actions (a kernel push, a dataset download) should use the
queuekaggle prefix -- the dispatcher routes a queued skill through
queue_runner instead, so it runs in the background and its output
arrives on its own.

SECURITY: the payload is passed to `shlex.split` and executed WITHOUT a
shell (shell=False), so a tag cannot chain commands. kaggle args are
data, not shell. This is a deliberate difference from the command
skill, which is a shell by design.
"""
import json
import os
import shlex
import shutil
import subprocess
from pathlib import Path

HOME = Path(os.path.expanduser("~"))
KAGGLE_JSON = HOME / ".kaggle" / "kaggle.json"
# The venv kaggle, resolved relative to this file: src/skills/ -> repo root.
_REPO = Path(__file__).resolve().parents[2]
VENV_KAGGLE = _REPO / ".venv" / "bin" / "kaggle"
TIMEOUT = 120  # inline actions are quick; long ones belong in queue

def kaggle_bin():
    if VENV_KAGGLE.exists():
        return str(VENV_KAGGLE)
    found = shutil.which("kaggle")
    return found

def handle(payload: str, ctx: dict) -> dict:
    payload = (payload or "").strip()
    if not payload:
        return {"ok": False, "error": "empty kaggle payload"}

    exe = kaggle_bin()
    if not exe:
        return {"ok": False, "error": "kaggle CLI not installed "
                "(pip install kaggle in the project venv)"}

    if not KAGGLE_JSON.exists():
        return {"ok": False, "error": f"no Kaggle credentials at {KAGGLE_JSON}; "
                "download kaggle.json from your Kaggle account settings"}

    try:
        args = shlex.split(payload)
    except ValueError as e:
        return {"ok": False, "error": f"bad kaggle arguments: {e}"}

    try:
        proc = subprocess.run(
            [exe, *args],
            capture_output=True, text=True, timeout=TIMEOUT,
            shell=False,
        )
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": f"kaggle timed out after {TIMEOUT}s "
                "(use queuekaggle for long actions)"}
    except Exception as e:
        return {"ok": False, "error": str(e)}

    return {
        "ok": proc.returncode == 0,
        "exit_code": proc.returncode,
        "stdout": proc.stdout[-20000:],
        "stderr": proc.stderr[-4000:],
    }


# ── Remote GPU training helpers ──────────────────────────────────────
# kaggle kernels push already triggers a full "Save & Run All" (Commit):
# the notebook/script runs end-to-end on Kaggle and its output is saved.
# There is no separate --commit flag; running is the default behaviour.
# So the whole remote-GPU workflow is: write code + kernel-metadata.json,
# push, poll `kernels status`, then `kernels output` for the results.

# The accelerator IDs the CLI accepts (--accelerator).
ACCELERATORS = (
    "NvidiaTeslaP100", "NvidiaTeslaT4", "NvidiaTeslaT4Highmem",
    "NvidiaTeslaA100", "NvidiaL4", "NvidiaL40S", "NvidiaH100",
    "TpuV38", "TpuV5E8",
)

def build_kernel_metadata(
    owner: str,
    slug: str,
    code_file: str,
    title: str = None,
    language: str = "python",
    kernel_type: str = "script",
    enable_gpu: bool = True,
    enable_internet: bool = True,
    is_private: bool = True,
    dataset_sources=None,
    competition_sources=None,
    kernel_sources=None,
    model_sources=None,
) -> dict:
    """Return a valid kernel-metadata.json dict for a kernels push.

    Values mirror what `kaggle kernels init` writes. enable_gpu requests
    a free Kaggle GPU; enable_internet is usually needed so the script
    can pip-install or fetch data at runtime. kernel_type "script" runs
    a .py file; use "notebook" for .ipynb.
    """
    meta = {
        "id": f"{owner}/{slug}",
        "title": title or slug,
        "code_file": code_file,
        "language": language,
        "kernel_type": kernel_type,
        "is_private": "true" if is_private else "false",
        "enable_gpu": "true" if enable_gpu else "false",
        "enable_internet": "true" if enable_internet else "false",
        "dataset_sources": list(dataset_sources or []),
        "competition_sources": list(competition_sources or []),
        "kernel_sources": list(kernel_sources or []),
        "model_sources": list(model_sources or []),
    }
    return meta

def write_kernel_dir(dir_path: str, code: str, metadata: dict,
                     code_file: str = None) -> dict:
    """Write a runnable kernel folder: the code file + kernel-metadata.json.

    Returns {ok, path, files}. dir_path is created if missing. The code
    file name comes from metadata['code_file'] unless overridden.
    """
    d = Path(dir_path)
    cf = code_file or metadata.get("code_file", "train.py")
    try:
        d.mkdir(parents=True, exist_ok=True)
        (d / cf).write_text(code, encoding="utf-8")
        (d / "kernel-metadata.json").write_text(
            json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    except Exception as e:
        return {"ok": False, "error": str(e)}
    return {"ok": True, "path": str(d), "files": [cf, "kernel-metadata.json"]}
