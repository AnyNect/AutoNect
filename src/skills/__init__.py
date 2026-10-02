"""Skill dispatch for non-command skills (attach, kaggle, ...).

'command' is handled by the server's PTY path and never reaches here.
"""
from typing import Callable, Dict

from src.skills import attach as _attach

Handler = Callable[[str, dict], dict]

HANDLERS: Dict[str, Handler] = {
    "attach": _attach.handle,
}


def get_handler(skill: str):
    return HANDLERS.get(skill)


__all__ = ["HANDLERS", "get_handler"]
