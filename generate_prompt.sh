#!/bin/bash
# Regenerate src/prompts/system.txt and system_restricted.txt from the
# two templates in src/prompts/. The templates carry the full prompt
# with {{PLACEHOLDER}} tokens; this script detects the environment and
# substitutes. Edit the TEMPLATES, not the generated files -- the
# generated files are overwritten by this script and by setup.sh.

set -euo pipefail

REPO="$(cd "$(dirname "$0")" && pwd)"
PROMPTS="$REPO/src/prompts"

# --- Environment detection ---
OS=$(uname -s)
KERNEL=$(uname -r)
ARCH=$(uname -m)
SHELL_NAME=$(basename "${SHELL:-bash}")
TERM_VAL=${TERM:-unknown}
USER_NAME=${USER:-$(whoami)}
HOME_DIR=${HOME:-$HOME}
LANG_VAL=${LANG:-en_US.UTF-8}
HOSTNAME_VAL=$(hostname)

if command -v pacman >/dev/null; then PACKAGE_MANAGER="pacman"
elif command -v apt >/dev/null; then PACKAGE_MANAGER="apt"
elif command -v dnf >/dev/null; then PACKAGE_MANAGER="dnf"
elif command -v yum >/dev/null; then PACKAGE_MANAGER="yum"
elif command -v zypper >/dev/null; then PACKAGE_MANAGER="zypper"
elif command -v apk >/dev/null; then PACKAGE_MANAGER="apk"
else PACKAGE_MANAGER="unknown"
fi

TERMINAL_EMULATOR="${TERM_PROGRAM:-${TERMINAL_EMULATOR:-${XDG_SESSION_TYPE:-unknown}}}"
DESKTOP_SESSION_VAL="${XDG_CURRENT_DESKTOP:-${DESKTOP_SESSION:-unknown}}"

# --- Software versions ---
PYTHON_VER=$(python3 --version 2>/dev/null | cut -d' ' -f2 || echo "not found")
NODE_VER=$(node --version 2>/dev/null || echo "not installed")
DOCKER_VER=$(docker --version 2>/dev/null | cut -d' ' -f3 | tr -d ',' || echo "not installed")
GIT_VER=$(git --version 2>/dev/null | cut -d' ' -f3 || echo "not installed")

# --- User preferences: editor ---
if [ -n "${EDITOR:-}" ]; then
    EDITOR_DETECTED="$EDITOR"
else
    EDITOR_DETECTED=""
    for e in code kate vim nvim nano; do
        if command -v "$e" >/dev/null; then EDITOR_DETECTED="$e"; break; fi
    done
    [ -z "$EDITOR_DETECTED" ] && EDITOR_DETECTED="not set"
fi

# --- User preferences: browser ---
if [ -n "${BROWSER:-}" ]; then
    BROWSER_DETECTED="$BROWSER"
else
    BROWSER_DETECTED=""
    if command -v thorium-browser >/dev/null; then BROWSER_DETECTED="thorium-browser"
    elif command -v thorium >/dev/null; then BROWSER_DETECTED="thorium"
    else
        for b in firefox chromium google-chrome brave; do
            if command -v "$b" >/dev/null; then BROWSER_DETECTED="$b"; break; fi
        done
    fi
    [ -z "$BROWSER_DETECTED" ] && BROWSER_DETECTED="not set"
fi

# --- Timezone ---
TIMEZONE=$(timedatectl show --property=Timezone --value 2>/dev/null \
    || cat /etc/timezone 2>/dev/null || echo "unknown")

# --- Substitute placeholders in a template ---
render() {
    local template="$1"
    local output="$2"
    [ -f "$template" ] || { echo "missing template: $template" >&2; exit 1; }
    python3 - "$template" "$output" <<PYEOF
import sys
src, dst = sys.argv[1], sys.argv[2]
subs = {
    "OS": "$OS",
    "KERNEL": "$KERNEL",
    "ARCH": "$ARCH",
    "SHELL": "$SHELL_NAME",
    "TERM": "$TERM_VAL",
    "USER": "$USER_NAME",
    "HOME": "$HOME_DIR",
    "PACKAGE_MANAGER": "$PACKAGE_MANAGER",
    "TERMINAL_EMULATOR": "$TERMINAL_EMULATOR",
    "DESKTOP_SESSION": "$DESKTOP_SESSION_VAL",
    "LANG": "$LANG_VAL",
    "HOSTNAME": "$HOSTNAME_VAL",
    "PYTHON_VER": "$PYTHON_VER",
    "NODE_VER": "$NODE_VER",
    "DOCKER_VER": "$DOCKER_VER",
    "GIT_VER": "$GIT_VER",
    "EDITOR_DETECTED": "$EDITOR_DETECTED",
    "BROWSER_DETECTED": "$BROWSER_DETECTED",
    "TIMEZONE": "$TIMEZONE",
}
with open(src) as f:
    content = f.read()
for k, v in subs.items():
    content = content.replace("{{" + k + "}}", v)
with open(dst, "w") as f:
    f.write(content)
PYEOF
}

mkdir -p "$PROMPTS"
render "$PROMPTS/system_template.txt" "$PROMPTS/system.txt"
render "$PROMPTS/system_restricted_template.txt" "$PROMPTS/system_restricted.txt"

echo "Regenerated system.txt and system_restricted.txt from templates."
