import os
import re
from pathlib import Path
from typing import Optional, Tuple

from .config import GuardConfig

def _glob_to_regex(pattern: str) -> str:
    """
    Convert a simple glob pattern (e.g., '*.pem', '.git/') to a
    regular expression suitable for matching absolute paths.
    """
    # Escape all special regex characters except * and ?
    escaped = re.escape(pattern)
    # Replace escaped wildcards back with regex equivalents
    escaped = escaped.replace(r"\*", ".*")   # * -> .*
    escaped = escaped.replace(r"\?", ".")    # ? -> .
    # If the original pattern ends with /, allow trailing content
    if pattern.endswith("/"):
        escaped += ".*"
    return escaped

class PathProtector:
    def __init__(self, config: GuardConfig):
        self.config = config
        self.workspace_root = config.workspace_root
        # Convert all protected/allowed patterns to regex
        self.protected_patterns = [
            re.compile(_glob_to_regex(p)) for p in config.protected_paths
        ]
        self.allowed_patterns = [
            re.compile(_glob_to_regex(p)) for p in config.allowed_paths
        ]

    def canonicalize(self, path_str: str) -> str:
        """Resolve symlinks and return absolute path."""
        try:
            return str(Path(path_str).expanduser().resolve())
        except Exception:
            return path_str  # fallback

    def is_protected(self, path_str: str) -> Tuple[bool, Optional[str]]:
        """
        Returns (is_protected, matched_pattern)
        """
        abs_path = self.canonicalize(path_str)

        # Check against protected patterns
        for pat in self.protected_patterns:
            if pat.search(abs_path):
                return True, pat.pattern

        # Check workspace boundary
        if self.workspace_root:
            try:
                Path(abs_path).relative_to(self.workspace_root)
            except ValueError:
                return True, "workspace_boundary"
        return False, None

    def is_allowed_path(self, path_str: str) -> bool:
        """Check if path matches an allowed pattern (overrides protection)."""
        abs_path = self.canonicalize(path_str)
        for pat in self.allowed_patterns:
            if pat.search(abs_path):
                return True
        return False

    def check_file_access(self, command: str) -> Optional[dict]:
        """
        Inspect command for file arguments and return a violation dict if any
        protected file is accessed.
        """
        parts = command.split()
        for i, part in enumerate(parts):
            if '/' in part or part.startswith('~') or part.startswith('.'):
                cleaned = part.strip("'\"")
                protected, pattern = self.is_protected(cleaned)
                if protected and not self.is_allowed_path(cleaned):
                    return {
                        "path": cleaned,
                        "pattern": pattern,
                        "reason": f"BAccess to protected path: {cleaned}"
                    }
        return None