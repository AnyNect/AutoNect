import logging
from .config import GuardConfig
from .session import SessionApprovalManager
from .policy import SecurityPolicy
from .constants import Decision

logger = logging.getLogger(__name__)


class CommandGuard:
    def __init__(self):
        self.config = GuardConfig()
        self.session_mgr = SessionApprovalManager()
        self.policy = SecurityPolicy(self.config, self.session_mgr)
        logger.info("CommandGuard initialized with config: enabled=%s, default_decision=%s",
                    self.config.enabled, self.config.default_decision)

    def evaluate(self, raw_cmd: str, session_id: str = "default"):
        logger.debug("Evaluating command: %s (session=%s)", raw_cmd[:100], session_id)
        decision, info = self.policy.evaluate(raw_cmd, session_id)
        logger.info("Command evaluation result: decision=%s, reason=%s",
                    decision.value, info.get("reason") if info else "None")
        if decision == Decision.DENY:
            logger.warning("Command DENIED: %s | Reason: %s", raw_cmd[:100], info.get("reason") if info else "No reason")
        elif decision == Decision.ASK:
            logger.info("Command ASK: %s | Reason: %s", raw_cmd[:100], info.get("reason") if info else "No reason")
        else:
            logger.debug("Command ALLOWED: %s", raw_cmd[:100])
        return decision.value, info

    def approve_once(self, command: str, path: str = ""):
        logger.info("Approving command once: %s (path=%s)", command[:50], path)
        self.session_mgr.approve_once(command, path)

    def approve_session(self, command: str, path: str = ""):
        logger.info("Approving command for session: %s (path=%s)", command[:50], path)
        self.session_mgr.approve_session(command, path)

    def deny(self, command: str, path: str = ""):
        logger.info("Denying command: %s (path=%s)", command[:50], path)
        self.session_mgr.deny(command, path)