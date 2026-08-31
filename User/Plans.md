# Plans & Roadmap

## Current Goals

*(Add your current objectives here.)*

## Ideas

*(Add ideas you want to explore.)*

## Next Steps

*(What you plan to work on next.)*

## Current Goals

- [x] - **Adapt AutoNect's system prompt** – The current prompt is hardcoded for your system (CachyOS, Konsole, etc.). It needs to be made more generic or system-aware so it can adapt to other environments.

## Public Release Checklist

Before making AutoNect public, the following must be addressed:

### Critical UX & Safety
- [ ] Fix long output crashes (Issue #1): truncate or file fallback.
- [ ] Auto‑deny pending approvals when user sends new chat prompt.
- [ ] Command serialization (per‑session queue) to avoid concurrent execution.

### Security
- [ ] Audit `safe_commands.txt` – remove/keep commands intentionally.
- [ ] Add rate limiting for command execution.
- [ ] Enforce workspace root and path protection consistently.

### Documentation & Legal
- [ ] Update README with clear setup, config, and risk warnings.
- [ ] Complete `User/User.md`, `Guidelines.md`, `Journal.md` with policies.
- [ ] Add a LICENSE file (e.g., MIT, GPL, or "All Rights Reserved").

### Code Quality
- [ ] Remove `server_new.py` (broken) or merge useful parts.
- [ ] Ensure security tests pass (`test_guard.py`, `test_guard_strict.py`).
- [ ] Improve error handling and WebSocket cleanup.

### Configuration
- [ ] Document all fields in `config/settings.json`.
- [ ] Add sensible defaults for public release.

### Browser Automation
- [ ] Verify Playwright/Patchright compatibility with latest Thorium/Chromium.
- [ ] Add retry logic for DOM selectors.

### UI & Feedback
- [ ] Show "QUEUED" and "AUTO‑DENIED" status on command cards.
- [ ] Ensure terminal modal respects serialization queue.

### Logging & Monitoring
- [ ] Remove `uvicorn.log` from version control (already done).
- [ ] Add structured logging for production debugging.

### Deployment
- [ ] Provide installation script or Dockerfile.
- [ ] Test on a clean system.
