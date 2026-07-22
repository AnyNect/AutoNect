import queue
import time


class DOMObserver:

    def __init__(self, page):
        self.page = page
        self.events = queue.Queue()

    def start(self):
        self.page.expose_function("autonect_dom_event", self.handle_event)

        self.page.evaluate("""
            () => {
                const observer = new MutationObserver((mutations) => {
                    for (const mutation of mutations) {
                        let eventData = { type: mutation.type };
                        if (mutation.type === 'childList' || mutation.type === 'characterData') {
                            eventData.target = mutation.target.className || '';
                            eventData.text = mutation.target.innerText || '';
                        } else if (mutation.type === 'attributes') {
                            eventData.target = mutation.target.className || '';
                            eventData.attributeName = mutation.attributeName;
                            eventData.attributeValue = mutation.target.getAttribute(mutation.attributeName);
                        }
                        window.autonect_dom_event(eventData);
                    }
                });
                observer.observe(document.body, {
                    childList: true,
                    subtree: true,
                    characterData: true,
                    attributes: true,
                    attributeFilter: ['class']
                });
            }
        """)
        print("[Observer] Started")

    def handle_event(self, event):
        self.events.put(event)

    def clear_events(self):
        """Discard all pending events."""
        while not self.events.empty():
            try:
                self.events.get_nowait()
            except queue.Empty:
                break

    def wait_for_condition(self, condition, timeout=120):
        """
        Block until condition(event) returns True.
        Raises TimeoutError if timeout is reached.
        """
        start = time.time()
        while True:
            elapsed = time.time() - start
            if elapsed > timeout:
                raise TimeoutError("Observer condition timed out")
            try:
                event = self.events.get(timeout=timeout - elapsed)
            except queue.Empty:
                raise TimeoutError("Observer condition timed out")
            if condition(event):
                return event