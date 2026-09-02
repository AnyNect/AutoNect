#!/usr/bin/env bash
set -e

# ── Colour output ──
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[0;33m'
NC='\033[0m'

function info() { echo -e "${BLUE}[INFO]${NC} $1"; }
function success() { echo -e "${GREEN}[OK]${NC} $1"; }
function warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }

# ── Activate virtual environment ──
if [ ! -d ".venv" ]; then
    warn "Virtual environment not found. Run ./setup.sh first."
    exit 1
fi
source .venv/bin/activate

# ── Check if browser profile exists ──
PROFILE_DIR=$(python -c "from src.core.config import config; print(config.get('browser', 'profile_path'))" 2>/dev/null || echo "")
if [ -z "$PROFILE_DIR" ]; then
    PROFILE_DIR="$HOME/.autonect/browser-profile"
fi

if [ ! -d "$PROFILE_DIR" ] || [ ! -f "$PROFILE_DIR/Default/Bookmarks" ]; then
    warn "Browser profile not found. Please log in to DeepSeek once."
    info "Opening browser for login..."
    python -m tests.test_browser
    echo ""
    info "Login complete. Press Enter to start the server."
    read -r
fi

# ── Start the server ──
info "Starting AutoNect server..."

# Use the Python launcher directly (avoids reliance on the AutoNect script)
python -m src.web.launcher
