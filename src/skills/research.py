"""research skill -- run the LOCAL deep-research engine.

Payload is a small block of key: value lines (the agent writes them):

    mode: run          # probe | fetch | run | index | search | context
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
    # 1. the installed binary (~/.local/bin/research, usually a symlink)
    if RESEARCH_BIN.exists():
        return str(RESEARCH_BIN)
    # 2. the in-repo engine: <repo>/scripts/research, two levels up from
    #    src/skills/research.py -- lets a fresh clone work with no install.
    repo_bin = Path(__file__).resolve().parents[2] / "scripts" / "research"
    if repo_bin.exists():
        return str(repo_bin)
    # 3. anything on PATH
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
    if mode == "index":
        return _parse_index(kv)
    if mode == "search":
        return _parse_search(kv)
    if mode == "context":
        return _parse_context(kv)
    # default: run
    argv = ["run"]
    if kv.get("query"): argv.append(kv["query"])
    argv += urls
    if kv.get("breadth"): argv += ["--breadth", kv["breadth"]]
    if kv.get("top"): argv += ["--top", kv["top"]]
    if kv.get("engines"): argv += ["--engines", kv["engines"]]
    if kv.get("per_domain"): argv += ["--per-domain", kv["per_domain"]]
    if kv.get("min_relevance"): argv += ["--min-relevance", kv["min_relevance"]]
    return argv + ["--json"]

def _parse_index(kv):
    argv = ["index"]
    if kv.get("rebuild", "").lower() in ("1", "true", "yes"):
        argv.append("--rebuild")
    return argv + ["--json"]

def _parse_search(kv):
    argv = ["search", kv.get("query", "")]
    if kv.get("top"): argv += ["--top", kv["top"]]
    if kv.get("show_text", "").lower() in ("1", "true", "yes"):
        argv.append("--show-text")
    if kv.get("rerank", "").lower() in ("1", "true", "yes"):
        argv.append("--rerank")
    if kv.get("min_relevance"): argv += ["--min-relevance", kv["min_relevance"]]
    if kv.get("no_dedup", "").lower() in ("1", "true", "yes"):
        argv.append("--no-dedup")
    return argv + ["--json"]

def _parse_context(kv):
    argv = ["context", kv.get("query", "")]
    if kv.get("queries"): argv += ["--queries", kv["queries"]]
    if kv.get("budget"): argv += ["--budget", kv["budget"]]
    if kv.get("per_doc"): argv += ["--per-doc", kv["per_doc"]]
    if kv.get("top"): argv += ["--top", kv["top"]]
    if kv.get("max_lines"): argv += ["--max-lines", kv["max_lines"]]
    if kv.get("no_compress", "").lower() in ("1", "true", "yes"):
        argv.append("--no-compress")
    if kv.get("out"): argv += ["--out", kv["out"]]
    return argv

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
            elif data.get("mode") == "index":
                st = data.get("stats", {})
                note = (f"index: {st.get('docs', 0)} docs, "
                        f"{st.get('chunks', 0)} chunks, "
                        f"{st.get('db_bytes', 0)/1e6:.1f} MB, "
                        f"{data.get('reindexed', 0)} refreshed.")
            elif data.get("mode") == "search":
                note = (f"search: {data.get('count', 0)} hits over the "
                        f"indexed vault (hybrid dense+BM25).")
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
