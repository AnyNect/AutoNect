from typing import Dict, Tuple, Optional
from .constants import ApprovalMode

class SessionApprovalManager:
    def __init__(self):
        # Map (command, path) -> (approval_mode, timestamp)
        self.approvals: Dict[Tuple[str, str], ApprovalMode] = {}
        self.session_id: Optional[str] = None

    def set_session(self, session_id: str):
        self.session_id = session_id

    def is_approved(self, command: str, path: str = "") -> bool:
        key = (command, path)
        mode = self.approvals.get(key)
        if mode == ApprovalMode.SESSION:
            return True
        if mode == ApprovalMode.ONCE:
            # Remove after use (consume once)
            del self.approvals[key]
            return True
        return False

    def approve_once(self, command: str, path: str = ""):
        self.approvals[(command, path)] = ApprovalMode.ONCE

    def approve_session(self, command: str, path: str = ""):
        self.approvals[(command, path)] = ApprovalMode.SESSION

    def deny(self, command: str, path: str = ""):
        # Store as denied? For simplicity, we just remove any approval
        key = (command, path)
        if key in self.approvals:
            del self.approvals[key]