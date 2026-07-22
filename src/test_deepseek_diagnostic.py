from src.ai.providers.deepseek import DeepSeekProvider
import time


def main():
    provider = DeepSeekProvider()
    provider.connect()

    # Inject a prompt but don't send yet
    provider.send_prompt("Hello")   # This will inject and send automatically in current code.
    # Wait, that will send. We need to bypass _click_send. So let's manually inject and then start observer.
    # Better: create a raw page test.

    # Actually, we can just use the provider's page and manually set up observer before sending.
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

    # Now manually click send? Let's click send via code but then wait for user.
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