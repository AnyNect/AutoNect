import time
import re
import base64
import logging
import json
from pathlib import Path
from markdownify import markdownify as md
from src.ai.provider import AIProvider
from src.browser.manager import BrowserManager
from src.browser.observer import DOMObserver
from src.core.config import config

logger = logging.getLogger(__name__)

# Load selectors from config file
SELECTORS_FILE = Path(__file__).parent / "deepseek_selectors.json"
try:
    with open(SELECTORS_FILE, "r") as f:
        SELECTORS = json.load(f)
    logger.debug("Loaded DeepSeek selectors from %s", SELECTORS_FILE)
except FileNotFoundError:
    # Fallback defaults
    SELECTORS = {
        "textarea": 'textarea[placeholder="Message DSeek"]',
        "send_button": 'div[role="button"].ds-button--primary.ds-button--filled:not(.ds-button--disabled)',
        "processing_svg_paths": ["M2 4.88C2 3.68", "M34,18 C34,9.163444"],
        "retry_button": 'div[role="button"].ds-button--warning',
        "thinking_block": ".ds-think-content",
        "assistant_container": ".ds-assistant-message-main-content",
        "language_tag": ".d813de27",
        "code_block": ".md-code-block",
        "primary_button": 'div[role="button"].ds-button--primary:not(.ds-button--disabled)',
    }
    logger.warning("Selectors file not found; using built‑in fallback selectors")

