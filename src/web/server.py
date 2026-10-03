import asyncio
import json
import os
import pty
import signal
import uuid
import fcntl
import termios
import struct
from typing import Optional
import re
from contextlib import asynccontextmanager
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
import logging
from logging.config import dictConfig
import subprocess
import threading

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request, File, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from starlette.middleware.base import BaseHTTPMiddleware

from src.ai.providers.deepseek import DeepSeekProvider
from src.parser.commands import extract_commands
from src.skills import get_handler as _get_skill_handler
from src.skills import queue_runner as _queue_runner
from src.security import CommandGuard
from src.core.config import config
from src.database import upsert_chat, add_message, get_chat_list, get_chat, get_chat_by_url, update_chat, delete_chat, update_chat_name, chat_exists

# =============================================================================
# Logging Configuration
# =============================================================================
LOG_CONFIG = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "default": {
            "format": "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
            "datefmt": "%Y-%m-%d %H:%M:%S",
        },
        "detailed": {
            "format": "%(asctime)s - %(name)s - %(levelname)s - %(pathname)s:%(lineno)d - %(message)s",
            "datefmt": "%Y-%m-%d %H:%M:%S",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "level": "INFO",
            "formatter": "default",
            "stream": "ext://sys.stdout",
        },
        "file": {
            "class": "logging.handlers.RotatingFileHandler",
            "level": "DEBUG",
            "formatter": "detailed",
            "filename": "logs/app.log",
            "maxBytes": 10_485_760,
            "backupCount": 5,
        },
    },
    "root": {
        "level": "DEBUG",
        "handlers": ["console", "file"],
    },
    "loggers": {
        "uvicorn": {"level": "INFO", "handlers": ["console"], "propagate": False},
        "uvicorn.error": {"level": "INFO", "handlers": ["console"], "propagate": False},
        "uvicorn.access": {"level": "INFO", "handlers": ["console"], "propagate": False},
    },
}

Path("logs").mkdir(exist_ok=True)

dictConfig(LOG_CONFIG)
logger = logging.getLogger(__name__)

# =============================================================================
# Application Setup
# =============================================================================

_provider_executor = ThreadPoolExecutor(max_workers=1)

provider: DeepSeekProvider | None = None
guard = CommandGuard()

# Chat id of the conversation the user is currently on. Set by /api/chat.
# Used by _on_dom_event to attribute DeepSeek title changes to the correct
# database row without a URL lookup.
_current_chat_id = None
_last_synced_title = {}

# Debounce state for title sync. DeepSeek's SPA churns the tab title during
# generation, so we only commit a title after it has been stable for
# DEBOUNCE_SECONDS. This prevents rapid oscillation writes.
_pending_titles = {}          # chat_id -> latest observed title
_pending_timers = {}          # chat_id -> threading.Timer
_pending_lock = threading.Lock()
DEBOUNCE_SECONDS = 2.5

# Titles DeepSeek shows transiently during page load. Never sync these;
# the real title always arrives later.
_PLACEHOLDER_TITLES = {
    "New chat",
    "DeepSeek",
    "DSeek",
    "DSeek - Into the Unknown",
    "Untitled",
}

BASE_DIR = Path(__file__).parent
LAST_URL_FILE = Path("data/last_url.json")
TEMPLATES_DIR = BASE_DIR / "templates"
STATIC_DIR = BASE_DIR / "static"

SUPPORTED_EXTENSIONS_PATH = STATIC_DIR / "supported-extensions.json"
try:
    _raw = json.loads(SUPPORTED_EXTENSIONS_PATH.read_text(encoding="utf-8"))
    SUPPORTED_EXTENSIONS = frozenset(str(e).lower().lstrip(".") for e in _raw)
    logger.info("Loaded %d supported file extensions", len(SUPPORTED_EXTENSIONS))
except Exception:
    logger.warning("Could not load %s; uploads will not be extension-validated",
                   SUPPORTED_EXTENSIONS_PATH)
    SUPPORTED_EXTENSIONS = frozenset()
INDEX_HTML = (TEMPLATES_DIR / "index.html").read_text(encoding="utf-8")

SYSTEM_PROMPT_PATH = Path("src/prompts/system.txt")
try:
    SYSTEM_PROMPT = SYSTEM_PROMPT_PATH.read_text(encoding="utf-8").strip()
    logger.info("System prompt loaded successfully")
except FileNotFoundError:
    SYSTEM_PROMPT = ""
    logger.warning("System prompt file not found at %s", SYSTEM_PROMPT_PATH)

MAX_WEBSOCKET_OUTPUT_BYTES = config.get("websocket", "max_output_bytes", default=150_000)
TERMINAL_COMMAND_TEMPLATE = config.get("terminal", "command", default=["konsole", "-e", "bash", "-c", "{command}; exec bash"])
FALLBACK_TERMINALS = config.get("terminal", "fallback_terminals", default=["gnome-terminal", "xterm"])
OUTPUT_FILE_THRESHOLD = 50 * 1024  # 50 KB: above this, output is tailed
FILE_ATTACH_THRESHOLD = 7 * 1024   # 7 KB: above this, attach as a file
PER_COMMAND_TAIL_BYTES = 7 * 1024  # 7 KB tail per command when over the ceiling

# ── Output cache ──
_output_cache = {}  # key: output_id, value: stdout string

# ── Temporary directory for large outputs ──
TMP_DIR = Path("data/tmp")
TMP_DIR.mkdir(parents=True, exist_ok=True)

# =============================================================================
# Lifespan & Middleware
# =============================================================================

def _flush_pending_title(chat_id):
    """Commit the pending title for a chat after the debounce window."""
    with _pending_lock:
        title = _pending_titles.pop(chat_id, None)
        _pending_timers.pop(chat_id, None)
    if not title:
        return
    try:
        chat = get_chat(chat_id)
        if not chat:
            return
        if chat.get("is_custom_name"):
            return
        if chat.get("name") == title:
            _last_synced_title[chat_id] = title
            return
        upsert_chat(chat_id, name=title)
        _last_synced_title[chat_id] = title
        logger.info("Synced chat title from tab (settled): %s -> %s", chat_id[:8], title)
    except Exception:
        logger.exception("Failed to flush pending title")


def _on_dom_event(event):
    """Handle a DOM mutation observed by the Playwright observer.

    Currently only reacts to DeepSeek chat-title changes: sync the new
    title to the database unless the user set a custom name for that chat.
    Runs on the Playwright thread; must be fast and non-blocking.
    """
    # Read the browser tab title. DeepSeek sets it to "<chat name> - DSeek",
    # which is the most reliable source of the current chat name. The suffix
    # is configurable via deepseek_selectors.json ("title_suffix").
    raw = (event.get("title") or "").strip()
    suffix = (provider.selectors.get("title_suffix") if provider else None) or " - DSeek"
    if raw.endswith(suffix):
        title = raw[:-len(suffix)].strip()
    else:
        title = raw

    # Ignore placeholder / brand-only titles.
    if not title or title in _PLACEHOLDER_TITLES or len(title) > 200:
        return

    # Attribute the title to the chat whose URL matches the current page.
    # Fall back to the last chat we messaged on if the URL has no match yet
    # (e.g. the row has not been written to the DB).
    path = event.get("path") or ""
    # DeepSeek chat URLs end in /a/chat/s/<uuid>; match on the uuid.
    uuid_part = ""
    if "/a/chat/s/" in path:
        uuid_part = path.rsplit("/a/chat/s/", 1)[-1].split("/")[0].split("?")[0]
    matched = get_chat_by_url(uuid_part) if uuid_part else None
    chat_id = matched["id"] if matched else _current_chat_id
    if not chat_id:
        return
    if _last_synced_title.get(chat_id) == title:
        return

    # Schedule the write after a stability window. If another title arrives
    # before the timer fires, this one is replaced.
    with _pending_lock:
        _pending_titles[chat_id] = title
        old = _pending_timers.pop(chat_id, None)
        if old:
            old.cancel()
        t = threading.Timer(DEBOUNCE_SECONDS, _flush_pending_title, args=(chat_id,))
        t.daemon = True
        _pending_timers[chat_id] = t
        t.start()


