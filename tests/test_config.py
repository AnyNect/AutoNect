import sys
from pathlib import Path

# Add project root to path so we can import src
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.core.config import config

print("Headless:", config.get("browser", "headless"))
print("AI Provider:", config.get("ai", "provider"))
print("Auto Approve:", config.get("safety", "auto_approve"))
