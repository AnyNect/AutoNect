import logging
from playwright.sync_api import sync_playwright
from patchright.sync_api import sync_playwright as patchright_playwright

from src.core.config import config

logger = logging.getLogger(__name__)


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
            logger.info("Starting Patchright in headless mode")
            self.playwright = patchright_playwright().start()
            self.browser = self.playwright.chromium.launch(headless=True)
            self.page = self.browser.new_page()
            logger.debug("Headless browser launched, new page created")
        else:
            logger.info("Starting Thorium in headed mode")
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
                logger.info("Reusing existing page: %s", self.page.url)
                # Optionally navigate to DeepSeek if not already there
                if "chat.deepseek.com" not in self.page.url:
                    logger.debug("Navigating existing page to DeepSeek")
                    self.page.goto("https://chat.deepseek.com")
                    self.page.wait_for_load_state("networkidle")
            else:
                self.page = self.context.new_page()
                logger.info("No existing page, creating new one")
                self.page.goto("https://chat.deepseek.com")
                self.page.wait_for_load_state("networkidle")

        logger.info("Browser ready")
        return self.page

    def close(self):
        logger.info("Closing browser resources...")
        # Safely close each component, ignoring thread errors
        if self.context:
            try:
                self.context.close()
                logger.debug("Browser context closed")
            except Exception as e:
                logger.warning("Context close error (ignored): %s", e)

        if self.browser:
            try:
                self.browser.close()
                logger.debug("Browser instance closed")
            except Exception as e:
                logger.warning("Browser close error (ignored): %s", e)

        if self.playwright:
            try:
                self.playwright.stop()
                logger.debug("Playwright stopped")
            except Exception as e:
                logger.warning("Playwright stop error (ignored): %s", e)

        logger.info("Browser resources closed")