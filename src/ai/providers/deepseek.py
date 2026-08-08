import time
import re
import base64
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
        Inject a MutationObserver that auto-clicks DeepSeek's
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
                        console.log('[AutoNect] Auto-clicking retry button');
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

        # Extract answer AND commands from the LAST assistant message.
        # Replace code blocks with unique, alphanumeric placeholders that survive
        # the HTML-to-markdown conversion without triggering escape characters.
        answer_data = self.page.evaluate("""
            () => {
                const containers = document.querySelectorAll('.ds-assistant-message-main-content');
                if (containers.length === 0) return { html: '', codeBlocks: [], commands: [] };
                const container = containers[containers.length - 1];
                const clone = container.cloneNode(true);

                const codeBlocks = [];
                const commands = [];

                clone.querySelectorAll('.md-code-block').forEach((block, idx) => {
                    const langTag = block.querySelector('.d813de27');
                    const pre = block.querySelector('pre');
                    const lang = langTag ? langTag.textContent.trim() : '';
                    const code = pre ? pre.textContent.trim() : '';

                    if (lang === 'command') {
                        commands.push({ code: code, raw: code });
                    }
                    codeBlocks.push({ idx, lang, code });

                    // Replace the code block with a safe, alphanumeric placeholder
                    const placeholder = document.createTextNode(
                        `\n\nCODEBLOCKPLACEHOLDER${idx}\n\n`
                    );
                    block.parentNode.replaceChild(placeholder, block);
                });

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

        # Convert HTML → markdown (placeholders stay as plain text)
        markdown = md(html_content, heading_style="ATX") if html_content else ""

        markdown = re.sub(r'\n*Copy\n*', '\n', markdown)
        markdown = re.sub(r'\n*Download\n*', '\n', markdown)

        # Customizable Colors Palette
        header_bg = "#222428"      # Header Bar Background matching matte theme
        header_text = "#f8f9fa"    # Language Title Text
        btn_bg = "#2e3137"         # Copy Button Background
        btn_text = "#f8f9fa"       # Copy Button Text
        code_bg = "#4a4a4a"        # Main Code Background
        code_text = "#e6e6e6"      # Code Text Color

        # Replace placeholders with pure HTML containers with a sticky header bar
        for block in code_blocks:
            idx = block["idx"]
            lang = block["lang"]
            code = block["code"]
            placeholder_pattern = r'CODEBLOCKPLACEHOLDER' + str(idx)

            display_lang = lang if lang else "text"

            # Encode raw code to Base64 for safe clipboard execution
            encoded_code = base64.b64encode(code.encode('utf-8')).decode('utf-8')

            # Escape HTML tags without escaping quotes into entities like &quot;
            escaped_code = code.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

            # Prevent empty lines (\n\n) from breaking Markdown raw HTML parsing mode
            escaped_code = re.sub(r'\n(?=\n)', '\n&#8203;', escaped_code)

            # Unified HTML Card with sticky header bar styling
            formatted_block = (
                f'<div style="background-color: {code_bg} !important; border-radius: 8px; margin: 1em 0; font-family: monospace; position: relative;">'
                f'<div style="display: flex; justify-content: space-between; align-items: center; '
                f'background-color: {header_bg} !important; color: {header_text}; padding: 8px 12px; font-size: 13px; '
                f'position: sticky; top: 0; z-index: 10; border-top-left-radius: 8px; border-top-right-radius: 8px;">'
                f'<span style="font-weight: bold; text-transform: uppercase;">{display_lang}</span>'
                f'<button onclick="navigator.clipboard.writeText(decodeURIComponent(escape(window.atob(\'{encoded_code}\')))); '
                f'this.innerText=\'Copied!\'; setTimeout(() => this.innerText=\'Copy\', 2000);" '
                f'style="background: {btn_bg}; border: none; color: {btn_text}; padding: 4px 10px; '
                f'border-radius: 4px; cursor: pointer; font-family: inherit; font-size: 12px; transition: background 0.2s;">'
                f'Copy'
                f'</button>'
                f'</div>'
                f'<pre style="background-color: {code_bg} !important; color: {code_text}; padding: 12px; margin: 0; overflow-x: auto; font-size: 14px; line-height: 1.4; border: none; border-bottom-left-radius: 8px; border-bottom-right-radius: 8px;">'
                f'<code class="language-{display_lang}" style="background-color: transparent !important; color: inherit; font-family: inherit;">'
                f'{escaped_code}'
                f'</code>'
                f'</pre>'
                f'</div>'
            )

            markdown = re.sub(placeholder_pattern, f"\n\n{formatted_block}\n\n", markdown, flags=re.MULTILINE)

        # Safety net: remove any placeholders that weren't replaced
        markdown = re.sub(r'\s*CODEBLOCKPLACEHOLDER\d+\s*', '\n', markdown)

        # Fix task lists, normalise markers, clean up spacing
        markdown = re.sub(
            r'\*\s*☑\s*\n\s*\n\s*(.*?)(?=\n|$)',
            r'- [x] \1',
            markdown,
            flags=re.DOTALL,
        )
        markdown = re.sub(
            r'\*\s*□\s*\n\s*\n\s*(.*?)(?=\n|$)',
            r'- [ ] \1',
            markdown,
            flags=re.DOTALL,
        )
        markdown = re.sub(r'^(\s*)\+ ', r'\1* ', markdown, flags=re.MULTILINE)
        markdown = markdown.replace(
            "notalinknot a linknotalinknotaurlnot a urlnotaurl",
            "\\[not a link\\]\\(not a url\\)"
        )
        markdown = markdown.replace(
            "\n# Not a heading\n",
            "\n\\# Not a heading\n"
        )
        markdown = re.sub(r'\n---\n---', '\n---\n\n---', markdown)
        markdown = re.sub(r'\n{3,}', '\n\n', markdown)

        markdown = markdown.strip()

        print("[DeepSeek] Extraction complete")
        return {
            "thinking": thinking_text,
            "answer": markdown,
            "commands": commands,
        }

    def close(self):
        self.browser.close()