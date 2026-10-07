"""research skill -- run the LOCAL deep-research engine.

Payload is a small block of key: value lines (the agent writes them):

    mode: run          # probe | fetch | run  (default: run)
    query: <text>      # required for probe/run
    breadth: 10        # search results to fetch (run)
    top: 8             # sources kept after rerank (run)
    urls:              # for fetch, one URL per line after this
      https://a
      https://b

The handler runs /home/zizouurl/.local/bin/research (the local engine:
SearXNG + trafilatura + fastembed rerank). NO shell is used -- the
payload is parsed into an argv list and executed with shell=False, so
a tag cannot chain commands (same contract as the kaggle skill).

Returns {ok, exit_code, stdout, stderr, paths, note}. The engine
writes its evidence bundle under the vault; the bundle paths come back
in `files` so the existing feedback channel can attach them.
"""
import os
import subprocess
from pathlib import Path

HOME = Path(os.path.expanduser("~"))
RESEARCH_BIN = HOME / ".local" / "bin" / "research"
TIMEOUT = 300  # a run fetches + reranks; keep inline, queue for huge

def _research_bin():
    if RESEARCH_BIN.exists():
        return str(RESEARCH_BIN)
    import shutil
    return shutil.which("research")

def _parse_payload(payload: str) -> list[str]:
    """Turn the key:value block into an argv list for the CLI."""
    lines = [ln.rstrip() for ln in (payload or "").splitlines()]
    kv, urls, in_urls = {}, [], False
    for raw in lines:
        if not raw.strip():
            continue
        if in_urls and raw.startswith(("http://", "https://")):
            urls.append(raw.strip()); continue
        if raw.lstrip().startswith(("http://", "https://")):
            urls.append(raw.strip()); continue
        if ":" not in raw:
            continue
        key, _, val = raw.partition(":")
        key = key.strip().lower(); val = val.strip()
        if key == "urls":
            in_urls = True; continue
        in_urls = False
        kv[key] = val
    mode = kv.get("mode", "run").lower()
    argv: list[str] = []
    if mode == "selftest":
        return ["selftest"]
    if mode == "probe":
        argv = ["probe", kv.get("query", "")]
        if kv.get("limit"): argv += ["--limit", kv["limit"]]
        if kv.get("engines"): argv += ["--engines", kv["engines"]]
        return argv + ["--json"]
    if mode == "fetch":
        argv = ["fetch", *urls]
        if kv.get("limit"): argv += ["--limit", kv["limit"]]
        return argv + ["--json"]
    # default: run
    argv = ["run"]
    if kv.get("query"): argv.append(kv["query"])
    argv += urls
    if kv.get("breadth"): argv += ["--breadth", kv["breadth"]]
    if kv.get("top"): argv += ["--top", kv["top"]]
    return argv + ["--json"]

def handle(payload: str, ctx: dict) -> dict:
    exe = _research_bin()
    if not exe:
        return {"ok": False, "error": "research CLI not found at "
                f"{RESEARCH_BIN} (or on PATH)"}
    try:
        args = _parse_payload(payload)
    except Exception as e:
        return {"ok": False, "error": f"bad research payload: {e}"}
    if not args:
        return {"ok": False, "error": "empty research payload"}
    try:
        proc = subprocess.run([exe, *args], capture_output=True,
                              text=True, timeout=TIMEOUT, shell=False)
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": f"research timed out after {TIMEOUT}s "
                "(use queueresearch for very broad runs)"}
    except Exception as e:
        return {"ok": False, "error": str(e)}

    paths = []
    note = ""
    if proc.returncode == 0 and proc.stdout.strip():
        import json as _json
        try:
            data = _json.loads(proc.stdout)
            if data.get("bundle_md"): paths.append(data["bundle_md"])
            if data.get("bundle_json"): paths.append(data["bundle_json"])
            if data.get("mode") == "run":
                note = (f"research: {data.get('count', len(data.get('sources', [])))} "
                        f"ranked sources; bundle attached.")
            elif data.get("mode") == "probe":
                note = f"research: {data.get('count', 0)} results."
            elif data.get("mode") == "fetch":
                note = (f"research: {data.get('ok_count', 0)}/"
                        f"{data.get('count', 0)} pages extracted.")
        except ValueError:
            pass
    return {
        "ok": proc.returncode == 0,
        "exit_code": proc.returncode,
        "stdout": proc.stdout[-20000:],
        "stderr": proc.stderr[-4000:],
        "paths": paths,
        "note": note,
    }
