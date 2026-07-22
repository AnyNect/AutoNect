from core.config import config


print("Headless:", config.get("browser", "headless"))
print("AI Provider:", config.get("ai", "provider"))
print("Auto Approve:", config.get("safety", "auto_approve"))