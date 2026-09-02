#!/usr/bin/env bash
set -e

GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[0;33m'
NC='\033[0m'

function info() { echo -e "${BLUE}[INFO]${NC} $1"; }
function success() { echo -e "${GREEN}[OK]${NC} $1"; }
function warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }

if [ ! -d ".venv" ]; then
    warn "Virtual environment not found. Run ./setup.sh first."
    exit 1
fi
source .venv/bin/activate

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

info "Starting AutoNect server..."

# Try launcher first, fallback to uvicorn
if python -c "import src.web.launcher" 2>/dev/null; then
    python -m src.web.launcher
else
    warn "Launcher not found, using uvicorn directly"
    uvicorn src.web.server:app --host 127.0.0.1 --port 8000
fi