def _save_last_url():
    """Persist the browser's current URL so a restart can return to it."""
    try:
        if provider and getattr(provider, "page", None):
            url = provider.page.url
            if url and url != "about:blank":
                LAST_URL_FILE.parent.mkdir(parents=True, exist_ok=True)
                LAST_URL_FILE.write_text(json.dumps({"url": url}))
    except Exception as e:
        logger.debug("save last url failed: %s", e)


def _restore_last_url():
    """Record the current chat id from the URL the browser is already on.

    Navigation to the last URL now happens inside provider.connect(), so
    startup goes straight there (no base_url -> last-chat double load).
    This only syncs in-memory state.
    """
    try:
        if not provider or not getattr(provider, "page", None):
            return
        url = provider.page.url or ""
        frag = url.rsplit("/", 1)[-1].split("?")[0]
        global _current_chat_id
        matched = get_chat_by_url(frag) if frag and frag != "about:blank" else None
        if matched:
            _current_chat_id = matched["id"]
            logger.info("Restored chat id: %s", _current_chat_id)
    except Exception as e:
        logger.debug("restore last url failed (ignored): %s", e)


@asynccontextmanager
def _stt_port_listening(port: int) -> bool:
    """True only if the STT app actually answers HTTP.

    A bare TCP connect is not enough: a uvicorn shutting down keeps its
    listening socket briefly, so connect_ex() succeeds against a dead
    process and the caller skips starting a real one. An HTTP GET to the
    root proves the ASGI app is serving (any status counts).
    """
    import socket
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.3)
        if sock.connect_ex(("127.0.0.1", port)) != 0:
            return False
    try:
        import urllib.request
        urllib.request.urlopen(f"http://127.0.0.1:{port}/", timeout=1.0)
        return True
    except urllib.error.HTTPError:
        return True          # answered with an HTTP status -> app is up
    except Exception:
        return False          # connected but no HTTP -> not really up


def _maybe_start_stt():
    """Start the STT service (:6012) if it is not already serving."""
    _start_stt_process(force=False)


async def lifespan(app: FastAPI):
    global provider
    logger.info("Starting application lifespan")
    loop = asyncio.get_running_loop()
    global _event_loop
    _event_loop = loop
    _queue_runner.set_on_complete(_on_queue_job_done)
    # Best-effort: bring up the local STT service so the mic works.
    try:
        _maybe_start_stt()
    except Exception:
        logger.exception("STT auto-start failed (non-fatal)")
    provider = DeepSeekProvider()
    try:
        await loop.run_in_executor(_provider_executor, provider.connect)
        logger.info("DeepSeek provider connected")
        await loop.run_in_executor(_provider_executor, _restore_last_url)
        _load_pending_restart_report()
        if provider.observer:
            provider.observer.subscribe(_on_dom_event)
            logger.info("Subscribed to DOM observer for title sync")
        _host = os.environ.get("AUTONECT_HOST", "127.0.0.1")
        _port = os.environ.get("AUTONECT_PORT", "8000")
        _url = f"http://{_host}:{_port}"
        print("\n" + "=" * 60)
        print("✅ AnyNect is ready!")
        print(f"🌐 Open the UI at: \033]8;;{_url}\033\\{_url}\033]8;;\033\\")
        print("📝 Press Ctrl+C to stop the server")
        print("=" * 60 + "\n")
    except Exception as e:
        logger.exception("Failed to connect DeepSeek provider")
        raise
    yield
    logger.info("Shutting down application lifespan")
    await loop.run_in_executor(_provider_executor, _save_last_url)
    await loop.run_in_executor(_provider_executor, provider.close)
    _provider_executor.shutdown(wait=False)
    logger.info("Cleanup completed")


class LoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        logger.info("Request: %s %s", request.method, request.url.path)
        try:
            response = await call_next(request)
            logger.info("Response: %s %s - Status %d", request.method, request.url.path, response.status_code)
            return response
        except Exception as e:
            logger.exception("Unhandled exception during request: %s %s", request.method, request.url.path)
            raise


app = FastAPI(title="AutoNect Chat", lifespan=lifespan)
app.add_middleware(LoggingMiddleware)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

# =============================================================================
# Pydantic Models
# =============================================================================

class ChatRequest(BaseModel):
    prompt: str
    session_id: Optional[str] = None


class ChatResponse(BaseModel):
    thinking: str
    answer: str
    commands: list[dict] = []
    session_id: str


class AIFeedbackRequest(BaseModel):
    commands: list[dict] = []
    files: list[str] = []
    command: str | None = None
    stdout: str | None = None
    stderr: str | None = None
    exit_code: int | None = None
    chat_id: str | None = None
    output_id: str | None = None


class AIFeedbackResponse(BaseModel):
    thinking: str
    answer: str
    commands: list[dict] = []


class OpenTerminalRequest(BaseModel):
    command: str


class NavigateRequest(BaseModel):
    url: str


# =============================================================================
# Helper Functions
# =============================================================================

def _tail_bytes(text: str, n: int) -> str:
    """Return the last n bytes of text, with a marker when truncated."""
    if not text:
        return ""
    if len(text) <= n:
        return text
    return f"...[truncated, showing last {n} bytes]\n" + text[-n:]


def build_wrapped_command_output(command: str, exit_code: int, stdout: str, stderr: str) -> str:
    return (
        f"[SYSTEM_COMMAND_OUTPUT]\n"
        f"Command: {command}\n"
        f"Exit code: {exit_code}\n"
        f"stdout:\n{stdout}\n"
        f"stderr:\n{stderr}\n"
        f"[/SYSTEM_COMMAND_OUTPUT]"
    )


def build_wrapped_commands_output(commands: list[dict]) -> str:
    parts = []
    for cmd in commands:
        parts.append(
            f"[SYSTEM_COMMAND_OUTPUT]\n"
            f"Command: {cmd.get('command', '')}\n"
            f"Exit code: {cmd.get('exit_code', -1)}\n"
            f"stdout:\n{cmd.get('stdout', '')}\n"
            f"stderr:\n{cmd.get('stderr', '')}\n"
            f"[/SYSTEM_COMMAND_OUTPUT]"
        )
    return "\n\n".join(parts)


def _annotate_commands_with_safety(commands: list[dict], session_id: str = "default") -> list[dict]:
    annotated = []
    for cmd in commands:
        decision, info = guard.evaluate(cmd["code"], session_id)
        if decision == "ask":
            safety = "warn"
        else:
            safety = decision
        cmd["safety"] = safety
        cmd["safety_reason"] = info.get("reason", "") if safety != "allow" else ""
        annotated.append(cmd)
    return annotated


