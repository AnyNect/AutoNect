import queue
import time
import logging

logger = logging.getLogger(__name__)


class DOMObserver:
    """
    Observes DOM mutations on a Playwright page and queues events for processing.
    """

    def __init__(self, page):
        """
        Initialize the DOM observer.

        Args:
            page: Playwright page object to observe.
        """
        self.page = page
        self.events = queue.Queue()
        self._running = False

    def start(self):
        """
        Start observing DOM mutations by exposing a JavaScript function and injecting a MutationObserver.
        """
        logger.info("Starting DOM observer...")
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
                window.__autonect_observer = observer;  // Keep reference for debugging
            }
        """)
        self._running = True
        logger.info("DOM observer started successfully")

    def handle_event(self, event):
        """
        Callback function exposed to the browser to receive DOM events.
        Puts the event into the internal queue.

        Args:
            event: Dictionary containing event data from the browser.
        """
        self.events.put(event)
        logger.debug("DOM event received: %s", event.get("type", "unknown"))

    def clear_events(self):
        """
        Discard all pending events from the queue.
        """
        discarded = 0
        while not self.events.empty():
            try:
                self.events.get_nowait()
                discarded += 1
            except queue.Empty:
                break
        if discarded:
            logger.debug("Cleared %d pending DOM events", discarded)

    def wait_for_condition(self, condition, timeout=120):
        """
        Block until condition(event) returns True.

        Args:
            condition: Callable that takes an event dict and returns bool.
            timeout: Maximum seconds to wait.

        Returns:
            The event that satisfied the condition.

        Raises:
            TimeoutError: If no event satisfies the condition within timeout.
        """
        logger.debug("Waiting for DOM condition with timeout %d seconds", timeout)
        start = time.time()
        while True:
            elapsed = time.time() - start
            if elapsed > timeout:
                logger.error("DOM condition timed out after %d seconds", timeout)
                raise TimeoutError("Observer condition timed out")
            try:
                event = self.events.get(timeout=timeout - elapsed)
            except queue.Empty:
                logger.error("Queue empty; condition timed out")
                raise TimeoutError("Observer condition timed out")
            if condition(event):
                logger.debug("DOM condition satisfied with event: %s", event)
                return event
            else:
                logger.debug("Event did not satisfy condition: %s", event)