class DeepSeekProvider(AIProvider):
    def __init__(self):
        self.browser = BrowserManager()
        self.page = None
        self.observer = None
        self.base_url = config.get("ai", "base_url", default="https://chat.deepseek.com")
        self.response_timeout = config.get("ai", "response_timeout_ms", default=180000)
        self.selectors = SELECTORS

    def _saved_url(self):
        """URL saved before the last shutdown, if it belongs to this
        provider's own site.  Lets startup go STRAIGHT to the last chat
        instead of base_url -> last chat (two navigations)."""
        try:
            import json
            from pathlib import Path
            f = Path("data/last_url.json")
            if not f.exists():
                return None
            saved = json.loads(f.read_text()).get("url")
            if not saved:
                return None
            base_host = self.base_url.split("//")[-1].split("/")[0]
            if base_host and base_host in saved:
                return saved
        except Exception as e:
            logger.debug("saved-url lookup failed: %s", e)
        return None

    def connect(self):
        logger.info("Connecting to DeepSeek...")
        self.page = self.browser.launch()

        # Go directly to the last chat if we have one; else the base page.
        target = self._saved_url() or self.base_url
        if target not in self.page.url:
            logger.info("Navigating to %s", target)
            self.page.goto(target, timeout=30000)
            try:
                self.page.wait_for_load_state("networkidle", timeout=15000)
            except Exception:
                pass

        self.observer = DOMObserver(self.page)
        self.observer.start()

        self._click_retry_loading()

        logger.info("DeepSeek connected successfully")

    def _ensure_page(self):
        try:
            self.page.evaluate("1")
        except Exception as e:
            logger.warning("Page is closed or unresponsive: %s", e)
            logger.info("Attempting to reconnect...")
            try:
                self.browser.close()
            except Exception:
                pass
            self.connect()
            time.sleep(1)

    def _is_processing(self):
        """True while DeepSeek is generating a reply.

        The send slot morphs into a Stop button during generation. The
        Stop icon's SVG path prefixes are stable (SVG geometry does not
        rotate like class hashes). The ds-button--disabled class is NOT
        usable here: an empty textarea shows the same class.
        """
        sigs = self.selectors.get("processing_svg_paths", [
            "M2 4.88C2 3.68", "M34,18 C34,9.163444",
        ])
        sigs_js = json.dumps(sigs)
        try:
            return bool(self.page.evaluate(f"""
                () => {{
                    const sigs = {sigs_js};
                    const btns = document.querySelectorAll(
                        'div[role="button"].ds-button--primary.ds-button--circle'
                    );
                    for (const b of btns) {{
                        for (const p of b.querySelectorAll('svg path')) {{
                            const d = p.getAttribute('d') || '';
                            for (const s of sigs) {{
                                if (d.startsWith(s)) return true;
                            }}
                        }}
                    }}
                    return false;
                }}
            """))
        except Exception as e:
            logger.warning("_is_processing evaluate failed: %s", e)
            return False

    def _wait_until_processing(self, timeout_ms=15000):
        sigs = self.selectors.get("processing_svg_paths", [
            "M2 4.88C2 3.68", "M34,18 C34,9.163444",
        ])
        sigs_js = json.dumps(sigs)
        self.page.wait_for_function(f"""
            () => {{
                const sigs = {sigs_js};
                const btns = document.querySelectorAll(
                    'div[role="button"].ds-button--primary.ds-button--circle'
                );
                for (const b of btns) {{
                    for (const p of b.querySelectorAll('svg path')) {{
                        const d = p.getAttribute('d') || '';
                        for (const s of sigs) {{
                            if (d.startsWith(s)) return true;
                        }}
                    }}
                }}
                return false;
            }}
        """, timeout=timeout_ms)

    def send_prompt(self, prompt, max_send_attempts=3):
        self._ensure_page()
        textarea_selector = self.selectors["textarea"]
        send_btn_selector = self.selectors["send_button"]

        for attempt in range(1, max_send_attempts + 1):
            # If the model is already answering, do NOT resend - the
            # previous send took.
            if self._is_processing():
                logger.info("Model is already answering; not resending (attempt %d)", attempt)
                return

            logger.info("Injecting prompt (attempt %d/%d)...", attempt, max_send_attempts)

            try:
                self.page.wait_for_selector(textarea_selector, state="attached", timeout=5000)
            except Exception as e:
                if attempt == max_send_attempts:
                    logger.error("DeepSeek input not found after retries")
                    raise Exception("DeepSeek input not found after retries") from e
                logger.warning("Textarea not ready; reloading and retrying...")
                try:
                    self.page.reload()
                    self.page.wait_for_load_state("networkidle")
                except Exception as re:
                    logger.warning("Reload failed: %s", re)
                time.sleep(1)
                continue

            self.page.fill(textarea_selector, prompt)

            try:
                self.page.wait_for_function(
                    f"""
                    () => {{
                        const btn = document.querySelector('{send_btn_selector}');
                        return btn !== null;
                    }}
                    """,
                    timeout=10000
                )
                self.page.click(send_btn_selector)
                logger.info("Prompt sent via button click")
            except Exception as e:
                logger.warning("Button click failed, falling back to Enter key: %s", e)
                self.page.keyboard.press("Enter")
                logger.info("Prompt sent via Enter key")

            # Confirm the send took: the Stop button must appear.
            try:
                self._wait_until_processing(timeout_ms=10000)
                logger.info("Send confirmed: Stop button appeared")
                return
            except Exception:
                logger.warning("Send not confirmed on attempt %d/%d", attempt, max_send_attempts)
                if attempt < max_send_attempts:
                    logger.info("Reloading page and retrying send")
                    try:
                        self.page.reload()
                        self.page.wait_for_load_state("networkidle")
                    except Exception as re:
                        logger.warning("Reload failed: %s", re)
                    time.sleep(1)

        raise Exception(f"Failed to confirm prompt was sent after {max_send_attempts} attempts")

    def _click_send(self):
        logger.info("Clicking send button...")
        send_btn_selector = self.selectors["send_button"]
        button = self.page.locator(send_btn_selector).last
        button.wait_for(timeout=5000)
        button.click()
        logger.info("Send button clicked")

    def _click_retry_loading(self, attempts=5, delay=1.0):
        """Click DeepSeek's 'retry loading' button if it is showing.

        DeepSeek occasionally lands on a <span class="ds-button__content">
        retry loading</span> button when the SPA fails to finish loading.
        Check for it on every connect and click it so the user never has to.
        """
        js = """
            () => {
                const spans = document.querySelectorAll('span.ds-button__content');
                for (const s of spans) {
                    if (s.textContent.trim().toLowerCase() === 'retry loading') {
                        const target = s.closest('div[role="button"], button') || s;
                        target.click();
                        return true;
                    }
                }
                return false;
            }
        """
        for i in range(1, attempts + 1):
            try:
                clicked = self._safe_evaluate(js)
            except Exception as e:
                logger.warning("retry-loading check failed (attempt %d): %s", i, e)
                clicked = False
            if clicked:
                logger.info("Clicked 'retry loading' button (attempt %d)", i)
                return True
            time.sleep(delay)
        logger.debug("No 'retry loading' button found")
        return False

    def _inject_retry_observer(self):
        retry_selector = self.selectors["retry_button"]
        self._safe_evaluate(f"""
            () => {{
                if (window.__autonect_retry_observer) return;
                const observer = new MutationObserver(() => {{
                    const retryBtn = document.querySelector('{retry_selector}');
                    if (retryBtn) {{
                        console.log('[AutoNect] Auto-clicking retry button');
                        retryBtn.click();
                    }}
                }});
                observer.observe(document.body, {{
                    childList: true,
                    subtree: true,
                }});
                window.__autonect_retry_observer = observer;
            }}
        """)
        logger.debug("Retry observer injected")

    def _wait_for_response(self):
        logger.info("Waiting for response (retry observer active)...")
        self._inject_retry_observer()

        # The Stop button exists only while the server is generating.
        # Wait until it disappears. Do NOT use the send button's
        # ds-button--disabled class as the done signal: an empty
        # textarea shows the same class, so we would extract early and
        # read the previous assistant message.
        sigs = self.selectors.get("processing_svg_paths", [
            "M2 4.88C2 3.68", "M34,18 C34,9.163444",
        ])
        sigs_js = json.dumps(sigs)
        try:
            self.page.wait_for_function(f"""
                () => {{
                    const sigs = {sigs_js};
                    const btns = document.querySelectorAll(
                        'div[role="button"].ds-button--primary.ds-button--circle'
                    );
                    for (const b of btns) {{
                        for (const p of b.querySelectorAll('svg path')) {{
                            const d = p.getAttribute('d') || '';
                            for (const s of sigs) {{
                                if (d.startsWith(s)) return false;
                            }}
                        }}
                    }}
                    return true;
                }}
            """, timeout=self.response_timeout)
        except Exception:
            logger.error("DeepSeek response timeout (Stop button never disappeared)")
            raise TimeoutError("DeepSeek response timeout")

        logger.info("Response finished")

    def _safe_evaluate(self, expression, retries=3):
        """page.evaluate that survives an execution-context loss.

        DeepSeek can navigate or reload under us (e.g. the model's reply
        triggers a route change, or the renderer restarts). Playwright then
        raises "Execution context was destroyed" from the very next
        evaluate. Re-wait for the document, then retry. A closed page or
        a genuinely gone context is re-raised after the retries so the
        caller fails loudly rather than returning empty text.
        """
        last = None
        for attempt in range(1, retries + 1):
            try:
                return self.page.evaluate(expression)
            except Exception as e:
                msg = str(e)
                if "Execution context was destroyed" not in msg and \
                   "Cannot find context with specified id" not in msg and \
                   "Target closed" not in msg:
                    raise
                last = e
                logger.warning(
                    "evaluate failed (context lost, attempt %d/%d): %s",
                    attempt, retries, msg.splitlines()[0],
                )
                if attempt == retries:
                    break
                try:
                    self.page.wait_for_load_state("domcontentloaded", timeout=15000)
                except Exception:
                    pass
                time.sleep(0.5 * attempt)
        raise last

    def get_response(self):
        self._wait_for_response()
        logger.info("Extracting response...")

        thinking_selector = self.selectors["thinking_block"]
        thinking_text = self._safe_evaluate(f"""
            () => {{
                const blocks = document.querySelectorAll('{thinking_selector}');
                if (blocks.length === 0) return '';
                const lastBlock = blocks[blocks.length - 1];
                const clone = lastBlock.cloneNode(true);
                clone.querySelectorAll('.md-code-block').forEach(el => el.remove());
                return clone.innerText.trim();
            }}
        """)

        container_selector = self.selectors["assistant_container"]
        lang_tag_selector = self.selectors["language_tag"]
        code_block_selector = self.selectors["code_block"]

        answer_data = self._safe_evaluate(f"""
            () => {{
                const containers = document.querySelectorAll('{container_selector}');
                if (containers.length === 0) return {{ html: '', codeBlocks: [], commands: [] }};
                const container = containers[containers.length - 1];
                const clone = container.cloneNode(true);

                const codeBlocks = [];
                const commands = [];

                clone.querySelectorAll('{code_block_selector}').forEach((block, idx) => {{
                    const langTag = block.querySelector('{lang_tag_selector}');
                    const pre = block.querySelector('pre');
                    const lang = langTag ? langTag.textContent.trim() : '';
                    const code = pre ? pre.textContent.trim() : '';

                    if (lang === 'command') {{
                        commands.push({{ code: code, raw: code }});
                    }}
                    codeBlocks.push({{ idx, lang, code }});

                    const placeholder = document.createTextNode(
                        `\\n\\nCODEBLOCKPLACEHOLDER${{idx}}\\n\\n`
                    );
                    block.parentNode.replaceChild(placeholder, block);
                }});

                return {{
                    html: clone.innerHTML,
                    codeBlocks: codeBlocks,
                    commands: commands,
                }};
            }}
        """)

        # Rest of the code remains the same (markdown processing)
        html_content = answer_data["html"] if answer_data else ""
        code_blocks = answer_data["codeBlocks"] if answer_data else []
        commands = answer_data["commands"] if answer_data else []

        markdown = md(html_content, heading_style="ATX") if html_content else ""

        markdown = re.sub(r'\n*Copy\n*', '\n', markdown)
        markdown = re.sub(r'\n*Download\n*', '\n', markdown)

        header_bg  = "#222428"
        header_text = "#ececec"
        btn_bg     = "#2e3137"
        btn_text   = "#b4b4b4"
        code_bg    = "#1a1b1e"
        code_text  = "#d4d4d4"

        for block in code_blocks:
            idx = block["idx"]
            lang = block["lang"]
            code = block["code"]
            placeholder_str = f"CODEBLOCKPLACEHOLDER{idx}"

            display_lang = lang if lang else "text"

            if display_lang == "command":
                markdown = markdown.replace(placeholder_str, f"\n\n```command\n{code}\n```\n\n")
                continue

            encoded_code = base64.b64encode(code.encode('utf-8')).decode('utf-8')
            escaped_code = code.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            escaped_code = re.sub(r'\n(?=\n)', '\n&#8203;', escaped_code)

            formatted_block = (
                f'<div style="background-color: {code_bg} !important; border-radius: 8px; margin: 1em 0; font-family: monospace; position: relative; border: 1px solid rgba(255,255,255,0.1);">'
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

            markdown = markdown.replace(placeholder_str, f"\n\n{formatted_block}\n\n")

        markdown = re.sub(r'\s*CODEBLOCKPLACEHOLDER\d+\s*', '\n', markdown)

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

        logger.info("Extraction complete")
        return {
            "thinking": thinking_text,
            "answer": markdown,
            "commands": commands,
        }

    def close(self):
        logger.info("Closing DeepSeek provider...")
        self.browser.close()
        logger.info("DeepSeek provider closed")