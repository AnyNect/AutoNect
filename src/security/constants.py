# Severity levels for rule matching (from original DCG)
from enum import Enum

class Severity(Enum):
    CRITICAL = 4
    HIGH = 3
    MEDIUM = 2
    LOW = 1

# Decision types
class Decision(Enum):
    ALLOW = "allow"
    ASK = "ask"
    DENY = "deny"

# Session approval modes
class ApprovalMode(Enum):
    ONCE = "once"
    SESSION = "session"
    NONE = "none"