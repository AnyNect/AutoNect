import time
from markdownify import markdownify as md
from src.ai.provider import AIProvider
from src.browser.manager import BrowserManager
from src.browser.observer import DOMObserver


class DeepSeekProvider(AIProvider):

    def __init__(self):
        self.browser = BrowserManager()
        self.page = None
        self.observer = None

    def connect(self):
        print("[DeepSeek] Connecting...")
        self.page = self.browser.launch()
        self.page.goto("https://chat.deepseek.com")
        self.page.wait_for_load_state("networkidle")

        self.observer = DOMObserver(self.page)
        self.observer.start()

        print("[DeepSeek] Connected")

    def send_prompt(self, prompt):
        print("[DeepSeek] Injecting prompt...")

        result = self.page.evaluate(
            """
            (text) => {
                const textarea = document.querySelector(
                    'textarea[placeholder="Message DSeek"]'
                );
                if (!textarea) {
                    return false;
                }
                const setter = Object.getOwnPropertyDescriptor(
                    HTMLTextAreaElement.prototype,
                    "value"
                ).set;
                setter.call(textarea, text);
                textarea.dispatchEvent(new Event("input", { bubbles: true }));
                textarea.dispatchEvent(new Event("change", { bubbles: true }));
                return true;
            }
            """,
            prompt
        )

        if not result:
            raise Exception("DeepSeek input not found")

        print("[DeepSeek] Prompt injected")
        self._click_send()

    def _click_send(self):
        print("[DeepSeek] Clicking send...")

        button = self.page.locator(
            'div[role="button"].ds-button--primary.ds-button--filled:not(.ds-button--disabled)'
        ).last

        button.wait_for(timeout=5000)
        button.click()
        print("[DeepSeek] Sent")

    def _wait_for_response(self):
        print("[DeepSeek] Waiting for response (observer) ...")

        self.page.evaluate("""
            () => {
                window.__autonect_done = false;
                const observer = new MutationObserver((mutations) => {
                    for (const m of mutations) {
                        if (m.type === 'attributes' && m.attributeName === 'class') {
                            const targetClass = m.target.className;
                            if (targetClass.includes('ds-button--primary') &&
                                targetClass.includes('ds-button--disabled')) {
                                window.__autonect_done = true;
                                observer.disconnect();
                                return;
                            }
                        }
                    }
                });
                observer.observe(document.body, {
                    attributes: true,
                    subtree: true,
                    attributeFilter: ['class']
                });
            }
        """)

        try:
            self.page.wait_for_function(
                "window.__autonect_done",
                timeout=120000
            )
        except Exception:
            raise TimeoutError("DeepSeek response timeout")

        print("[DeepSeek] Response finished")

    def get_response(self):
        self._wait_for_response()

        print("[DeepSeek] Extracting response...")

        # Extract thinking (from DOM, as before)
        thinking_text = ""
        thinking_elements = self.page.locator(".ds-think-content")
        if thinking_elements.count() > 0:
            thinking_text = "\n".join(
                thinking_elements.nth(i).inner_text()
                for i in range(thinking_elements.count())
            )

        # Extract answer HTML
        answer_html = ""
        answer_elements = self.page.locator(".ds-assistant-message-main-content")
        if answer_elements.count() > 0:
            answer_html = answer_elements.last.inner_html()

        # Convert HTML → markdown (like DeepSeek's Copy button)
        answer_markdown = md(answer_html, heading_style="ATX") if answer_html else ""

        print("[DeepSeek] Extraction complete")
        return {
            "thinking": thinking_text,
            "answer": answer_markdown,
        }

    def close(self):
        self.browser.close()