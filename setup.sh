#!/usr/bin/env bash
#
# AnyNect — idempotent, bulletproof setup script.
#
# Safe to run repeatedly. Preserves user data (config, system prompt,
# user notes). Only regenerates files that are script-owned.
#
set -euo pipefail

# ── Colour output ──
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
BLUE='\033[0;34m'
NC='\033[0m'

function info()    { echo -e "${BLUE}[INFO]${NC} $1"; }
function success() { echo -e "${GREEN}[OK]${NC} $1"; }
function warn()    { echo -e "${YELLOW}[WARN]${NC} $1"; }
function error()   { echo -e "${RED}[ERROR]${NC} $1"; exit 1; }

# ── Resolve repo root so the script works from anywhere ──
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# ── Helper: write a file only if its content would change ──
# Usage: atomic_write <path> <<'EOF' ... EOF
# Backs up the old file to <path>.bak once, only when content differs.
atomic_write() {
    local target="$1"
    local new_content
    new_content="$(cat)"
    if [[ -f "$target" ]] && [[ "$(cat "$target")" == "$new_content" ]]; then
        info "$(basename "$target") unchanged — skipping."
        return 0
    fi
    if [[ -f "$target" ]]; then
        cp "$target" "${target}.bak"
        info "Backed up $(basename "$target") → $(basename "$target").bak"
    fi
    printf '%s\n' "$new_content" > "$target"
    success "Wrote $target"
}

# ── Check prerequisites ──
info "Checking prerequisites..."

if ! command -v python3 &> /dev/null; then
    error "python3 not found. Install Python 3.10 or later."
fi

if ! python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)'; then
    PY_VER=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
    error "Python $PY_VER detected, but 3.10+ is required."
fi
PY_VER=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
success "Python $PY_VER found."

if ! command -v git &> /dev/null; then
    warn "git not found — you may need it to update the repository."
fi

# ── Detect browser ──
info "Detecting browser..."
BROWSER_CMD=""
if command -v thorium-browser &> /dev/null; then
    BROWSER_CMD="thorium-browser"; success "Thorium found."
elif command -v chromium &> /dev/null; then
    BROWSER_CMD="chromium"; success "Chromium found."
elif command -v google-chrome &> /dev/null; then
    BROWSER_CMD="google-chrome"; warn "Chrome found — consider Thorium/Chromium for best Playwright compatibility."
elif command -v chrome &> /dev/null; then
    BROWSER_CMD="chrome"; warn "Chrome found — consider Thorium/Chromium."
else
    warn "No supported browser found."
    info "Install Thorium (https://thorium.rocks) or Chromium via your package manager."
    read -p "Continue anyway? (y/N) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        error "Install a browser and re-run."
    fi
fi

# ── Virtual environment ──
if [ -d ".venv" ] && [ -f ".venv/bin/activate" ]; then
    info "Virtual environment already exists."
else
    info "Creating virtual environment..."
    python3 -m venv .venv
    success "Virtual environment created."
fi

# shellcheck disable=SC1091
source .venv/bin/activate

# ── Upgrade pip ──
info "Upgrading pip..."
pip install --quiet --upgrade pip

# ── Base dependencies ──
info "Installing base dependencies..."
if [ -f "dependencies/base.txt" ]; then
    pip install --quiet -r dependencies/base.txt
elif [ -f "requirements.txt" ]; then
    warn "dependencies/base.txt not found — using requirements.txt."
    pip install --quiet -r requirements.txt
else
    error "Neither dependencies/base.txt nor requirements.txt found."
fi

# ── Dev dependencies (optional) ──
if [ -f "dependencies/dev.txt" ]; then
    info "Installing dev dependencies..."
    pip install --quiet -r dependencies/dev.txt
fi

# ── Terminal extras (optional) ──
if command -v konsole &> /dev/null && [ -f "dependencies/terminal.txt" ]; then
    info "Konsole detected — installing terminal extras."
    pip install --quiet -r dependencies/terminal.txt
fi

# ── setup.py (script-owned, generated if missing) ──
if [ ! -f "setup.py" ]; then
    info "Generating setup.py..."
    cat > setup.py <<'PYEOF'
