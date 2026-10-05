#!/usr/bin/env python3
"""Manual browser probe -- NOT a pytest test.

Opens DeepSeek in the configured persistent profile and blocks until
you press Enter. It used to live at tests/test_browser.py and launched
the browser at IMPORT time, so `pytest tests/` failed collection with a
profile-lock error and `AnyNect test` (which maps `all` -> pytest
tests/) was unusable.

Run it directly:  .venv/bin/python scripts/manual/browser_probe.py
It needs the persistent profile to be FREE (no other AutoNect running).
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.browser.manager import BrowserManager

def main() -> int:
    browser = BrowserManager()
    try:
        page = browser.launch()
        page.goto("https://www.deepseek.com")
        input("Press Enter to close...")
    finally:
        browser.close()
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