def _dispatch_skills(commands: list[dict], session_id: str) -> list[dict]:
    """Run non-command skills (attach, kaggle, ...) through their handlers.

    'command' is left untouched -- it runs through the PTY path in the
    frontend. Every other skill gets its payload handed to the handler
    and the result is stored under cmd['result']. Unknown skills drop.
    """
    out = []
    for cmd in commands:
        skill = cmd.get("skill", "command")
        if skill == "command":
            if cmd.get("queued"):
                # Background job: launch server-side, never the PTY.
                # Approval is deliberately skipped for v1 -- the
                # launch is still gated by the agent emitting the tag.
                try:
                    result = _queue_runner.launch(cmd["code"],
                                                  {"session_id": session_id})
                except Exception as e:
                    logger.exception("queue launch failed")
                    result = {"error": str(e)}
                entry = dict(cmd)
                entry["skill"] = "queue"
                entry["result"] = result
                out.append(entry)
                continue
            out.append(cmd); continue
        if skill == "attach":
            # Resolution happens at FEEDBACK time (after commands ran),
            # so files a command creates exist by then. Store the raw
            # paths for the frontend to send back.
            cmd = dict(cmd)
            cmd["result"] = {"paths": [
                ln.strip() for ln in cmd["code"].splitlines()
                if ln.strip() and not ln.strip().startswith("#")
            ]}
            out.append(cmd)
            continue
        handler = _get_skill_handler(skill)
        if handler is None:
            logger.warning("Unknown skill %r -- dropping", skill); continue
        try:
            result = handler(cmd["code"], {"session_id": session_id})
        except Exception as e:
            logger.exception("Skill %r raised", skill)
            result = {"error": str(e)}
        cmd = dict(cmd); cmd["result"] = result
        out.append(cmd)
    return out


def _extract_response(response: dict, session_id: str = "default") -> tuple[str, str, list[dict]]:
    thinking = response.get("thinking", "")
    answer = response.get("answer", "")
    commands = response.get("commands", [])

    if not commands:
        commands = extract_commands(answer)

    thinking_commands = extract_commands(thinking)
    thinking_codes = {cmd["code"] for cmd in thinking_commands}
    commands = [cmd for cmd in commands if cmd["code"] not in thinking_codes]
    commands = _annotate_commands_with_safety(commands, session_id)
    commands = _dispatch_skills(commands, session_id)
    return thinking, answer, commands


def clean_deepseek_markdown(text: str) -> str:
    if text.strip().startswith("```") and text.strip().endswith("```"):
        text = text.strip()[3:-3].strip()
    lines = text.splitlines()
    if lines and lines[0].strip().lower() in ["python", "javascript", "bash", "sh", "css", "html"]:
        lines = lines[1:]
    fence_count = sum(1 for line in lines if line.strip().startswith("```"))
    if fence_count % 2 == 1:
        lines.append("```")
    cleaned = "\n".join(lines)
    return cleaned


# =============================================================================
# HTTP Endpoints
# =============================================================================

@app.get("/", response_class=HTMLResponse)
async def index():
    logger.info("Serving index page")
    return HTMLResponse(
        content=INDEX_HTML,
        headers={
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Pragma": "no-cache",
            "Expires": "0",
        },
    )