from setuptools import setup, find_packages

setup(
    name="autonect",
    version="1.0.0",
    packages=find_packages(),
    install_requires=[
        "fastapi",
        "uvicorn[standard]",
        "pydantic",
        "markdownify",
        "playwright",
        "patchright",
    ],
    entry_points={
        "console_scripts": [
            "AnyNect = src.web.launcher:main",
            "AutoNect = src.web.launcher:main",
        ],
    },
    author="AnyNect",
    description="Autonomous AI–Shell bridge",
    python_requires=">=3.10",
)
PYEOF
    success "setup.py created."
fi

# ── launcher.py (script-owned, always written) ──
mkdir -p src/web
info "Writing launcher.py..."
atomic_write "src/web/launcher.py" <<'PYEOF'
#!/usr/bin/env python3
"""AnyNect CLI — global entry point for AutoNect.

Installed via `pip install -e .`, which registers the `AnyNect` command
through setup.py's entry_points. `AutoNect` is kept as a backward-compat
alias pointing at the same `main` function.

Subcommands:
    start   (default)  start the AnyNect web server
    setup              run setup.sh to install/repair dependencies
    login              open DeepSeek in the default browser
    test [target]      run tests (all | config | browser)
    version            print the version
"""
import argparse
import os
import subprocess
import sys
import webbrowser
from pathlib import Path

VERSION = "1.0.0"

# When invoked through the console_scripts entry point, sys.path does not
# include the project root, so `import src.*` fails unless we add it here.
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def _run(cmd, **kwargs):
    """Run a subprocess from the project root, propagating Ctrl+C cleanly."""
    try:
        return subprocess.run(cmd, cwd=str(PROJECT_ROOT), check=True, **kwargs)
    except KeyboardInterrupt:
        print("\nInterrupted.", file=sys.stderr)
        return 130
    except subprocess.CalledProcessError as e:
        return e.returncode


def cmd_start(args):
    from src.core.config import config

    port = args.port if args.port is not None else config.get("server", "port", default=8000)
    host = args.host if args.host is not None else config.get("server", "host", default="127.0.0.1")
    reload = args.reload if args.reload is not None else config.get("server", "reload", default=False)

    # Propagate host/port to the server process so the startup banner
    # reflects the actual values instead of hardcoded defaults.
    os.environ["AUTONECT_HOST"] = str(host)
    os.environ["AUTONECT_PORT"] = str(port)

    import uvicorn
    print(f"🚀 Starting AnyNect on http://{host}:{port}")
    uvicorn.run(
        "src.web.server:app",
        host=host,
        port=port,
        reload=bool(reload),
        log_level="info",
    )
    return 0


def cmd_setup(args):
    script = PROJECT_ROOT / "setup.sh"
    if not script.exists():
        print(f"setup.sh not found at {script}", file=sys.stderr)
        return 1
    return _run(["bash", str(script)])


def cmd_login(args):
    webbrowser.open("https://chat.deepseek.com/")
    print("Opened DeepSeek in your default browser.")
    return 0


def cmd_test(args):
    mapping = {
        "config":  "tests.test_config",
        "browser": "tests.test_browser",
    }
    target = args.target or "all"
    if target == "all":
        return _run([sys.executable, "-m", "pytest", "tests/"])
    module = mapping.get(target)
    if not module:
        print(f"Unknown test target: {target}", file=sys.stderr)
        print(f"Available: all, {', '.join(mapping)}", file=sys.stderr)
        return 2
    return _run([sys.executable, "-m", module])


