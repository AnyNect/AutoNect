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
        self.listeners = []
        self._running = False

    # JS injected into every new document to install a MutationObserver
    # that reports events back to Python via autonect_dom_event.
    #
    # This runs as an init script (see start()) so it survives page.goto(),
    # and once via evaluate() so it also covers the document that is
    # currently loaded when start() is called.
    _OBSERVER_JS = """
        (() => {
            const install = () => {
                if (window.__autonect_observer) {
                    // Already installed on this document; do not double-register.
                    return;
                }
                const observer = new MutationObserver((mutations) => {
                    const pageTitle = document.title || '';
                    const pagePath = location.pathname || '';
                    for (const mutation of mutations) {
                        let eventData = { type: mutation.type, title: pageTitle, path: pagePath };
                        if (mutation.type === 'characterData') {
                            const parent = mutation.target.parentElement;
                            eventData.target = parent ? (parent.className || '') : '';
                            eventData.text = parent ? (parent.innerText || '')
                                                    : (mutation.target.textContent || '');
                        } else if (mutation.type === 'childList') {
                            eventData.target = mutation.target.className || '';
                            eventData.text = mutation.target.innerText || '';
                        } else if (mutation.type === 'attributes') {
                            eventData.target = mutation.target.className || '';
                            eventData.attributeName = mutation.attributeName;
                            eventData.attributeValue = mutation.target.getAttribute(mutation.attributeName);
                        }
                        try { window.autonect_dom_event(eventData); } catch (e) { /* swallow */ }
                    }
                });
                observer.observe(document.body, {
                    childList: true,
                    subtree: true,
                    characterData: true,
                    attributes: true,
                    attributeFilter: ['class']
                });
                window.__autonect_observer = observer;
            };

            // init scripts run at document_start, before <body> exists.
            // Defer installation until the DOM is ready.
            if (document.body) {
                install();
            } else if (document.readyState === 'loading') {
                document.addEventListener('DOMContentLoaded', install, { once: true });
            } else {
                install();
            }
        })();
    """

    def start(self):
        """
        Start observing DOM mutations.

        Registers a JS function on the browser context (survives navigation)
        and installs the MutationObserver via add_init_script so it re-runs
        on every new document after a page.goto(). Also evaluates once for
        the currently-loaded document.
        """
        logger.info("Starting DOM observer...")
        self.page.expose_function("autonect_dom_event", self.handle_event)

        # Persist across navigations.
        self.page.add_init_script(self._OBSERVER_JS)
        # Cover the document that is already open right now.
        try:
            self.page.evaluate(self._OBSERVER_JS)
        except Exception:
            logger.exception("Failed to install observer on current document")

        self._running = True
        logger.info("DOM observer started successfully")

    def subscribe(self, callback):
        """Register a callback to receive every DOM event."""
        self.listeners.append(callback)
        logger.debug("Observer listener registered (total=%d)", len(self.listeners))

    def handle_event(self, event):
        """
        Callback function exposed to the browser to receive DOM events.
        Puts the event into the internal queue.

        Args:
            event: Dictionary containing event data from the browser.
        """
        self.events.put(event)
        for cb in self.listeners:
            try:
                cb(event)
            except Exception:
                logger.exception("DOM observer listener raised")
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