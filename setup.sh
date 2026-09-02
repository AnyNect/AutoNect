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
    pip install -r requirements.txt
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

# Ensure setup.py exists
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

# Ensure launcher exists
if [ ! -f "src/web/launcher.py" ]; then
    warn "launcher.py not found, creating..."
    mkdir -p src/web
    cat > src/web/launcher.py <<'EOF'
#!/usr/bin/env python3
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from src.core.config import config
from src.web.server import app
import uvicorn

def main():
    port = config.get("server", "port", default=8000)
    host = config.get("server", "host", default="127.0.0.1")
    reload = config.get("server", "reload", default=False)
    print(f"🚀 Starting AutoNect on http://{host}:{port}")
    uvicorn.run("src.web.server:app", host=host, port=port, reload=reload, log_level="info")

if __name__ == "__main__":
    main()
EOF
    success "Created launcher.py"
fi

# ── Install package in editable mode ──
info "Installing AutoNect package in editable mode..."
pip install -e .

# ── Install Playwright browsers ──
info "Installing Playwright Chromium (headless) ..."
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

# ── Generate DeepSeek selectors file if missing ──
SELECTORS_FILE="src/ai/providers/deepseek_selectors.json"
if [ ! -f "$SELECTORS_FILE" ]; then
    info "Generating default DeepSeek selectors..."
    mkdir -p src/ai/providers
    cat > "$SELECTORS_FILE" <<'EOF'
{
  "textarea": "textarea[placeholder=\"Message DSeek\"]",
  "send_button": "div[role=\"button\"].ds-button--primary.ds-button--filled:not(.ds-button--disabled)",
  "retry_button": "div[role=\"button\"].ds-button--warning",
  "thinking_block": ".ds-think-content",
  "assistant_container": ".ds-assistant-message-main-content",
  "language_tag": ".d813de27",
  "code_block": ".md-code-block",
  "primary_button": "div[role=\"button\"].ds-button--primary:not(.ds-button--disabled)"
}
EOF
    success "DeepSeek selectors created at $SELECTORS_FILE."
else
    info "DeepSeek selectors already exist – skipping."
fi

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
echo "  2. Log in to DeepSeek once to save session:"
echo "       python -m tests.test_browser"
echo "  3. Start the server:"
echo "       AutoNect"
echo "     (or run 'python -m src.web.launcher' if you prefer)"
echo "  4. Open http://127.0.0.1:8000 in your browser (or the port you configured)."
echo ""
info "Note: The browser profile is stored in $HOME/.autonect/browser-profile."
echo "      You only need to log in once; cookies are saved."