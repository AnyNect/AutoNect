#!/usr/bin/env bash
set -e

# ── Colour output ──
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
BLUE='\033[0;34m'
NC='\033[0m'

function info() { echo -e "${BLUE}[INFO]${NC} $1"; }
function success() { echo -e "${GREEN}[OK]${NC} $1"; }
function warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
function error() { echo -e "${RED}[ERROR]${NC} $1"; exit 1; }

# ── Check prerequisites ──
info "Checking prerequisites..."

if ! command -v python3 &> /dev/null; then
    error "Python3 not found. Please install Python 3.10 or later."
fi
PY_VER=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
if [[ $(echo "$PY_VER < 3.10" | bc) -eq 1 ]]; then
    error "Python $PY_VER detected, but 3.10+ is required."
fi
success "Python $PY_VER found."

if ! command -v git &> /dev/null; then
    warn "Git not found – you might need it to clone the repository."
fi

# ── Detect and set browser ──
info "Detecting browser..."
BROWSER_CMD=""
if command -v thorium-browser &> /dev/null; then
    BROWSER_CMD="thorium-browser"
    success "Thorium found."
elif command -v chromium &> /dev/null; then
    BROWSER_CMD="chromium"
    success "Chromium found (will be used as fallback)."
elif command -v google-chrome &> /dev/null; then
    BROWSER_CMD="google-chrome"
    warn "Chrome found – Playwright may not work perfectly; consider using Thorium or Chromium."
elif command -v chrome &> /dev/null; then
    BROWSER_CMD="chrome"
    warn "Chrome found – Playwright may not work perfectly; consider using Thorium or Chromium."
else
    warn "No supported browser found. We'll attempt to install Chromium via Playwright (headless only) but for headed mode you need a GUI browser."
    info "You can install Thorium from https://thorium.rocks or install Chromium via your package manager."
    read -p "Continue anyway? (y/N) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        error "Install a browser and run this script again."
    fi
fi

# ── Create virtual environment ──
if [ -d ".venv" ]; then
    info "Virtual environment already exists, skipping creation."
else
    info "Creating virtual environment..."
    python3 -m venv .venv
    success "Virtual environment created."
fi

source .venv/bin/activate

# ── Upgrade pip ──
info "Upgrading pip..."
pip install --upgrade pip

# ── Install base dependencies ──
info "Installing base dependencies..."
if [ -f "dependencies/base.txt" ]; then
    pip install -r dependencies/base.txt
else
    warn "dependencies/base.txt not found – using requirements.txt (legacy)"
    if [ -f "requirements.txt" ]; then
        pip install -r requirements.txt
    else
        error "Neither dependencies/base.txt nor requirements.txt found."
    fi
fi

# ── Install dev dependencies (optional) ──
if [ -f "dependencies/dev.txt" ]; then
    info "Installing development dependencies..."
    pip install -r dependencies/dev.txt
fi

# ── Install terminal extras if Konsole is present ──
if command -v konsole &> /dev/null; then
    info "Konsole detected – installing terminal extras."
    if [ -f "dependencies/terminal.txt" ]; then
        pip install -r dependencies/terminal.txt
    else
        warn "terminal.txt not found; skipping."
    fi
else
    warn "Konsole not found – native terminal integration will be disabled."
fi

# ── Ensure setup.py exists ──
if [ ! -f "setup.py" ]; then
    warn "setup.py not found, creating minimal one..."
    cat > setup.py <<'EOF'
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
EOF
    success "Created setup.py"
fi

# ── Launcher ──
# The launcher is a generated file — always write the latest version so
# upgrades (including new subcommands) land reliably. A timestamped backup
# is taken if the file already exists so user edits are never lost.
if [ -f "src/web/launcher.py" ]; then
    BACKUP="src/web/launcher.py.bak.$(date +%Y%m%d_%H%M%S)"
    cp "src/web/launcher.py" "$BACKUP"
    info "Existing launcher.py backed up to $BACKUP"
fi

mkdir -p src/web
info "Writing launcher.py (AnyNect CLI)..."
cat > src/web/launcher.py <<'EOF'
#!/usr/bin/env python3
"""AnyNect CLI — global entry point for AutoNect.

Installed via `pip install -e .`, which registers the `AnyNect` command
through setup.py's entry_points. `AutoNect` is kept as a backward-compat
alias pointing at the same `main` function.

Subcommands:
    start   (default)  start the AutoNect web server
    setup              run setup.sh to install/repair dependencies
    login              open DeepSeek in the default browser
    test [target]      run tests (all | config | browser)
    version            print the version
"""
import argparse
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

    import uvicorn
    print(f"🚀 Starting AutoNect on http://{host}:{port}")
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
EOF
success "launcher.py written."

# ── Install package in editable mode ──
info "Installing AutoNect package in editable mode..."
pip install -e .

# ── Install Playwright browsers ──
info "Installing Playwright Chromium (headless)..."
playwright install chromium

# ── Generate configuration if missing ──
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
    success "Default config created at config/settings.json."
else
    info "config/settings.json already exists – skipping."
fi

# ── DeepSeek selectors ──
# This file tracks DeepSeek's web UI. It is generated, not user-owned, so we
# always write the current version. A backup is taken if one exists.
SELECTORS_FILE="src/ai/providers/deepseek_selectors.json"
mkdir -p "$(dirname "$SELECTORS_FILE")"
if [ -f "$SELECTORS_FILE" ]; then
    BACKUP="${SELECTORS_FILE}.bak.$(date +%Y%m%d_%H%M%S)"
    cp "$SELECTORS_FILE" "$BACKUP"
    info "Existing selectors backed up to $BACKUP"
