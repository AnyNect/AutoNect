import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.ai.providers.deepseek import DeepSeekProvider
import time


def main():
    provider = DeepSeekProvider()
    provider.connect()

    # Get the page for manual control
    page = provider.page

    # Remove any existing exposed function if needed
    page.evaluate("""() => {
        window._autonect_log = [];
        window._observer = new MutationObserver((mutations) => {
            mutations.forEach(m => {
                let entry = {
                    type: m.type,
                    target: m.target.className || '',
                    text: (m.target.innerText || '').substring(0, 50)
                };
                window._autonect_log.push(entry);
            });
        });
        window._observer.observe(document.body, {
            childList: true,
            subtree: true,
            characterData: true,
            attributes: true,
            attributeFilter: ['class']
        });
    }""")

    # Inject prompt
    page.evaluate("""
        (text) => {
            const textarea = document.querySelector('textarea[placeholder="Message DSeek"]');
            const setter = Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, "value").set;
            setter.call(textarea, text);
            textarea.dispatchEvent(new Event("input", { bubbles: true }));
            textarea.dispatchEvent(new Event("change", { bubbles: true }));
        }
    """, "Explain AutoNect in one sentence.")

    # Click send
    button = page.locator('div[role="button"].ds-button--primary:not(.ds-button--disabled)').last
    button.click()

    print("[Diagnostic] Prompt sent. Waiting for user to confirm generation finished...")
    input("Press Enter after you see the final disabled send button (like your example).")

    # Retrieve log
    log = page.evaluate("() => window._autonect_log")
    print("\n[Diagnostic] Last 50 mutations:")
    for entry in log[-50:]:
        print(entry)

    provider.close()

if __name__ == "__main__":
    main()
