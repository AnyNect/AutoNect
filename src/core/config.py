import json
from pathlib import Path


class Config:
    def __init__(self, config_path="config/settings.json"):
        self.config_path = Path(config_path)
        self.data = self._load()

    def _load(self):
        if not self.config_path.exists():
            raise FileNotFoundError(
                f"Config file not found: {self.config_path}"
            )

        with open(self.config_path, "r", encoding="utf-8") as file:
            return json.load(file)

    def get(self, *keys, default=None):
        """
        Example:
        config.get("browser", "headless")
        """
        value = self.data

        for key in keys:
            if key not in value:
                return default
            value = value[key]

        return value


# Global config instance
config = Config()