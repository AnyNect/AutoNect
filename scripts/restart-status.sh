#!/usr/bin/env bash
# Print the AutoNect restart report written by scripts/restart.sh.
# Run this AFTER restart.sh; it returns the outcome the restart itself
# could not (the restart kills the server hosting that command's output).
set -u
STATUS="${AUTONECT_STATUS:-/tmp/autonect-restart-status.txt}"
if [ -f "$STATUS" ]; then
    cat "$STATUS"
else
    echo "No restart report yet at $STATUS"
    echo "(run scripts/restart.sh first, wait ~15s, then run this again)"
fi