fi

info "Writing DeepSeek selectors (including chat_title)..."
cat > "$SELECTORS_FILE" <<'EOF'
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
EOF
success "DeepSeek selectors written to $SELECTORS_FILE."

# ── Create User directory with placeholders ──
if [ ! -d "User" ]; then
    info "Creating User directory with placeholders..."
    mkdir -p User
    cat > User/README.md <<EOF
# User Directory

This directory is for your personal notes, journals, and project context.
All files here are ignored by Git – feel free to store anything you want to share with the AI.

Examples:
- notes.md
- journal.md
- plans.md
- context.md
EOF
    echo "# Personal notes" > User/notes.md
    echo "# Journal" > User/journal.md
    echo "# Plans" > User/plans.md
    echo "# Project context" > User/context.md
    success "User directory initialised."
else
    info "User directory already exists – skipping."
fi

# ── Generate system prompt from template ──
info "Generating system prompt from template..."
TEMPLATE_FILE="src/prompts/system_template.txt"
OUTPUT_FILE="src/prompts/system.txt"

if [ -f "$TEMPLATE_FILE" ]; then
    # Detect environment variables
    OS=$(uname -s)
    KERNEL=$(uname -r)
    ARCH=$(uname -m)
    SHELL=$(basename "$SHELL")
    TERM=${TERM:-unknown}
    USER=${USER:-$(whoami)}
    HOME=${HOME:-$HOME}
    LANG=${LANG:-en_US.UTF-8}

    # Package manager detection
    if command -v apt &> /dev/null; then
        PACKAGE_MANAGER="apt"
    elif command -v pacman &> /dev/null; then
        PACKAGE_MANAGER="pacman"
    elif command -v dnf &> /dev/null; then
        PACKAGE_MANAGER="dnf"
    elif command -v yum &> /dev/null; then
        PACKAGE_MANAGER="yum"
    elif command -v zypper &> /dev/null; then
        PACKAGE_MANAGER="zypper"
    elif command -v apk &> /dev/null; then
        PACKAGE_MANAGER="apk"
    else
        PACKAGE_MANAGER="unknown"
    fi

    # Terminal emulator detection
    if [ -n "$TERM_PROGRAM" ]; then
        TERMINAL_EMULATOR="$TERM_PROGRAM"
    elif [ -n "$TERMINAL_EMULATOR" ]; then
        TERMINAL_EMULATOR="$TERMINAL_EMULATOR"
    elif [ -n "$XDG_SESSION_TYPE" ]; then
        TERMINAL_EMULATOR="$XDG_SESSION_TYPE"
    else
        TERMINAL_EMULATOR="unknown"
    fi

    # Desktop session
    if [ -n "$XDG_CURRENT_DESKTOP" ]; then
        DESKTOP_SESSION="$XDG_CURRENT_DESKTOP"
    elif [ -n "$DESKTOP_SESSION" ]; then
        DESKTOP_SESSION="$DESKTOP_SESSION"
    else
        DESKTOP_SESSION="unknown"
    fi

    # Use Python to substitute placeholders
    python3 -c "
import os, sys, re
with open('$TEMPLATE_FILE', 'r') as f:
    content = f.read()
subs = {
    'OS': '$OS',
    'KERNEL': '$KERNEL',
    'ARCH': '$ARCH',
    'SHELL': '$SHELL',
    'TERM': '$TERM',
    'USER': '$USER',
    'HOME': '$HOME',
    'PACKAGE_MANAGER': '$PACKAGE_MANAGER',
    'TERMINAL_EMULATOR': '$TERMINAL_EMULATOR',
    'DESKTOP_SESSION': '$DESKTOP_SESSION',
    'LANG': '$LANG',
}
for key, val in subs.items():
    content = content.replace('{{' + key + '}}', val)
with open('$OUTPUT_FILE', 'w') as f:
    f.write(content)
"
    success "System prompt generated from template at $OUTPUT_FILE"
else
    warn "Template file $TEMPLATE_FILE not found – using default hardcoded prompt."
    mkdir -p src/prompts
    cat > "$OUTPUT_FILE" <<'EOF'
You are an AI assistant that helps users with system administration and development tasks.
Your responses should be clear, concise, and include commands only when appropriate.
When you provide commands, place them inside triple backticks with the language "command", e.g.:

```command
ls -la
```

Always explain what the command does before showing it.
EOF
    success "Default system prompt created at $OUTPUT_FILE"
fi

# ── Create logs directory ──
mkdir -p logs

# ── Final instructions ──
echo ""
success "Setup complete!"
echo ""
info "Next steps:"
echo "  1. (Optional) Edit config/settings.json to adjust paths, port, or behaviour."
echo "  2. Log in to DeepSeek once to save the session:"
echo "       AnyNect login"
echo "     (or run 'python -m tests.test_browser' if you prefer the test harness)"
echo "  3. Start the server:"
echo "       AnyNect start"
echo "     (or just 'AnyNect' — start is the default subcommand)"
echo "  4. Open http://127.0.0.1:8000 in your browser (or the port you configured)."
echo ""
info "Available commands:"
echo "       AnyNect start [--host H] [--port P] [--reload]"
echo "       AnyNect setup"
echo "       AnyNect login"
echo "       AnyNect test [all|config|browser]"
echo "       AnyNect version"
echo ""
info "Note: The browser profile is stored in $HOME/.autonect/browser-profile."
echo "      You only need to log in once; cookies are saved."
echo ""
info "Note: 'AutoNect' remains available as a backward-compat alias for 'AnyNect'."