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

    def _inject_retry_observer(self):
        """
        Inject a MutationObserver that auto‑clicks DeepSeek's
        "Check network and retry" button the instant it appears.
        """
        self.page.evaluate("""
            () => {
                if (window.__autonect_retry_observer) return;
                const observer = new MutationObserver(() => {
                    const retryBtn = document.querySelector(
                        'div[role="button"].ds-button--warning'
                    );
                    if (retryBtn) {
                        console.log('[AutoNect] Auto‑clicking retry button');
                        retryBtn.click();
                    }
                });
                observer.observe(document.body, {
                    childList: true,
                    subtree: true,
                });
                window.__autonect_retry_observer = observer;
            }
        """)

    def _wait_for_response(self):
        print("[DeepSeek] Waiting for response (retry observer active) ...")

        # Inject the retry observer BEFORE waiting
        self._inject_retry_observer()

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
                timeout=180000
            )
        except Exception:
            raise TimeoutError("DeepSeek response timeout")

        print("[DeepSeek] Response finished")

    def get_response(self):
        self._wait_for_response()

        print("[DeepSeek] Extracting response...")

        # Extract thinking from the LAST thinking block, with code blocks removed
        thinking_text = self.page.evaluate("""
            () => {
                const blocks = document.querySelectorAll('.ds-think-content');
                if (blocks.length === 0) return '';
                const lastBlock = blocks[blocks.length - 1];
                const clone = lastBlock.cloneNode(true);
                clone.querySelectorAll('.md-code-block').forEach(el => el.remove());
                return clone.innerText.trim();
            }
        """)

        # Extract answer AND commands from the LAST assistant message
        answer_data = self.page.evaluate("""
            () => {
                const containers = document.querySelectorAll('.ds-assistant-message-main-content');
                if (containers.length === 0) return { html: '', codeBlocks: [], commands: [] };
                const container = containers[containers.length - 1];

                const codeBlocks = [];
                const commands = [];
                const clone = container.cloneNode(true);

                clone.querySelectorAll('.md-code-block').forEach((block) => {
                    const langTag = block.querySelector('.d813de27');
                    const pre = block.querySelector('pre');
                    const lang = langTag ? langTag.textContent.trim() : '';
                    const code = pre ? pre.textContent.trim() : '';

                    if (lang === 'command') {
                        commands.push({ code: code, raw: code });
                    }
                    codeBlocks.push({ lang, code });
                });

                clone.querySelectorAll('.md-code-block').forEach(el => el.remove());

                return {
                    html: clone.innerHTML,
                    codeBlocks: codeBlocks,
                    commands: commands,
                };
            }
        """)

        html_content = answer_data["html"] if answer_data else ""
        code_blocks = answer_data["codeBlocks"] if answer_data else []
        commands = answer_data["commands"] if answer_data else []

        markdown = md(html_content, heading_style="ATX") if html_content else ""

        import re
        markdown = re.sub(r'\n*Copy\n*', '\n', markdown)
        markdown = re.sub(r'\n*Download\n*', '\n', markdown)
        markdown = re.sub(r'\n{3,}', '\n\n', markdown)

        # Append code blocks at the end
        for block in code_blocks:
            lang = block["lang"]
            code = block["code"]
            if lang:
                markdown += f"\n```{lang}\n{code}\n```\n"
            else:
                markdown += f"\n```\n{code}\n```\n"

        markdown = markdown.strip()

        print("[DeepSeek] Extraction complete")
        return {
            "thinking": thinking_text,
            "answer": markdown,
            "commands": commands,
        }

    def close(self):
        self.browser.close()