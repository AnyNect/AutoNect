"""Skill dispatch for non-command skills (attach, kaggle, queue, ...).

'command' is handled by the server's PTY path and never reaches here,
except when it carries the queue prefix: the parser strips the prefix
and sets queued: True, and the dispatcher routes that entry to the
server-side background runner (queue_runner) instead of the PTY.
"""
from typing import Callable, Dict

from src.skills import attach as _attach
from src.skills import queue_runner as _queue_runner

Handler = Callable[[str, dict], dict]

HANDLERS: Dict[str, Handler] = {
    "attach": _attach.handle,
}


def get_handler(skill: str):
    return HANDLERS.get(skill)


__all__ = ["HANDLERS", "get_handler", "queue_runner"]
