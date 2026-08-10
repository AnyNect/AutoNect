from .config import GuardConfig
from .session import SessionApprovalManager
from .policy import SecurityPolicy
from .constants import Decision

class CommandGuard:
    def __init__(self):
        self.config = GuardConfig()
        self.session_mgr = SessionApprovalManager()
        self.policy = SecurityPolicy(self.config, self.session_mgr)

    def evaluate(self, raw_cmd: str, session_id: str = "default"):
        decision, info = self.policy.evaluate(raw_cmd, session_id)
        # Convert to old interface: decision string + info dict
        return decision.value, info

    def approve_once(self, command: str, path: str = ""):
        self.session_mgr.approve_once(command, path)

    def approve_session(self, command: str, path: str = ""):
        self.session_mgr.approve_session(command, path)

    def deny(self, command: str, path: str = ""):
        self.session_mgr.deny(command, path)