@app.post("/api/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    logger.info("Chat request received, session_id=%s", request.session_id)
    if not provider:
        logger.error("Provider not initialized")
        return JSONResponse(status_code=500, content={"error": "Provider not initialized"})

    loop = asyncio.get_running_loop()

    # Decide new-vs-existing from the database, not from in-memory state.
    # An in-memory flag resets on every server restart, which caused
    # existing chats to be renamed to the last prompt on the next message.
    is_new_chat = (request.session_id is None) or (not chat_exists(request.session_id))
    if request.session_id is None:
        request.session_id = str(uuid.uuid4())

    if is_new_chat:
        logger.info("New session created: %s", request.session_id)
        full_prompt = f"{SYSTEM_PROMPT}\n\n{request.prompt}" if SYSTEM_PROMPT else request.prompt
    else:
        full_prompt = request.prompt
        logger.debug("Existing session: %s", request.session_id)

    # Append any finished background-job blocks to the outbound prompt.
    # Appended, not prepended -- the block rides the tail of whatever
    # message is next (user, feedback, or skill output).
    injected = _queue_runner.drain_injections()
    if injected:
        full_prompt = full_prompt + "\n\n" + injected
        logger.info("Injected %d bytes of background-job output", len(injected))

    def send_and_get():
        # If the assembled prompt exceeds the output-file threshold, attach
        # it as a file (mirroring the large-command-output path) instead of
        # filling the textarea, so nothing is truncated.
        if len(full_prompt) > OUTPUT_FILE_THRESHOLD:
            temp_file = TMP_DIR / f"prompt_{uuid.uuid4().hex[:8]}.txt"
            try:
                with open(temp_file, "w", encoding="utf-8") as f:
                    f.write(full_prompt)
                logger.info(
                    "Large prompt saved to %s (%s bytes)",
                    temp_file, temp_file.stat().st_size,
                )
                selector = provider.selectors.get("file_input", "input[type='file']")
                provider.page.wait_for_selector(selector, state="attached", timeout=10000)
                provider.page.set_input_files(selector, str(temp_file))
                logger.info("Large prompt attached to DeepSeek: %s", temp_file.name)
                provider.send_prompt(
                    "[USER_PROMPT]\n"
                    "The user's full message is attached as a file. "
                    "Read it and respond to it.\n"
                    "[/USER_PROMPT]"
                )
            except Exception as e:
                logger.error("Large-prompt file attach failed; sending inline: %s", e)
                provider.send_prompt(full_prompt)
            finally:
                try:
                    if temp_file.exists():
                        temp_file.unlink()
                except Exception:
                    pass
        else:
            provider.send_prompt(full_prompt)
        return provider.get_response()

    try:
        response = await loop.run_in_executor(_provider_executor, send_and_get)
        thinking, answer, commands = _extract_response(response, request.session_id)

        global _current_chat_id
        _current_chat_id = request.session_id

        def _grab_url():
            try:
                if provider and getattr(provider, "page", None):
                    return provider.page.url
            except Exception:
                pass
            return None

        deepseek_url = await loop.run_in_executor(_provider_executor, _grab_url)
        await loop.run_in_executor(_provider_executor, _save_last_url)
        chat_name = request.prompt[:50] if is_new_chat else None
        upsert_chat(request.session_id, deepseek_url, chat_name)

        add_message(request.session_id, "user", request.prompt)
        add_message(request.session_id, "assistant", answer, thinking, commands)

        logger.info("Chat completed for session %s, commands=%d", request.session_id, len(commands))
        return ChatResponse(
            thinking=thinking,
            answer=answer,
            commands=commands,
            session_id=request.session_id
        )
    except Exception as e:
        logger.exception("Error during chat processing for session %s", request.session_id)
        return JSONResponse(status_code=500, content={"error": str(e)})


@app.post("/api/ai-feedback", response_model=AIFeedbackResponse)
async def ai_feedback(request: AIFeedbackRequest):
    logger.info("AI feedback request received")

    stdout = request.stdout or ""
    # HARDENING (2026-10-02): when a BATCH of commands is present, do
    # NOT populate stdout from the output_id cache. output_id names ONE
    # command's output, and setting stdout_content from it makes the
    # is_multi gate below False -- the server then sends only that one
    # command's output and silently drops the rest of the batch. A
    # stale (cached) client could still send both fields, so the
    # server refuses to trust the single-output hint.
    if not stdout and request.output_id and not request.commands:
        cached = _output_cache.pop(request.output_id, None)
        if cached:
            stdout = cached
            logger.info("Retrieved stdout from cache using output_id %s (length: %s)", request.output_id, len(stdout))

    stdout_len = len(stdout) if stdout else 0
    logger.info("stdout length: %s bytes (threshold: %s)", stdout_len, OUTPUT_FILE_THRESHOLD)

    if not provider:
        logger.error("Provider not initialized")
        return JSONResponse(status_code=500, content={"error": "Provider not initialized"})

    loop = asyncio.get_running_loop()

    def send_wrapped_and_get():
        # A finished background job rides this feedback turn too.
        queued_block = _queue_runner.drain_injections()
        if queued_block:
            logger.info("Feedback: injecting %d bytes of background-job output",
                        len(queued_block))
        # Resolve <attach> files at FEEDBACK time -- after the commands
        # ran, so files a command just created now exist. Re-validate
        # through the attach handler so the allowlist still applies.
        # Files ride the SAME prompt as the command output.
        attach_paths = []
        for raw in (request.files or []):
            try:
                res = _get_skill_handler("attach")(raw, {})
                attach_paths.extend(f["path"] for f in res.get("files", []))
            except Exception as e:
                logger.warning("attach resolve failed for %r: %s", raw, e)

        has_cmd_work = bool(stdout) or bool(request.commands) or bool(request.command)

        if attach_paths:
            selector = provider.selectors.get("file_input", "input[type='file']")
            provider.page.wait_for_selector(selector, state="attached", timeout=10000)
            provider.page.set_input_files(selector, attach_paths)
            logger.info("Feedback: attached %d file(s)", len(attach_paths))

        # Attach-only turn: deliver the files, no command text.
        if not has_cmd_work:
            provider.send_prompt(
                "[ATTACHED FILES]\n"
                "The files you requested are attached. "
                "Read them and continue with the task.\n"
                "[/ATTACHED FILES]"
                + ("\n\n" + queued_block if queued_block else "")
            )
            return provider.get_response()

        attach_note = ""
        if attach_paths:
            attach_note = (
                "\n\n[ATTACHED FILES]\n"
                "The files you requested are attached. "
                "Read them and continue with the task.\n"
                "[/ATTACHED FILES]"
            )

        stdout_content = stdout
        command_display = request.command or ""
        cmds = request.commands or []
        is_multi = bool(cmds) and not stdout_content

        def _assemble(cmd_list):
            out = ""
            for cmd in cmd_list:
                out += f"Command: {cmd.get('command', '')}\n"
                out += f"Exit code: {cmd.get('exit_code', -1)}\n"
                out += f"stdout:\n{cmd.get('stdout', '')}\n"
                out += f"stderr:\n{cmd.get('stderr', '')}\n\n"
            return out

        if is_multi:
            stdout_content = _assemble(cmds)
            command_display = " | ".join(c.get('command', '') for c in cmds) or "multiple commands"

        # Original (pre-truncation) size drives the file-vs-inline decision.
        original_size = len(stdout_content) if stdout_content else 0

        # Ceiling: above OUTPUT_FILE_THRESHOLD (50 KB), tail to the last
        # PER_COMMAND_TAIL_BYTES (7 KB). Multi-command runs tail each
        # command's stdout and stderr; a single command's blob is tailed
        # whole. Truncation runs before the file-vs-inline decision so the
        # attached file carries the tailed content.
        if stdout_content and original_size > OUTPUT_FILE_THRESHOLD:
            if is_multi:
                cmds = [
                    {**c,
                     'stdout': _tail_bytes(c.get('stdout', ''), PER_COMMAND_TAIL_BYTES),
                     'stderr': _tail_bytes(c.get('stderr', ''), PER_COMMAND_TAIL_BYTES)}
                    for c in cmds
                ]
                stdout_content = _assemble(cmds)
                command_display = " | ".join(c.get('command', '') for c in cmds) or command_display
            else:
                stdout_content = _tail_bytes(stdout_content, PER_COMMAND_TAIL_BYTES)

        # File if the ORIGINAL output exceeded FILE_ATTACH_THRESHOLD (7 KB);
        # otherwise inline.
        if stdout_content and original_size > FILE_ATTACH_THRESHOLD:
            temp_file = TMP_DIR / f"output_{uuid.uuid4().hex[:8]}.txt"
            try:
                with open(temp_file, 'w', encoding='utf-8') as f:
                    f.write(stdout_content)
                logger.info("Large output saved to %s (%s bytes)", temp_file, temp_file.stat().st_size)

                selector = provider.selectors.get("file_input", "input[type='file']")
                provider.page.wait_for_selector(selector, state="attached", timeout=10000)
                provider.page.set_input_files(selector, str(temp_file))
                logger.info("Large output file attached to DeepSeek: %s", temp_file.name)

                provider.send_prompt(
                    f"[SYSTEM_COMMAND_OUTPUT]\nCommand: {command_display or 'unknown'}\nThe output is attached as a file.\n[/SYSTEM_COMMAND_OUTPUT]" + attach_note
                    + ("\n\n" + queued_block if queued_block else "")
                )
            except Exception as e:
                logger.error("Failed to upload output file: %s", e)
                truncated = stdout_content[:1000] + "...\n[Output truncated, too large to include]"
                if cmds:
                    wrapped = f"[SYSTEM_COMMAND_OUTPUT]\nCommand: {command_display}\nstdout:\n{truncated}\n[/SYSTEM_COMMAND_OUTPUT]"
                else:
                    wrapped = build_wrapped_command_output(
                        request.command, request.exit_code, truncated, request.stderr or ""
                    )
                provider.send_prompt(wrapped + attach_note
                                     + ("\n\n" + queued_block if queued_block else ""))
            finally:
                try:
                    if temp_file.exists():
                        temp_file.unlink()
                except Exception:
                    pass
        else:
            if cmds:
                wrapped = build_wrapped_commands_output(cmds)
            else:
                wrapped = build_wrapped_command_output(
                    request.command, request.exit_code, stdout_content or "", request.stderr or ""
                )
            provider.send_prompt(wrapped + attach_note
                                 + ("\n\n" + queued_block if queued_block else ""))
        return provider.get_response()

    try:
        ai_response = await loop.run_in_executor(_provider_executor, send_wrapped_and_get)
        thinking, answer, commands = _extract_response(ai_response)

        if request.chat_id:
            add_message(request.chat_id, "assistant", answer, thinking, commands)
            logger.info("Stored feedback response for chat %s", request.chat_id)

        logger.info("AI feedback processed, commands=%d", len(commands))
        return AIFeedbackResponse(
            thinking=thinking,
            answer=answer,
            commands=commands,
        )
    except Exception as e:
        logger.exception("Error during AI feedback processing")
        return JSONResponse(status_code=500, content={"error": str(e)})


@app.post("/api/queue-flush")
async def queue_flush():
    """Fire a turn whose ONLY payload is pending background-job output.

    The UI calls this when it goes idle and a queue* job has finished
    but no message is coming to carry the block. Server-side:
    if nothing is pending, no-op; otherwise drain, send a minimal
    prompt + the block, and return the reply so the UI renders it
    like any other assistant turn. On failure the block is requeued.
    """
    if _queue_runner.pending_count() == 0:
        return {"flushed": False}
    if not provider:
        return JSONResponse(status_code=500, content={"error": "Provider not initialized"})

    block = _queue_runner.drain_injections()
    if not block:
        return {"flushed": False}

    loop = asyncio.get_running_loop()

    def send_and_get():
        provider.send_prompt(
            "A background job you launched has finished. "
            "Its output is below -- react to it as you normally would.\n\n"
            + block
        )
        return provider.get_response()

    try:
        ai_response = await loop.run_in_executor(_provider_executor, send_and_get)
        thinking, answer, commands = _extract_response(ai_response)
        logger.info("Queue flush turn complete, commands=%d", len(commands))
        return {"flushed": True, "thinking": thinking,
                "answer": answer, "commands": commands}
    except Exception as e:
        logger.exception("Queue flush failed; requeueing block")
        _queue_runner.requeue_injections(block)
        return JSONResponse(status_code=500, content={"error": str(e)})


@app.post("/api/open-terminal")
async def open_terminal(request: OpenTerminalRequest):
    command = request.command
    logger.info("Opening native terminal for command: %s", command[:100])

    full_cmd = []
    for arg in TERMINAL_COMMAND_TEMPLATE:
        if isinstance(arg, str):
            full_cmd.append(arg.format(command=command))
        else:
            full_cmd.append(arg)

    try:
        subprocess.Popen(full_cmd, start_new_session=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        logger.info("Terminal launched successfully")
        return JSONResponse(content={"status": "success", "message": "Terminal opened"})
    except FileNotFoundError:
        logger.warning("Primary terminal not found, trying fallbacks...")
        for fallback in FALLBACK_TERMINALS:
            try:
                fallback_cmd = [fallback, "-e", "bash", "-c", f"{command}; exec bash"]
                subprocess.Popen(fallback_cmd, start_new_session=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                logger.info("Fallback terminal %s launched successfully", fallback)
                return JSONResponse(content={"status": "success", "message": f"Terminal opened with {fallback}"})
            except FileNotFoundError:
                continue
        logger.error("No terminal emulator found.")
        return JSONResponse(
            status_code=500,
            content={"error": "No terminal emulator found. Please install konsole, gnome-terminal, or xterm."}
        )
    except Exception as e:
        logger.exception("Failed to launch terminal")
        return JSONResponse(status_code=500, content={"error": f"Failed to launch terminal: {str(e)}"})


# ── Chat history endpoints ──

@app.get("/api/chats")
async def list_chats():
    chats = get_chat_list()
    return JSONResponse(content=chats)


@app.get("/api/current-chat")
async def current_chat():
    """Chat id matching the browser's current URL, for auto-open on load."""
    chat_id = _current_chat_id
    try:
        if provider and getattr(provider, "page", None):
            url = provider.page.url or ""
            frag = url.rsplit("/", 1)[-1].split("?")[0]
            matched = get_chat_by_url(frag) if frag and frag != "about:blank" else None
            if matched:
                chat_id = matched["id"]
    except Exception as e:
        logger.debug("current-chat lookup failed: %s", e)
    return JSONResponse(content={"chat_id": chat_id})


CONTEXT_FILE_PATH = Path("User/FOR_AI.md")


@app.get("/api/context/for-ai")
async def get_for_ai_context():
    """Return FOR_AI.md for the 'Load Context' button.

    The button sends this as the first message of a fresh chat; the
    server already prepends src/prompts/system.txt on new sessions, so
    this reproduces the manual 'paste FOR_AI.md' flow in one click.
    """
    try:
        content = CONTEXT_FILE_PATH.read_text(encoding="utf-8")
    except FileNotFoundError:
        logger.warning("Context file not found at %s", CONTEXT_FILE_PATH)
        return JSONResponse(status_code=404, content={"error": "FOR_AI.md not found"})
    logger.info("Served context file (%d bytes)", len(content))
    return JSONResponse(content={"content": content, "path": str(CONTEXT_FILE_PATH)})


@app.get("/api/restart-report")
async def get_restart_report():
    """Latest restart report written by scripts/restart.sh, if any.

    The frontend polls this after a command whose feedback needed a
    retry (i.e. the server was restarting) and forwards the report to
    the AI, so a self-restart's outcome reaches the AI with no human
    step.
    """
    f = Path(os.environ.get("AUTONECT_STATUS", "/tmp/autonect-restart-status.txt"))
    try:
        if f.exists():
            return JSONResponse(content={"content": f.read_text(encoding="utf-8"),
                                         "mtime": f.stat().st_mtime})
    except Exception as e:
        logger.debug("restart-report read failed: %s", e)
    return JSONResponse(content={"content": None})


@app.post("/api/restart-report/ack")
async def ack_restart_report():
    """Mark the restart report as consumed (clear memory + delete file)."""
    global _pending_restart_report
    _pending_restart_report = None
    f = Path(os.environ.get("AUTONECT_STATUS", "/tmp/autonect-restart-status.txt"))
    try:
        f.unlink()
    except Exception:
        pass
    return JSONResponse(content={"ok": True})


@app.get("/api/chats/{chat_id}")
async def get_chat_history(chat_id: str):
    chat = get_chat(chat_id)
    if not chat:
        return JSONResponse(status_code=404, content={"error": "Chat not found"})
    return JSONResponse(content=chat)


@app.put("/api/chats/{chat_id}")
async def update_chat_metadata(chat_id: str, request: Request):
    data = await request.json()
    name = data.get("name")
    pinned = data.get("pinned")
    update_chat(chat_id, name, pinned)
    return JSONResponse(content={"status": "ok"})


@app.put("/api/chats/{chat_id}/name")
async def update_chat_name_endpoint(chat_id: str, request: Request):
    data = await request.json()
    name = data.get("name")
    if not name:
        return JSONResponse(status_code=400, content={"error": "Name is required"})
    update_chat_name(chat_id, name)
    return JSONResponse(content={"status": "ok"})


@app.delete("/api/chats/{chat_id}")
async def delete_chat_endpoint(chat_id: str):
    delete_chat(chat_id)
    return JSONResponse(content={"status": "ok"})


# ── Browser navigation ──

@app.post("/api/browser/navigate")
async def navigate_browser(request: NavigateRequest):
    if not provider or not provider.page:
        logger.error("Provider or page not available")
        return JSONResponse(status_code=500, content={"error": "Browser not available"})

    url = request.url
    logger.info("Navigating browser to: %s", url)

    def _navigate():
        try:
            provider.page.goto(url, timeout=30000)
            provider.page.wait_for_load_state("networkidle")
            logger.info("Navigation successful")
        except Exception as e:
            logger.exception("Navigation failed: %s", e)
            raise

    loop = asyncio.get_running_loop()
    try:
        await loop.run_in_executor(_provider_executor, _navigate)
        await loop.run_in_executor(_provider_executor, _save_last_url)
        return JSONResponse(content={"status": "success", "url": url})
    except Exception as e:
        logger.exception("Navigation error")
        return JSONResponse(status_code=500, content={"error": f"Navigation failed: {str(e)}"})

@app.get("/api/selectors")
async def get_selectors():
    """Expose the current DeepSeek selector map to the frontend.

    The title-extraction logic in script.js uses a hardcoded fallback chain.
    This endpoint lets the frontend pull the authoritative chain from the
    provider config, so UI changes only require editing the JSON file.
    """
    if not provider:
        return JSONResponse(status_code=500, content={"error": "Provider not initialized"})
    return JSONResponse(content=provider.selectors)

@app.post("/api/browser/evaluate")
async def evaluate_browser(request: Request):
    if not provider or not provider.page:
        logger.error("Provider or page not available")
        return JSONResponse(status_code=500, content={"error": "Browser not available"})

    data = await request.json()
    script = data.get("script")
    if not script:
        return JSONResponse(status_code=400, content={"error": "Script is required"})

    logger.debug("Evaluating script in browser")

    def _evaluate():
        try:
            result = provider.page.evaluate(script)
            return result
        except Exception as e:
            logger.exception("Script evaluation failed: %s", e)
            raise

    loop = asyncio.get_running_loop()
    try:
        result = await loop.run_in_executor(_provider_executor, _evaluate)
        return JSONResponse(content={"result": result})
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})


# ── Supported extensions (single source of truth) ──

@app.get("/api/supported-extensions")
async def supported_extensions():
    return JSONResponse(content={"extensions": sorted(SUPPORTED_EXTENSIONS)})


# ── File upload ──

@app.post("/api/upload")
async def upload_file(file: UploadFile = File(...)):
    if not provider or not provider.page:
        logger.error("Provider or page not available")
        return JSONResponse(status_code=500, content={"error": "Browser not available"})

    content = await file.read()
    file_name = file.filename
    mime_type = file.content_type or "application/octet-stream"

    ext = Path(file_name).suffix.lower().lstrip(".")
    if SUPPORTED_EXTENSIONS and ext not in SUPPORTED_EXTENSIONS:
        logger.warning("Rejected upload (unsupported extension): %s", file_name)
        return JSONResponse(
            status_code=400,
            content={"error": f"Unsupported file extension: .{ext or '(none)'}"},
        )

    selector = provider.selectors.get("file_input", "input[type='file']")

    loop = asyncio.get_running_loop()

    def _set_files():
        provider.page.wait_for_selector(selector, state="attached", timeout=10000)
        provider.page.set_input_files(selector, {
            "name": file_name,
            "mimeType": mime_type,
            "buffer": content
        })

    try:
        await loop.run_in_executor(_provider_executor, _set_files)
        logger.info("File uploaded to DeepSeek: %s (%s bytes)", file_name, len(content))
        return JSONResponse(content={"status": "success", "filename": file_name})
    except Exception as e:
        logger.exception("Failed to upload file")
        return JSONResponse(status_code=500, content={"error": str(e)})


# =============================================================================
# WebSocket Endpoint
# =============================================================================

@app.websocket("/ws/execute")
async def websocket_execute(websocket: WebSocket):
    # ── Accept the connection ──
    await websocket.accept()
    logger.info("WebSocket connection accepted")

    try:
        init_msg = await websocket.receive_text()
        logger.debug("WebSocket init message received: %s", init_msg[:200])
    except Exception as e:
        logger.error("Failed to receive init message: %s", e)
        await websocket.close(code=4000, reason="Init message missing")
        return

    try:
        cmd_data = json.loads(init_msg)
        command = cmd_data.get("command", "")
        session_id = cmd_data.get("session_id", "default")
    except json.JSONDecodeError as e:
        logger.error("Invalid JSON in init message: %s", e)
        await websocket.close(code=4000, reason="Invalid JSON")
        return

    if not command:
        logger.warning("WebSocket connection closed: no command provided")
        await websocket.close(code=4000, reason="No command provided")
        return

    logger.info("WebSocket command evaluation: session=%s, command=%s", session_id, command[:100])

    # ── Security evaluation ──
    decision, info = guard.evaluate(command, session_id)
    if decision in ("ask", "deny"):
        severity = "unsafe" if decision == "deny" else "unsure"
        logger.info("Command requires user approval: %s (severity=%s)", command[:50], severity)
        try:
            await websocket.send_text(json.dumps({
                "type": "ask",
                "command": command,
                "reason": info.get("reason", ""),
                "path": info.get("path", ""),
                "session_id": session_id,
                "severity": severity
            }))
        except (WebSocketDisconnect, RuntimeError):
            logger.warning("Client disconnected before approval could be sent")
            return

        try:
            approval = await websocket.receive_text()
            data = json.loads(approval)
            action = data.get("action")
            path = data.get("path", "")
            if action in ("allow_once", "allow_session"):
                guard.approve_once(command, path)
                if action == "allow_session":
                    guard.approve_session(command, path)
                logger.info("Command approved by user: action=%s", action)
            else:
                logger.warning("Command denied by user")
                try:
                    await websocket.send_text(json.dumps({"type": "denied", "reason": "User denied"}))
                except (WebSocketDisconnect, RuntimeError):
                    pass
                await websocket.close(code=4000, reason="Denied by user")
                return
        except Exception as e:
            logger.error("Approval error: %s", e)
            try:
                await websocket.send_text(json.dumps({"type": "denied", "reason": "Approval error"}))
            except (WebSocketDisconnect, RuntimeError):
                pass
            await websocket.close(code=4000, reason="Approval error")
            return

    # ── Fork PTY ──
    # Launch a plain interactive shell (argv does NOT contain the user command),
    # then feed the command via the PTY master. This prevents tools like
    # `pkill -f` from matching and SIGTERM-ing the shell's own command line.
    logger.info("Forking PTY for command: %s", command[:100])
    pid, master_fd = pty.fork()
    if pid == 0:
        # pty.fork() already called setsid() in the child.
        # Suppress interactive pagers. Tools like less, man, git log, and
        # systemctl read from the PTY's stdin while running; if a pager
        # consumes the exit that we write to the master, the shell never
        # sees it and the session hangs until the user types exit.
        os.environ["PAGER"] = "cat"
        os.environ["GIT_PAGER"] = "cat"
        os.environ["MANPAGER"] = "cat"
        os.environ["SYSTEMD_PAGER"] = "cat"
        os.environ["LESS"] = "-FRX"
        os.execvp("/bin/sh", ["/bin/sh"])
        os._exit(1)

    logger.debug("Forked child PID: %d", pid)

    # Make PTY non-blocking
    flags = fcntl.fcntl(master_fd, fcntl.F_GETFL)
    fcntl.fcntl(master_fd, fcntl.F_SETFL, flags | os.O_NONBLOCK)

    # Send the command to the shell via the PTY master.
    try:
        os.write(master_fd, (command + "\nexit\n").encode())
    except OSError as e:
        logger.error("Failed to write command to PTY: %s", e)

    loop = asyncio.get_running_loop()
    output_chunks = []
    exit_status = None
    signal_info = None

    reader_queue = asyncio.Queue()

    def pty_reader_callback():
        try:
            data = os.read(master_fd, 4096)
            if data:
                reader_queue.put_nowait(data)
            else:
                reader_queue.put_nowait(None)
        except (OSError, BlockingIOError):
            pass

    loop.add_reader(master_fd, pty_reader_callback)

    async def wait_for_exit(pid):
        nonlocal exit_status, signal_info
        pid_status = await loop.run_in_executor(None, os.waitpid, pid, 0)
        _, status = pid_status
        if os.WIFSIGNALED(status):
            signum = os.WTERMSIG(status)
            exit_status = -signum
            try:
                sig_name = signal.Signals(signum).name
            except (ValueError, AttributeError):
                sig_name = f"signal {signum}"
            signal_info = {
                "signum": signum,
                "name": sig_name
            }
            logger.info("Process %d terminated by signal %d (%s)", pid, signum, sig_name)
        else:
            exit_status = os.WEXITSTATUS(status)
            logger.info("Process %d exited with status %d", pid, exit_status)
        return exit_status

    async def read_pty():
        while True:
            try:
                data = await reader_queue.get()
            except asyncio.CancelledError:
                break
            if data is None:
                logger.debug("Reader received EOF")
                break
            output_chunks.append(data)
            try:
                await websocket.send_bytes(data)
            except (WebSocketDisconnect, RuntimeError):
                logger.warning("WebSocket closed during send_bytes, stopping read")
                break

    async def write_ws_to_pty():
        try:
            while True:
                try:
                    msg = await websocket.receive()
                except WebSocketDisconnect:
                    logger.info("WebSocket disconnected during receive")
                    break
                if "text" in msg:
                    try:
                        obj = json.loads(msg["text"])
                    except json.JSONDecodeError:
                        try:
                            os.write(master_fd, msg["text"].encode())
                        except OSError:
                            break
                        continue

                    if obj.get("type") == "resize":
                        cols = obj.get("cols", 80)
                        rows = obj.get("rows", 24)
                        try:
                            winsize = struct.pack("HHHH", rows, cols, 0, 0)
                            fcntl.ioctl(master_fd, termios.TIOCSWINSZ, winsize)
                        except OSError as e:
                            logger.error("Resize error: %s", e)
                    elif obj.get("type") == "signal":
                        sig = getattr(signal, obj.get("signal", ""), None)
                        if sig and pid > 0:
                            try:
                                os.killpg(pid, sig)
                            except OSError as e:
                                logger.error("Signal error: %s", e)
                    elif obj.get("type") == "stdin":
                        try:
                            os.write(master_fd, obj["data"].encode())
                        except OSError:
                            break
                elif "bytes" in msg:
                    try:
                        os.write(master_fd, msg["bytes"])
                    except OSError:
                        break
        except WebSocketDisconnect:
            logger.info("WebSocket disconnected during write")
        except Exception as e:
            logger.exception("Unexpected error in write_ws_to_pty: %s", e)
        finally:
            reader_task.cancel()

    reader_task = asyncio.create_task(read_pty())
    writer_task = asyncio.create_task(write_ws_to_pty())
    exit_task = asyncio.create_task(wait_for_exit(pid))

    # Wait for either the process to exit or the writer to stop (client disconnect).
    done, pending = await asyncio.wait(
        [exit_task, writer_task],
        return_when=asyncio.FIRST_COMPLETED
    )

    # ── Ensure the child is reaped so exit_status gets a real value ──
    # If the writer stopped first (client disconnected) but the process is
    # still running, do NOT cancel exit_task — that would leave exit_status
    # as None and cause "-1" to be reported for a successful command.
    # Instead, give the process a grace period, then escalate SIGTERM → SIGKILL.
    if exit_task in pending:
        logger.info("Writer stopped before process exit; waiting for PID %d to finish", pid)
        try:
            await asyncio.wait_for(asyncio.shield(exit_task), timeout=2.0)
        except asyncio.TimeoutError:
            logger.info("PID %d still alive, sending SIGTERM to process group", pid)
            try:
                os.killpg(pid, signal.SIGTERM)
            except OSError as e:
                logger.debug("killpg(SIGTERM) failed: %s", e)
            try:
                await asyncio.wait_for(asyncio.shield(exit_task), timeout=2.0)
            except asyncio.TimeoutError:
                logger.warning("PID %d ignored SIGTERM, sending SIGKILL", pid)
                try:
                    os.killpg(pid, signal.SIGKILL)
                except OSError as e:
                    logger.debug("killpg(SIGKILL) failed: %s", e)
                try:
                    await asyncio.wait_for(asyncio.shield(exit_task), timeout=2.0)
                except asyncio.TimeoutError:
                    logger.error("PID %d did not exit after SIGKILL", pid)

    # Cancel whatever is still pending (e.g. writer_task if the process exited first).
    for task in pending:
        if not task.done():
            task.cancel()
            try:
                await task
            except (asyncio.CancelledError, Exception):
                pass

    # ── Flush any remaining data from PTY ──
    # After the process exits, there may still be buffered output in the PTY.
    # Read until no more data is available (up to 5 attempts with 50ms delay).
    flush_attempts = 5
    for _ in range(flush_attempts):
        try:
            data = os.read(master_fd, 4096)
            if data:
                output_chunks.append(data)
                try:
                    await websocket.send_bytes(data)
                except (WebSocketDisconnect, RuntimeError):
                    logger.warning("WebSocket closed during final flush")
                    break
            else:
                break
        except BlockingIOError:
            await asyncio.sleep(0.05)
        except OSError:
            break

    loop.remove_reader(master_fd)
    reader_queue.put_nowait(None)

    try:
        await asyncio.wait_for(reader_task, timeout=1)
    except (asyncio.CancelledError, asyncio.TimeoutError):
        pass

    final_output = b"".join(output_chunks).decode(errors="replace")

    output_id = uuid.uuid4().hex
    _output_cache[output_id] = final_output
    logger.info("Cached stdout with output_id %s (length: %s)", output_id, len(final_output))

    exit_msg = {
        "type": "exit",
        "code": exit_status if exit_status is not None else -1,
        "output": final_output,
        "output_id": output_id
    }
    if signal_info:
        exit_msg["signal"] = signal_info["signum"]
        exit_msg["signal_name"] = signal_info["name"]
        exit_msg["message"] = f"Process terminated by signal {signal_info['signum']} ({signal_info['name']})"
    else:
        exit_msg["message"] = f"Process exited with code {exit_status}" if exit_status is not None else "Unknown exit"

    # ── Convey exit status via the WebSocket close frame ──
    # Text messages sent right before a close frame are unreliable across
    # ASGI transports and browsers. The close frame itself is guaranteed to
    # be delivered, so we encode the exit status in its code and reason.
    #
    # Close-code mapping (custom application range is 4000-4999):
    #   1000        → normal / exit 0
    #   4000 + N    → process exited with code N (N >= 1)
    #   4100 + N    → process killed by signal N
    #   4000        → unknown
    if exit_status is None:
        ws_code = 4000
        ws_reason = "exit:unknown"
    elif exit_status == 0:
        ws_code = 1000
        ws_reason = "exit:0"
    elif exit_status > 0:
        ws_code = 4000 + (exit_status % 1000)
        ws_reason = f"exit:{exit_status}"
    else:  # negative → killed by signal
        signum = -exit_status
        ws_code = 4100 + (signum % 100)
        ws_reason = f"signal:{signum}"

    logger.info("Sending exit message: %s (close code=%d)", exit_msg["message"], ws_code)

    # Best-effort text frame first, for clients that want the full payload.
    try:
        await websocket.send_text(json.dumps(exit_msg))
    except (WebSocketDisconnect, RuntimeError) as e:
        logger.warning("Could not send exit message: %s", e)

    try:
        await websocket.close(code=ws_code, reason=ws_reason)
    except (WebSocketDisconnect, RuntimeError):
        logger.debug("WebSocket already closed, skipping close call")

    try:
        os.close(master_fd)
    except OSError as e:
        logger.error("Error closing master fd: %s", e)


# =============================================================================
# STT proxy — expose the local STT service on AutoNect's own origin
# =============================================================================
# The STT service binds 127.0.0.1:6012, so a phone hitting AutoNect over
# LAN cannot reach it, and a plain-HTTP page cannot open a mic at all
# (secure-context rule).  Proxying /ws/stt through AutoNect means the
# browser talks to the SAME origin it loaded from -- works over HTTPS,
# no extra port, no UFW rule, no mixed content.
STT_UPSTREAM = os.environ.get("AUTONECT_STT_UPSTREAM", "ws://127.0.0.1:6012/ws/stt")


# =============================================================================
# Event bus — server pushes events to the UI (no polling)
# =============================================================================
# The UI holds a persistent /ws/events socket. The server pushes events
# (e.g. a restart report) the moment they happen, so the frontend never
# polls. A small pending buffer covers the window where the UI is
# reconnecting right after a restart.
_event_subscribers: set = set()
_pending_restart_report: Optional[str] = None

# The running event loop, captured in lifespan. The queue_runner
# completion callback fires from a plain thread and needs this to
# schedule an async broadcast.
_event_loop: Optional[asyncio.AbstractEventLoop] = None


def _on_queue_job_done(job: dict) -> None:
    """queue_runner completion callback (runs on the watcher thread).

    Push a queue-job-done event so the UI can decide, on its own, that
    it is idle and fire a turn to flush the block. The UI owns the
    idle predicate -- the PTY command state lives in the browser.
    """
    loop = _event_loop
    subs = len(_event_subscribers)
    logger.info("queue-job-done callback: job=%s subs=%d loop=%s",
                job.get("job_id"), subs, "set" if loop else "None")
    if loop is None:
        return
    payload = {
        "type": "queue-job-done",
        "job_id": job.get("job_id"),
        "exit_code": job.get("exit_code"),
        "runtime_s": job.get("runtime_s"),
    }
    try:
        asyncio.run_coroutine_threadsafe(_broadcast_event(payload), loop)
    except Exception as e:
        logger.warning("queue-job-done broadcast failed: %s", e)


async def _broadcast_event(payload: dict):
    dead = []
    for ws in list(_event_subscribers):
        try:
            await ws.send_text(json.dumps(payload))
        except Exception:
            dead.append(ws)
    for ws in dead:
        _event_subscribers.discard(ws)


def _load_pending_restart_report():
    """On boot, hold any restart report the script already wrote."""
    global _pending_restart_report
    try:
        f = Path(os.environ.get("AUTONECT_STATUS", "/tmp/autonect-restart-status.txt"))
        if f.exists():
            _pending_restart_report = f.read_text(encoding="utf-8")
            logger.info("Loaded pending restart report (%d bytes)", len(_pending_restart_report))
    except Exception as e:
        logger.debug("pending restart report load failed: %s", e)


@app.websocket("/ws/events")
async def websocket_events(websocket: WebSocket):
    """Persistent event channel. The server pushes; the client listens."""
    await websocket.accept()
    _event_subscribers.add(websocket)
    logger.info("Event subscriber connected (%d total)", len(_event_subscribers))
    try:
        # Deliver anything already waiting (e.g. a report written while
        # the UI was reconnecting).
        if _pending_restart_report:
            await websocket.send_text(json.dumps(
                {"type": "restart-report", "content": _pending_restart_report}))
        while True:
            await websocket.receive_text()   # keep-alive / disconnect detect
    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.debug("event socket closed: %s", e)
    finally:
        _event_subscribers.discard(websocket)
        logger.info("Event subscriber disconnected (%d left)", len(_event_subscribers))


@app.post("/api/restart-report/publish")
async def publish_restart_report(request: Request):
    """Called by scripts/restart.sh once the report is written.

    Stores it and PUSHES it to every connected UI, so delivery is an
    event, not a poll.
    """
    global _pending_restart_report
    try:
        data = await request.json()
    except Exception:
        data = {}
    content = data.get("content")
    if not content:
        try:
            f = Path(os.environ.get("AUTONECT_STATUS", "/tmp/autonect-restart-status.txt"))
            content = f.read_text(encoding="utf-8") if f.exists() else None
        except Exception:
            content = None
    if not content:
        return JSONResponse(status_code=400, content={"error": "no report content"})
    _pending_restart_report = content
    await _broadcast_event({"type": "restart-report", "content": content})
    logger.info("Published restart report to %d subscriber(s)", len(_event_subscribers))
    return JSONResponse(content={"ok": True, "subscribers": len(_event_subscribers)})


def _start_stt_process(force: bool = False) -> bool:
    """Spawn the STT service. With force=True, spawn regardless of the
    port state (uvicorn exits harmlessly if the port is taken), so a
    lingering socket from a dying instance cannot make us skip a start.
    Returns True if a process was spawned.
    """
    port = int(os.environ.get("AUTONECT_STT_PORT", "6012"))
    if not force and _stt_port_listening(port):
        logger.info("STT service already listening on :%d", port)
        return False
    project_root = BASE_DIR.parent.parent
    stt_dir = project_root / "stt-service"
    py = stt_dir / ".venv" / "bin" / "python"
    if not py.exists():
        logger.warning("STT service not found at %s", stt_dir)
        return False
    try:
        subprocess.Popen(
            [str(py), "-m", "uvicorn", "server:app",
             "--host", "127.0.0.1", "--port", str(port)],
            cwd=str(stt_dir),
            stdout=open("/tmp/stt-6012.log", "a"),
            stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,
            start_new_session=True,
        )
        logger.info("Started STT service on :%d (force=%s)", port, force)
        return True
    except Exception:
        logger.exception("Failed to start STT service")
        return False


async def _connect_stt(upstream_url):
    """Connect to the STT upstream, starting the service if it is down.

    The service is also brought up at boot, but it can die mid-session
    (crash, OOM, manual kill). Reviving it here makes the mic self-heal:
    the browser opens /ws/stt, and if the service is not listening we
    start it and retry. Returns the open connection or raises.
    """
    import websockets
    for attempt in range(1, 4):
        try:
            return await websockets.connect(upstream_url, max_size=None)
        except Exception as e:
            logger.info("STT upstream not ready (attempt %d): %s", attempt, e)
            if attempt < 3:
                # force-start: a lingering socket must not make us skip
                try:
                    _start_stt_process(force=True)
                except Exception:
                    logger.exception("STT revive failed")
                await asyncio.sleep(2.0 * attempt)
    # last try, let the error propagate
    return await websockets.connect(upstream_url, max_size=None)


@app.websocket("/ws/stt")
async def websocket_stt_proxy(client_ws: WebSocket):
    import websockets
    await client_ws.accept()
    query = client_ws.url.query
    upstream_url = STT_UPSTREAM + (("?" + query) if query else "")
    try:
        async with await _connect_stt(upstream_url) as up:
            async def client_to_up():
                try:
                    while True:
                        msg = await client_ws.receive()
                        if msg.get("type") == "websocket.disconnect":
                            break
                        if msg.get("bytes") is not None:
                            await up.send(msg["bytes"])
                        elif msg.get("text") is not None:
                            await up.send(msg["text"])
                except (WebSocketDisconnect, RuntimeError):
                    pass
                finally:
                    try:
                        await up.close()
                    except Exception:
                        pass

            async def up_to_client():
                try:
                    async for message in up:
                        if isinstance(message, (bytes, bytearray)):
                            await client_ws.send_bytes(bytes(message))
                        else:
                            await client_ws.send_text(message)
                except Exception:
                    pass

            await asyncio.gather(client_to_up(), up_to_client())
    except Exception as e:
        logger.warning("STT proxy failed: %s", e)
    finally:
        try:
            await client_ws.close()
        except Exception:
            pass
