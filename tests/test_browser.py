import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.browser.manager import BrowserManager

browser = BrowserManager()
page = browser.launch()
page.goto("https://www.deepseek.com")
input("Press Enter to close...")
browser.close()