def cmd_version(args):
    print(f"AnyNect v{VERSION}")
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="AnyNect",
        description="AnyNect — AI-driven desktop automation via DeepSeek.",
    )
    sub = parser.add_subparsers(dest="command", metavar="<command>")

    p_start = sub.add_parser("start", help="Start the AnyNect web server (default)")
    p_start.add_argument("--host", default=None, help="Bind host (default: from config)")
    p_start.add_argument("--port", type=int, default=None, help="Bind port (default: from config)")
    p_start.add_argument("--reload", dest="reload", action="store_true", default=None,
                         help="Enable uvicorn auto-reload")
    p_start.add_argument("--no-reload", dest="reload", action="store_false",
                         help="Disable uvicorn auto-reload")
    p_start.set_defaults(func=cmd_start)

    p_setup = sub.add_parser("setup", help="Run setup.sh to install dependencies and browsers")
    p_setup.set_defaults(func=cmd_setup)

    p_login = sub.add_parser("login", help="Open DeepSeek in your default browser")
    p_login.set_defaults(func=cmd_login)

    p_test = sub.add_parser("test", help="Run tests")
    p_test.add_argument("target", nargs="?", help="all (default) | config | browser")
    p_test.set_defaults(func=cmd_test)

    p_ver = sub.add_parser("version", help="Print version")
    p_ver.set_defaults(func=cmd_version)

    args = parser.parse_args(argv)

    # No subcommand → default to `start`
    if not args.command:
        args.host = None
        args.port = None
        args.reload = None
        return cmd_start(args)

    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
PYEOF

# ── Editable install (registers AnyNect / AutoNect) ──
info "Installing AnyNect package in editable mode..."
pip install --quiet -e .

# ── Playwright browser ──
if python -c "import playwright" 2>/dev/null; then
    info "Ensuring Playwright Chromium is installed..."
    python -m playwright install chromium 2>&1 | grep -vE '^BEWARE:' || true
fi

# ── config/settings.json (user-owned, never overwritten) ──
if [ ! -f "config/settings.json" ]; then
    info "Creating default config/settings.json..."
    mkdir -p config
    cat > config/settings.json <<EOF
{
  "server": {
    "host": "127.0.0.1",
    "port": 8000,
    "reload": false
  },
  "browser": {
    "headless": false,
    "thorium_path": "${BROWSER_CMD:-thorium-browser}",
    "profile_path": "$HOME/.autonect/browser-profile"
  },
  "ai": {
    "provider": "deepseek",
    "timeout_seconds": 180,
    "response_timeout_ms": 180000,
    "base_url": "https://chat.deepseek.com"
  },
  "websocket": {
    "max_output_bytes": 150000
  },
  "terminal": {
    "command": ["konsole", "-e", "bash", "-c", "{command}; exec bash"],
    "fallback_terminals": ["gnome-terminal", "xterm"]
  },
  "safety": {
    "auto_approve": false,
    "blocker_enabled": true
  },
  "logging": {
    "level": "INFO"
  }
}
EOF
    success "Default config written to config/settings.json."
else
    info "config/settings.json exists — keeping user settings."
fi

# ── DeepSeek selectors (script-owned, always written) ──
SELECTORS_FILE="src/ai/providers/deepseek_selectors.json"
mkdir -p "$(dirname "$SELECTORS_FILE")"
info "Writing DeepSeek selectors..."
atomic_write "$SELECTORS_FILE" <<'JSONEOF'
{
  "textarea": "textarea[placeholder=\"Message DSeek\"]",
  "send_button": "div[role=\"button\"].ds-button--primary.ds-button--filled:not(.ds-button--disabled)",
  "retry_button": "div[role=\"button\"].ds-button--warning",
  "thinking_block": ".ds-think-content",
  "assistant_container": ".ds-assistant-message-main-content",
  "language_tag": ".d813de27",
  "code_block": ".md-code-block",
  "primary_button": "div[role=\"button\"].ds-button--primary:not(.ds-button--disabled)",
  "file_input": "input[type=\"file\"]",
  "chat_title": "#root > div > div.c3ecdb44 > div._7780f2e > div > div._2be88ba > div.f8d1e4c0.the-header > div > div"
}
JSONEOF

# ── User directory (user-owned, never overwritten) ──
if [ ! -d "User" ]; then
    info "Initialising User directory..."
    mkdir -p User
    cat > User/README.md <<'EOF'
# User Directory

This directory holds your personal notes, journals, and project context.
All files here are ignored by Git — store anything you want to share with the AI.

Examples:
- notes.md
- journal.md
- plans.md
- context.md
EOF
    echo "# Personal notes"   > User/notes.md
    echo "# Journal"          > User/journal.md
    echo "# Plans"            > User/plans.md
    echo "# Project context"  > User/context.md
    success "User directory initialised."
