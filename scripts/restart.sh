#!/usr/bin/env bash
# Restart AutoNect in place (detached) and record a full status report.
#
# Why this exists: a restart kills the server that hosts the command's own
# output, so the outcome can NOT come back in the same command block. This
# script writes a complete report to $STATUS once the new server is healthy.
# Read it next with scripts/restart-status.sh (or: cat $STATUS).
#
# Env overrides: AUTONECT_PORT (8000), AUTONECT_HOST (0.0.0.0),
#   AUTONECT_PROFILE (browser profile dir; also scopes which Thorium is
#   killed, so restarting :9000 never touches :8000's browser).
set -u

APPDIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PORT="${AUTONECT_PORT:-8000}"
HOST="${AUTONECT_HOST:-0.0.0.0}"
PROFILE="${AUTONECT_PROFILE:-}"
LOG="${AUTONECT_LIVE_LOG:-/tmp/autonect-live.log}"
RESTART_LOG="${AUTONECT_RESTART_LOG:-/tmp/autonect-restart.log}"
STATUS="${AUTONECT_STATUS:-/tmp/autonect-restart-status.txt}"
BIN="$APPDIR/.venv/bin/AutoNect"

SCHEME="http"; CERT_ARGS=()
if [ -f "$APPDIR/certs/autonect-cert.pem" ] && [ -f "$APPDIR/certs/autonect-key.pem" ]; then
    SCHEME="https"
    CERT_ARGS=(--ssl-certfile "$APPDIR/certs/autonect-cert.pem" --ssl-keyfile "$APPDIR/certs/autonect-key.pem")
fi
CURL="curl -sk -m 2"

# ---- Stage 1: not detached -> re-exec detached, return immediately ----
if [ "${AUTONECT_RESTART_DETACHED:-}" != "1" ]; then
    AUTONECT_RESTART_DETACHED=1 \
    AUTONECT_PORT="$PORT" AUTONECT_HOST="$HOST" AUTONECT_PROFILE="$PROFILE" \
    AUTONECT_LIVE_LOG="$LOG" AUTONECT_RESTART_LOG="$RESTART_LOG" AUTONECT_STATUS="$STATUS" \
        setsid nohup "$0" "$@" > "$RESTART_LOG" 2>&1 < /dev/null &
    disown 2>/dev/null || true
    echo "AutoNect restart launched (detached) on :$PORT."
    echo "Report will be written to: $STATUS"
    echo "Read it next with:         $APPDIR/restart-status.sh"
    exit 0
fi

# ---- Stage 2: detached. ----
sleep 2
{
echo "=== restart starting $(date '+%F %T') ==="
echo "Stopping AutoNect on :$PORT..."
pkill -f "$APPDIR/.venv/bin/AutoNect" 2>/dev/null
# Kill only the Thorium bound to THIS profile (anchored so browser-profile
# does not also match browser-profile-9000).
if [ -n "$PROFILE" ]; then
    pkill -f -- "--user-data-dir=${PROFILE}( |$)" 2>/dev/null
fi
for _ in $(seq 1 20); do
    lsof -i :$PORT -sTCP:LISTEN >/dev/null 2>&1 || break
    sleep 0.5
done
LEFT="$(lsof -t -i:$PORT 2>/dev/null || true)"
if [ -n "$LEFT" ]; then kill -9 $LEFT 2>/dev/null; sleep 1; fi
sleep 1
echo "Starting AutoNect..."
cd "$APPDIR" || { echo "cd failed"; exit 1; }
if [ -n "$PROFILE" ]; then
    AUTONECT_PROFILE="$PROFILE" AUTONECT_STATUS="$STATUS" \
        setsid "$BIN" start --host "$HOST" --port "$PORT" "${CERT_ARGS[@]}" \
        > "$LOG" 2>&1 < /dev/null &
else
    AUTONECT_STATUS="$STATUS" \
        setsid "$BIN" start --host "$HOST" --port "$PORT" "${CERT_ARGS[@]}" \
        > "$LOG" 2>&1 < /dev/null &
fi
} >> "$RESTART_LOG" 2>&1

UP=0; WAITED=0
for i in $(seq 1 60); do
    WAITED=$i
    if $CURL "$SCHEME://127.0.0.1:$PORT/" -o /dev/null 2>/dev/null; then UP=1; break; fi
    sleep 1
done

PID="$(lsof -t -i:$PORT 2>/dev/null | head -n1)"
SERVED="$($CURL "$SCHEME://127.0.0.1:$PORT/" 2>/dev/null | grep -o 'script.js?v=[0-9]*' | head -1)"
GIT="$(git -C "$APPDIR" log --oneline -1 2>/dev/null)"

{
echo "=== AutoNect restart report $(date '+%F %T') ==="
if [ "$UP" = 1 ]; then echo "RESULT: UP after ~${WAITED}s"; else echo "RESULT: FAILED - did not come up within 60s"; fi
echo "PORT:   $PORT"
echo "URL:    $SCHEME://127.0.0.1:$PORT"
echo "PID:    ${PID:-none}"
echo "GIT:    ${GIT:-unknown}"
echo "SERVED: ${SERVED:-unknown}"
echo "--- last 20 lines of live log ---"
tail -n 20 "$LOG" 2>/dev/null
} | tee -a "$RESTART_LOG" > "$STATUS"

[ "$UP" = 1 ] && exit 0 || exit 1
