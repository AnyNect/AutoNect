#!/usr/bin/env bash
# Copy the DeepSeek login session from a logged-in Chromium profile into
# another profile, so a second AutoNect instance (e.g. the :9000 test
# instance) is authenticated without solving a CAPTCHA.
#
# Usage: sync-login.sh <source_profile_dir> <target_profile_dir>
#   source: e.g. ~/.autonect/browser-profile       (the daily driver)
#   target: e.g. ~/.autonect/browser-profile-9000  (the test instance)
#
# STOP the target instance first: a running Chromium rewrites its cookie
# DB on exit and would clobber the copy. This script refuses to run if a
# browser holds the target profile.
#
# Only auth state is copied (Cookies + Local/Session Storage). Caches are
# left alone. Chromium here uses --password-store=basic, so the cookie
# encryption key is stable and the DB is portable.
set -eu

SRC="${1:?source profile dir required}"
DST="${2:?target profile dir required}"

[ -d "$SRC" ] || { echo "source not found: $SRC" >&2; exit 1; }
[ -d "$DST" ] || { echo "target not found: $DST" >&2; exit 1; }

# Locate a profile's cookie file (subdir varies: "Default", "Profile 1", ...)
cookie_path() {
    local base="$1"
    local sub
    # Prefer the last-used profile recorded in Local State.
    if [ -f "$base/Local State" ]; then
        sub="$(python3 - "$base/Local State" << 'PY' 2>/dev/null || true
import json, sys
try:
    d = json.load(open(sys.argv[1]))
    print(d.get("profile", {}).get("last_used", ""))
except Exception:
    pass
PY
)"
        if [ -n "${sub:-}" ] && [ -f "$base/$sub/Cookies" ]; then
            printf '%s\n' "$base/$sub/Cookies"; return
        fi
    fi
    # Fallback: first Cookies file found.
    find "$base" -maxdepth 2 -name Cookies -type f 2>/dev/null | head -n1
}

SRC_COOKIES="$(cookie_path "$SRC")"
DST_COOKIES="$(cookie_path "$DST")"
[ -n "$SRC_COOKIES" ] || { echo "no Cookies in source $SRC" >&2; exit 1; }
[ -n "$DST_COOKIES" ] || { echo "no Cookies in target $DST" >&2; exit 1; }

# Refuse if the target profile is in use (SingletonLock points at a live pid).
if [ -L "$DST/SingletonLock" ]; then
    held="$(readlink "$DST/SingletonLock" || true)"
    pid="${held##*-}"
    if [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null; then
        echo "target profile is in use by pid $pid; stop that instance first" >&2
        exit 1
    fi
fi

# Verify the source actually has a DeepSeek session.
if ! strings "$SRC_COOKIES" | grep -q "ds_session_id"; then
    echo "warning: source $SRC_COOKIES has no ds_session_id (not logged in?)" >&2
fi

echo "Copying login state:"
echo "  from $SRC_COOKIES"
echo "    to $DST_COOKIES"
cp -f "$SRC_COOKIES" "$DST_COOKIES"
# Drop any journal/WAL so the copy is authoritative.
rm -f "${DST_COOKIES}-journal" "${DST_COOKIES}-wal" "${DST_COOKIES}-shm" 2>/dev/null || true

# Copy Local + Session Storage (some sites keep tokens there).
SRC_SUB="$(dirname "$SRC_COOKIES")"
DST_SUB="$(dirname "$DST_COOKIES")"
for store in "Local Storage" "Session Storage"; do
    if [ -d "$SRC_SUB/$store" ]; then
        rm -rf "$DST_SUB/$store"
        cp -rf "$SRC_SUB/$store" "$DST_SUB/$store"
        echo "  copied $store"
    fi
done

echo "Done. Restart the target instance to pick up the session."
