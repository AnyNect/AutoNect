"""attach skill -- validate file paths for the server to send to the AI.

Payload: newline-separated absolute paths. Each is validated against an
allowlist of roots, symlink-resolved before the check, and size-capped.
Returns files (for the server to attach) and errors (for display). Does
NOT queue anything -- the server's self-drain reads result["files"].
"""
import mimetypes
import os
from pathlib import Path
from typing import Dict, List

HOME = Path(os.path.expanduser("~")).resolve()
ROOTS = [HOME, Path("/tmp"), HOME / "Downloads"]
DENY_PARTS = {".ssh", ".gnupg", ".aws"}
MAX_BYTES = 50 * 1024 * 1024


def _resolve(p: str):
    try:
        return Path(p).expanduser().resolve(strict=True)
    except (OSError, RuntimeError):
        return None


def _in_allowed_root(rp: Path) -> bool:
    for root in ROOTS:
        try:
            rp.relative_to(root)
            return True
        except ValueError:
            continue
    return False


def handle(payload: str, ctx: dict) -> Dict[str, List[dict]]:
    files, errors = [], []
    for raw in payload.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        rp = _resolve(line)
        if rp is None:
            errors.append({"path": line, "reason": "not found"}); continue
        if not rp.is_file():
            errors.append({"path": line, "reason": "not a regular file"}); continue
        if not _in_allowed_root(rp):
            errors.append({"path": line, "reason": "outside allowlist"}); continue
        if any(part in DENY_PARTS for part in rp.parts):
            errors.append({"path": line, "reason": "denied path segment"}); continue
        try:
            size = rp.stat().st_size
        except OSError as e:
            errors.append({"path": line, "reason": f"stat failed: {e}"}); continue
        if size > MAX_BYTES:
            errors.append({"path": line, "reason": f"too large ({size} bytes)"}); continue
        mime, _ = mimetypes.guess_type(str(rp))
        files.append({"path": str(rp), "bytes": size,
                      "mime": mime or "application/octet-stream"})
    return {"files": files, "errors": errors}
