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

        # Extract thinking from the LAST thinking block, with code blocks removed
        thinking_text = self.page.evaluate("""
            () => {
                const blocks = document.querySelectorAll('.ds-think-content');
                if (blocks.length === 0) return '';
                // Get the last thinking block (current message only)
                const lastBlock = blocks[blocks.length - 1];
                const clone = lastBlock.cloneNode(true);
                // Remove code blocks so they don't pollute the thinking text
                clone.querySelectorAll('.md-code-block').forEach(el => el.remove());
                return clone.innerText.trim();
            }
        """)

        # Extract answer from the LAST assistant message
        answer_markdown = self.page.evaluate("""
            () => {
                const containers = document.querySelectorAll('.ds-assistant-message-main-content');
                if (containers.length === 0) return '';
                const container = containers[containers.length - 1];
                
                // Collect code blocks
                const codeBlocks = [];
                const clone = container.cloneNode(true);
                clone.querySelectorAll('.md-code-block').forEach((block, index) => {
                    const langTag = block.querySelector('.d813de27');
                    const pre = block.querySelector('pre');
                    codeBlocks.push({
                        lang: langTag ? langTag.textContent.trim() : '',
                        code: pre ? pre.textContent.trim() : ''
                    });
                });
                
                // Remove code blocks from the clone
                clone.querySelectorAll('.md-code-block').forEach(el => el.remove());
                
                return {
                    html: clone.innerHTML,
                    codeBlocks: codeBlocks
                };
            }
        """)

        # Convert the remaining HTML to markdown
        from markdownify import markdownify as md
        html_content = answer_markdown["html"] if answer_markdown else ""
        code_blocks = answer_markdown["codeBlocks"] if answer_markdown else []
        
        markdown = md(html_content, heading_style="ATX") if html_content else ""

        # Clean Copy/Download artifacts
        import re
        markdown = re.sub(r'\n*Copy\n*', '\n', markdown)
        markdown = re.sub(r'\n*Download\n*', '\n', markdown)
        markdown = re.sub(r'\n{3,}', '\n\n', markdown)

        # Append code blocks
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
        }

    def _extract_answer_as_markdown(self) -> str:
        """
        Extract answer content as clean markdown.
        Uses two-step JS evaluation:
          1. Collect code blocks and their positions.
          2. Get the textContent of the answer (markdownify handles the rest).
        """
        # Step 1 — collect code blocks
        code_blocks = self.page.evaluate("""
            () => {
                const blocks = [];
                const elements = document.querySelectorAll('.md-code-block');
                elements.forEach((el) => {
                    const langEl = el.querySelector('.d813de27');
                    const pre = el.querySelector('pre');
                    blocks.push({
                        lang: langEl ? langEl.textContent.trim() : '',
                        code: pre ? pre.textContent.trim() : ''
                    });
                });
                return blocks;
            }
        """)

        # Step 2 — get the answer HTML, remove code blocks, convert to markdown
        html_content = self.page.evaluate("""
            () => {
                const container = document.querySelector('.ds-assistant-message-main-content');
                if (!container) return '';
                // Clone and remove code blocks
                const clone = container.cloneNode(true);
                clone.querySelectorAll('.md-code-block').forEach(el => el.remove());
                return clone.innerHTML;
            }
        """)

        # Convert HTML → markdown
        markdown = md(html_content, heading_style="ATX") if html_content else ""

        # Strip Copy/Download artifacts from the markdown
        import re
        markdown = re.sub(r'\n*Copy\n*', '\n', markdown)
        markdown = re.sub(r'\n*Download\n*', '\n', markdown)
        markdown = re.sub(r'\n{3,}', '\n\n', markdown)

        # Append code blocks at the end (most reliable placement)
        for block in code_blocks:
            lang = block["lang"]
            code = block["code"]
            if lang:
                markdown += f"\n```{lang}\n{code}\n```\n"
            else:
                markdown += f"\n```\n{code}\n```\n"

        return markdown.strip()

    def close(self):
        self.browser.close()