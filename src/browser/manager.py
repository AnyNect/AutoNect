from playwright.sync_api import sync_playwright
from patchright.sync_api import sync_playwright as patchright_playwright

from core.config import config


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

            self.browser = self.playwright.chromium.launch(
                headless=True
            )

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

            self.page = self.context.new_page()


        print("[Browser] Ready")

        return self.page


    def close(self):

        if self.context:
            self.context.close()

        if self.browser:
            self.browser.close()

        if self.playwright:
            self.playwright.stop()