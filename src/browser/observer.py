import queue
import time
import logging

logger = logging.getLogger(__name__)


class DOMObserver:
    """
    Observes DOM mutations on a Playwright page and queues events for processing.

    Scope is deliberately narrow: only title changes are reported. Earlier
    versions forwarded every MutationObserver record, each carrying the full
    innerText of the mutated node. On a streaming LLM page that is thousands
    of synchronous JS->Python binding calls per second, which exhausts the
    Playwright driver's heap over a long session
    ("FATAL ERROR: Ineffective mark-compacts near heap limit") and destroys
    the page. The only consumer of these events is the chat-title sync, so
    only the title is sent now.
    """

    _MAX_QUEUED_EVENTS = 200

    _OBSERVER_JS = """
        (() => {
            const install = () => {
                if (window.__autonect_observer) return;

                let lastTitle = document.title || '';

                const emit = () => {
                    const t = document.title || '';
                    if (t === lastTitle) return;
                    lastTitle = t;
                    try {
                        window.autonect_dom_event({
                            type: 'title',
                            title: t,
                            path: location.pathname || '',
                        });
                    } catch (e) { /* swallow */ }
                };

                const observer = new MutationObserver(emit);
                observer.observe(document.head || document.documentElement, {
                    childList: true,
                    subtree: true,
                    characterData: true,
                });
                window.__autonect_observer = observer;

                try {
                    window.autonect_dom_event({
                        type: 'title',
                        title: document.title || '',
                        path: location.pathname || '',
                    });
                } catch (e) { /* swallow */ }
            };

            if (document.head || document.body) {
                install();
            } else if (document.readyState === 'loading') {
                document.addEventListener('DOMContentLoaded', install, { once: true });
            } else {
                install();
            }
        })();
    """

    def __init__(self, page):
        self.page = page
        self.events = queue.Queue(maxsize=self._MAX_QUEUED_EVENTS)
        self.listeners = []
        self._running = False

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
        Puts the event into the internal queue (dropping the oldest entry
        when the queue is full) and fans out to listeners.
        """
        try:
            self.events.put_nowait(event)
        except queue.Full:
            # Drop the oldest, keep the newest: the queue exists only for
            # debugging and must never grow without bound.
            try:
                self.events.get_nowait()
            except queue.Empty:
                pass
            try:
                self.events.put_nowait(event)
            except queue.Full:
                pass
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
