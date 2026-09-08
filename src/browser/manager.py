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
        # ── Common anti‑detection arguments ──
        common_args = [
            "--disable-blink-features=AutomationControlled",
            "--disable-dev-shm-usage",
            "--no-sandbox",
            "--disable-setuid-sandbox",
            "--disable-web-security",
            "--disable-features=IsolateOrigins,site-per-process",
            "--disable-site-isolation-trials",
            "--disable-features=BlockInsecurePrivateNetworkRequests",
        ]

        # Use a realistic user agent (matches Thorium/Chrome on Linux)
        user_agent = (
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.6099.109 Safari/537.36"
        )

        if self.headless:
            logger.info("Starting Patchright headless (with anti‑detection flags)")
            self.playwright = patchright_playwright().start()
            self.browser = self.playwright.chromium.launch(
                headless=True,
                args=common_args
            )
            self.page = self.browser.new_page(
                user_agent=user_agent,
                viewport={"width": 1280, "height": 720},
                locale="en-US",
                timezone_id="America/New_York",
                extra_http_headers={
                    "Accept-Language": "en-US,en;q=0.9",
                    "Accept-Encoding": "gzip, deflate, br",
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
                },
            )
        else:
            logger.info("Starting Thorium headed (with anti‑detection flags)")
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
                headless=False,
                args=common_args,
                user_agent=user_agent,
                viewport={"width": 1280, "height": 720},
                locale="en-US",
                timezone_id="America/New_York",
                extra_http_headers={
                    "Accept-Language": "en-US,en;q=0.9",
                    "Accept-Encoding": "gzip, deflate, br",
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
                },
            )

            existing_pages = self.context.pages
            if existing_pages:
                self.page = existing_pages[-1]
                logger.info("Reusing existing page: %s", self.page.url)
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