else
    info "User directory exists — keeping contents."
fi

# ── System prompt (user-owned unless a template is present) ──
TEMPLATE_FILE="src/prompts/system_template.txt"
OUTPUT_FILE="src/prompts/system.txt"
mkdir -p src/prompts

if [ -f "$TEMPLATE_FILE" ]; then
    info "Generating system prompt from template..."

    OS=$(uname -s)
    KERNEL=$(uname -r)
    ARCH=$(uname -m)
    SHELL_NAME=$(basename "${SHELL:-bash}")
    TERM=${TERM:-unknown}
    USER_NAME=${USER:-$(whoami)}
    HOME_DIR=${HOME:-$HOME}
    LANG_VALUE=${LANG:-en_US.UTF-8}

    if command -v apt &> /dev/null; then PACKAGE_MANAGER="apt"
    elif command -v pacman &> /dev/null; then PACKAGE_MANAGER="pacman"
    elif command -v dnf &> /dev/null; then PACKAGE_MANAGER="dnf"
    elif command -v yum &> /dev/null; then PACKAGE_MANAGER="yum"
    elif command -v zypper &> /dev/null; then PACKAGE_MANAGER="zypper"
    elif command -v apk &> /dev/null; then PACKAGE_MANAGER="apk"
    else PACKAGE_MANAGER="unknown"
    fi

    TERMINAL_EMULATOR="${TERM_PROGRAM:-${TERMINAL_EMULATOR:-${XDG_SESSION_TYPE:-unknown}}}"
    DESKTOP_SESSION_VAL="${XDG_CURRENT_DESKTOP:-${DESKTOP_SESSION:-unknown}}"

    python3 - "$TEMPLATE_FILE" "$OUTPUT_FILE" <<PYEOF
import sys
src, dst = sys.argv[1], sys.argv[2]
with open(src) as f:
    content = f.read()
subs = {
    'OS': '$OS', 'KERNEL': '$KERNEL', 'ARCH': '$ARCH',
    'SHELL': '$SHELL_NAME', 'TERM': '$TERM',
    'USER': '$USER_NAME', 'HOME': '$HOME_DIR',
    'PACKAGE_MANAGER': '$PACKAGE_MANAGER',
    'TERMINAL_EMULATOR': '$TERMINAL_EMULATOR',
    'DESKTOP_SESSION': '$DESKTOP_SESSION_VAL',
    'LANG': '$LANG_VALUE',
}
for key, val in subs.items():
    content = content.replace('{{' + key + '}}', val)
with open(dst, 'w') as f:
    f.write(content)
PYEOF
    success "System prompt regenerated from template."
elif [ ! -f "$OUTPUT_FILE" ]; then
    info "No template found — writing default system prompt."
    cat > "$OUTPUT_FILE" <<'EOF'
You are an AI assistant that helps users with system administration and development tasks.
Your responses should be clear, concise, and include commands only when appropriate.
When you provide commands, place them inside triple backticks with the language "command", e.g.:

```command
ls -la
```

Always explain what the command does before showing it.
EOF
    success "Default system prompt written."
else
    info "Existing system prompt preserved (no template found)."
fi

# ── Logs directory ──
mkdir -p logs

# ── Done ──
echo ""
success "Setup complete!"
echo ""
info "Next steps:"
echo "  • Activate the venv in your current shell:"
echo "      bash/zsh:  source .venv/bin/activate"
echo "      fish:      source .venv/bin/activate.fish"
echo ""
echo "  • Then run any of:"
echo "      AnyNect                 # start the server (default)"
echo "      AnyNect start --port P  # start on a custom port"
echo "      AnyNect login           # log in to DeepSeek once"
echo "      AnyNect test all        # run tests"
echo "      AnyNect version"
echo ""
info "Browser profile is stored at \$HOME/.autonect/browser-profile."
echo "      You only need to log in to DeepSeek once — cookies are saved."
echo ""
info "'AutoNect' remains available as a backward-compat alias for 'AnyNect'."