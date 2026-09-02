#!/usr/bin/env python3
"""
Launcher script for AutoNect.
Reads config, sets the port, and starts the server.
"""

import sys
import os
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.core.config import config
from src.web.server import app
import uvicorn


def main():
    port = config.get("server", "port", default=8000)
    host = config.get("server", "host", default="127.0.0.1")
    reload = config.get("server", "reload", default=False)

    print(f"🚀 Starting AutoNect on http://{host}:{port}")
    uvicorn.run(
        "src.web.server:app",
        host=host,
        port=port,
        reload=reload,
        log_level="info",
    )


if __name__ == "__main__":
    main()