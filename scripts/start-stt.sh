#!/usr/bin/env bash
# Start the AutoNect STT service (:6012) if it is not already listening.
# AutoNect's /ws/stt proxy calls this on demand too, so the mic self-heals
# even if this never runs; it is belt-and-braces for the desktop shortcut.
set -u
PORT="${AUTONECT_STT_PORT:-6012}"

if lsof -i :"$PORT" -sTCP:LISTEN >/dev/null 2>&1; then
    echo "STT already listening on :$PORT"
    exit 0
fi

# Resolve stt-service from this script's repo (works from repo or App Tests).
APPDIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
STT_DIR="$APPDIR/stt-service"
PY="$STT_DIR/.venv/bin/python"
[ -x "$PY" ] || { echo "STT venv not found at $PY" >&2; exit 1; }

cd "$STT_DIR" || exit 1
setsid "$PY" -m uvicorn server:app --host 127.0.0.1 --port "$PORT" \
    > /tmp/stt-6012.log 2>&1 < /dev/null &
disown 2>/dev/null || true
echo "STT starting on :$PORT (log /tmp/stt-6012.log)"
