import json
from pathlib import Path
from typing import Optional, List

class GuardConfig:
    def __init__(self, config_path: str = "config/guard_config.json",
                 safe_commands_path: str = "config/safe_commands.txt"):
        self.config_path = Path(config_path)
        self.safe_commands_path = Path(safe_commands_path)
        self.data = self._load_config()
        self.safe_commands = self._load_safe_commands()

    def _load_config(self) -> dict:
        if not self.config_path.exists():
            raise FileNotFoundError(f"Config not found: {self.config_path}")
        with open(self.config_path) as f:
            return json.load(f)

    def _load_safe_commands(self) -> set:
        if not self.safe_commands_path.exists():
            return set()
        with open(self.safe_commands_path) as f:
            return set(line.strip() for line in f if line.strip() and not line.startswith('#'))

    def get(self, key, default=None):
        return self.data.get(key, default)

    @property
    def enabled(self) -> bool:
        return self.get("enabled", True)

    @property
    def default_decision(self) -> str:
        return self.get("default_decision", "ask")

    @property
    def fail_closed(self) -> bool:
        return self.get("fail_closed", True)

    @property
    def workspace_root(self) -> Optional[str]:
        root = self.get("workspace_root")
        if root:
            return str(Path(root).expanduser().resolve())
        return None

    @property
    def protected_paths(self) -> List[str]:
        return self.get("protected_paths", [])

    @property
    def allowed_paths(self) -> List[str]:
        return self.get("allowed_paths", [])

    @property
    def block_shell_composition(self) -> bool:
        return self.get("block_shell_composition", True)

    @property
    def block_git_force_push(self) -> bool:
        return self.get("block_git_force_push", True)

    @property
    def block_obfuscation(self) -> bool:
        return self.get("block_obfuscation", True)