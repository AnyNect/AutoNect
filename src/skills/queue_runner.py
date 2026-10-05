"""queue* skills -- launch a shell command in the background.

A skill tag whose name starts with ``queue`` (e.g. ``<queuecommand>``,
``<queuekaggle>``) is normalised by the parser to the base skill name
plus ``queued: True``.  This module is the handler for the ``command``
base case: instead of running the command through the frontend PTY
(``/ws/execute``, which dies with the browser tab), it launches a real
subprocess on the server, drains its output on a reader thread, and
appends a formatted block to a pending-injection buffer when the job
finishes.

The injection buffer is drained by server.py at the top of BOTH
``/api/chat`` and ``/api/ai-feedback`` and appended to the outbound
prompt, so a finished background job rides the next message -- user,
skill, or command-output -- exactly as asked.

Jobs live in server memory.  A server restart orphans a running job
and its output never reaches the AI; a v2 could persist to disk.
"""
import shlex
import subprocess
import threading
import time
import uuid
from typing import Dict, List, Optional

MAX_INJECTION_BYTES = 60 * 1024  # cap a job's stdout in the injection block

_jobs: Dict[str, dict] = {}
_jobs_lock = threading.Lock()
_pending: List[str] = []
_pending_lock = threading.Lock()

# Optional completion callback, set by server.py. Fired from the
# watcher thread the moment a job's block is queued, so the UI can
# be told "a job finished" and decide on its own whether it is idle.
_on_complete = None
_on_complete_lock = threading.Lock()


def set_on_complete(cb):
    """Register a callback invoked (from the watcher thread) with the
    finished job's dict. Used to push a queue-job-done event."""
    global _on_complete
    with _on_complete_lock:
        _on_complete = cb

def _now() -> float:
    return time.time()

def _format_injection(job: dict) -> str:
    out = job.get("stdout", "") or ""
    err = job.get("stderr", "") or ""
    if len(out) > MAX_INJECTION_BYTES:
        out = f"...[truncated, showing last {MAX_INJECTION_BYTES} bytes]\n" + out[-MAX_INJECTION_BYTES:]
    if len(err) > MAX_INJECTION_BYTES:
        err = f"...[truncated, showing last {MAX_INJECTION_BYTES} bytes]\n" + err[-MAX_INJECTION_BYTES:]
    return (
        "[BACKGROUND JOB COMPLETE]\n"
        f"job      {job['job_id']}\n"
        f"command  {job['command']}\n"
        f"exit     {job.get('exit_code', -1)}\n"
        f"runtime  {job.get('runtime_s', 0):.1f}s\n"
        "stdout:\n"
        f"{out}\n"
        "stderr:\n"
        f"{err}\n"
        "[/BACKGROUND JOB COMPLETE]"
    )

def _reader(stream, sink: list, lock: threading.Lock) -> None:
    try:
        for line in iter(stream.readline, ""):
            with lock:
                sink.append(line)
    except Exception:
        pass
    finally:
        try:
            stream.close()
        except Exception:
            pass

def _watcher(job_id: str) -> None:
    with _jobs_lock:
        job = _jobs.get(job_id)
    if job is None:
        return
    proc: subprocess.Popen = job["proc"]
    proc.wait()
    for t in job.get("threads", []):
        t.join(timeout=5)
    with _jobs_lock:
        job["stdout"] = "".join(job["_out_buf"])
        job["stderr"] = "".join(job["_err_buf"])
        job["exit_code"] = proc.returncode
        job["runtime_s"] = _now() - job["started_at"]
        job["done"] = True
        job.pop("_out_buf", None)
        job.pop("_err_buf", None)
        job.pop("threads", None)
        block = _format_injection(job)
    with _pending_lock:
        _pending.append(block)
    with _on_complete_lock:
        cb = _on_complete
    if cb is not None:
        try:
            cb(dict(job))
        except Exception:
            pass

def launch(code: str, ctx: Optional[dict] = None,
           argv: Optional[list] = None) -> dict:
    """Launch ``code`` as a background shell command, or ``argv`` directly.

    ``argv`` bypasses the shell entirely: each element is one argument,
    so shell metacharacters in the payload cannot chain a second command
    and an executable path containing spaces needs no quoting. Skill
    payloads whose contract is "args, not shell" (kaggle) MUST use the
    argv form -- the shell form silently re-enables chaining, which is
    exactly the hole this parameter exists to close.

    ``code`` is used only when ``argv`` is None (the ``command`` skill,
    which is a shell by design)."""
    job_id = "j-" + uuid.uuid4().hex[:8]
    if argv is not None:
        cmd = [str(a) for a in argv]
        display = " ".join(shlex.quote(a) for a in cmd)
    else:
        cmd = ["bash", "-lc", code]
        display = code
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        stdin=subprocess.DEVNULL,
        text=True,
        bufsize=1,
        start_new_session=True,
    )
    out_buf: list = []
    err_buf: list = []
    buf_lock = threading.Lock()
    t_out = threading.Thread(target=_reader, args=(proc.stdout, out_buf, buf_lock), daemon=True)
    t_err = threading.Thread(target=_reader, args=(proc.stderr, err_buf, buf_lock), daemon=True)
    t_out.start()
    t_err.start()
    job = {
        "job_id": job_id,
        "command": display,
        "pid": proc.pid,
        "proc": proc,
        "started_at": _now(),
        "done": False,
        "exit_code": None,
        "runtime_s": 0.0,
        "stdout": "",
        "stderr": "",
        "_out_buf": out_buf,
        "_err_buf": err_buf,
        "threads": [t_out, t_err],
    }
    with _jobs_lock:
        _jobs[job_id] = job
    threading.Thread(target=_watcher, args=(job_id,), daemon=True).start()
    return {"job_id": job_id, "pid": proc.pid, "status": "running"}

def status(job_id: str) -> Optional[dict]:
    with _jobs_lock:
        job = _jobs.get(job_id)
    if job is None:
        return None
    return {
        "job_id": job["job_id"],
        "command": job["command"],
        "pid": job["pid"],
        "done": job["done"],
        "exit_code": job.get("exit_code"),
        "runtime_s": (job["runtime_s"] if job["done"] else _now() - job["started_at"]),
        "stdout_len": len("".join(job.get("_out_buf", []))) if not job["done"] else len(job.get("stdout", "")),
        "stderr_len": len("".join(job.get("_err_buf", []))) if not job["done"] else len(job.get("stderr", "")),
    }

def list_jobs() -> List[dict]:
    with _jobs_lock:
        ids = list(_jobs.keys())
    out = []
    for jid in ids:
        s = status(jid)
        if s:
            out.append(s)
    return out

def drain_injections() -> str:
    """Return and clear all finished-job blocks waiting to ride the next prompt."""
    with _pending_lock:
        if not _pending:
            return ""
        blocks = list(_pending)
        _pending.clear()
    return "\n\n".join(blocks)

def requeue_injections(block: str) -> None:
    """Put a drained block back at the front (used when a flush
    fails, so the output is not lost)."""
    if not block:
        return
    with _pending_lock:
        _pending.insert(0, block)


def pending_count() -> int:
    with _pending_lock:
        return len(_pending)
