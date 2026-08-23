from playwright.sync_api import sync_playwright
from patchright.sync_api import sync_playwright as patchright_playwright

from src.core.config import config


class BrowserManager:

    def __init__(self):
        self.headless = config.get(
            "browser",
            "headless",
            default=False
        )

        self.playwright = None
        self.browser = None
        self.context = None
        self.page = None

    def launch(self):
        if self.headless:
            print("[Browser] Starting Patchright headless")
            self.playwright = patchright_playwright().start()
            self.browser = self.playwright.chromium.launch(headless=True)
            self.page = self.browser.new_page()
        else:
            print("[Browser] Starting Thorium headed")

            self.playwright = sync_playwright().start()

            self.context = self.playwright.chromium.launch_persistent_context(
                user_data_dir=config.get(
                    "browser",
                    "profile_path"
                ),
                executable_path=config.get(
                    "browser",
                    "thorium_path"
                ),
                headless=False
            )

            # ── REUSE EXISTING PAGE if available ──
            existing_pages = self.context.pages
            if existing_pages:
                # Use the last active page (or the one that was focused)
                self.page = existing_pages[-1]
                print(f"[Browser] Reusing existing page: {self.page.url}")
                # Optionally navigate to DeepSeek if not already there
                if "chat.deepseek.com" not in self.page.url:
                    self.page.goto("https://chat.deepseek.com")
                    self.page.wait_for_load_state("networkidle")
            else:
                self.page = self.context.new_page()
                print("[Browser] No existing page, creating new one")
                self.page.goto("https://chat.deepseek.com")
                self.page.wait_for_load_state("networkidle")

        print("[Browser] Ready")
        return self.page

    def close(self):
        # Safely close each component, ignoring thread errors
        try:
            if self.context:
                self.context.close()
        except Exception as e:
            print(f"[Browser] Context close error (ignored): {e}")

        try:
            if self.browser:
                self.browser.close()
        except Exception as e:
            print(f"[Browser] Browser close error (ignored): {e}")

        try:
            if self.playwright:
                self.playwright.stop()
        except Exception as e:
            print(f"[Browser] Playwright stop error (ignored): {e}")