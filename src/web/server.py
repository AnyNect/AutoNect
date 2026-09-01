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

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from starlette.middleware.base import BaseHTTPMiddleware

from src.ai.providers.deepseek import DeepSeekProvider
from src.parser.commands import extract_commands
from src.security import CommandGuard

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
            "maxBytes": 10_485_760,  # 10 MB
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

# Ensure logs directory exists
Path("logs").mkdir(exist_ok=True)

dictConfig(LOG_CONFIG)
logger = logging.getLogger(__name__)

# =============================================================================
# Application Setup
# =============================================================================

# ── Single‑thread executor for Playwright ──
_provider_executor = ThreadPoolExecutor(max_workers=1)

provider: DeepSeekProvider | None = None
guard = CommandGuard()

BASE_DIR = Path(__file__).parent
TEMPLATES_DIR = BASE_DIR / "templates"
STATIC_DIR = BASE_DIR / "static"
INDEX_HTML = (TEMPLATES_DIR / "index.html").read_text(encoding="utf-8")

SYSTEM_PROMPT_PATH = Path("src/prompts/system.txt")
try:
    SYSTEM_PROMPT = SYSTEM_PROMPT_PATH.read_text(encoding="utf-8").strip()
    logger.info("System prompt loaded successfully")
except FileNotFoundError:
    SYSTEM_PROMPT = ""
    logger.warning("System prompt file not found at %s", SYSTEM_PROMPT_PATH)

# Session tracking
session_data = {}

# Maximum output bytes for WebSocket (150 KB)
MAX_WEBSOCKET_OUTPUT_BYTES = 150_000

# =============================================================================
# Lifespan & Middleware
# =============================================================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    global provider
    logger.info("Starting application lifespan")
    loop = asyncio.get_running_loop()
    provider = DeepSeekProvider()
    try:
        await loop.run_in_executor(_provider_executor, provider.connect)
        logger.info("DeepSeek provider connected")
    except Exception as e:
        logger.exception("Failed to connect DeepSeek provider")
        raise
    yield
    logger.info("Shutting down application lifespan")
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


class AIFeedbackRequest(BaseModel):
    commands: list[dict] = []
    command: str | None = None
    stdout: str | None = None
    stderr: str | None = None
    exit_code: int | None = None


class AIFeedbackResponse(BaseModel):
    thinking: str
    answer: str
    commands: list[dict] = []


# =============================================================================
# Helper Functions
# =============================================================================

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
    return thinking, answer, commands


def clean_deepseek_markdown(text: str) -> str:
    """Clean common markdown artifacts from DeepSeek responses."""
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
    return HTMLResponse(content=INDEX_HTML)


@app.post("/api/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    logger.info("Chat request received, session_id=%s", request.session_id)
    if not provider:
        logger.error("Provider not initialized")
        return JSONResponse(status_code=500, content={"error": "Provider not initialized"})

    loop = asyncio.get_running_loop()

    if request.session_id is None or request.session_id not in session_data:
        if request.session_id is None:
            request.session_id = str(uuid.uuid4())
            logger.info("New session created: %s", request.session_id)
        full_prompt = f"{SYSTEM_PROMPT}\n\n{request.prompt}" if SYSTEM_PROMPT else request.prompt
        session_data[request.session_id] = True
    else:
        full_prompt = request.prompt
        logger.debug("Existing session: %s", request.session_id)

    def send_and_get():
        provider.send_prompt(full_prompt)
        return provider.get_response()

    try:
        response = await loop.run_in_executor(_provider_executor, send_and_get)
        thinking, answer, commands = _extract_response(response, request.session_id)
        logger.info("Chat completed for session %s, commands=%d", request.session_id, len(commands))
        return ChatResponse(thinking=thinking, answer=answer, commands=commands)
    except Exception as e:
        logger.exception("Error during chat processing for session %s", request.session_id)
        return JSONResponse(status_code=500, content={"error": str(e)})


@app.post("/api/ai-feedback", response_model=AIFeedbackResponse)
async def ai_feedback(request: AIFeedbackRequest):
    logger.info("AI feedback request received")
    if not provider:
        logger.error("Provider not initialized")
        return JSONResponse(status_code=500, content={"error": "Provider not initialized"})

    loop = asyncio.get_running_loop()

    def send_wrapped_and_get():
        if request.commands:
            wrapped = build_wrapped_commands_output(request.commands)
        else:
            wrapped = build_wrapped_command_output(
                request.command, request.exit_code, request.stdout, request.stderr
            )
        provider.send_prompt(wrapped)
        return provider.get_response()

    try:
        ai_response = await loop.run_in_executor(_provider_executor, send_wrapped_and_get)
        thinking, answer, commands = _extract_response(ai_response)
        logger.info("AI feedback processed, commands=%d", len(commands))
        return AIFeedbackResponse(
            thinking=thinking,
            answer=answer,
            commands=commands,
        )
    except Exception as e:
        logger.exception("Error during AI feedback processing")
        return JSONResponse(status_code=500, content={"error": str(e)})


# =============================================================================
# WebSocket Endpoint
# =============================================================================

@app.websocket("/ws/execute")
async def websocket_execute(websocket: WebSocket):
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

    # Security evaluation
    decision, info = guard.evaluate(command, session_id)
    if decision in ("ask", "deny"):
        severity = "unsafe" if decision == "deny" else "unsure"
        logger.info("Command requires user approval: %s (severity=%s)", command[:50], severity)
        await websocket.send_text(json.dumps({
            "type": "ask",
            "command": command,
            "reason": info.get("reason", ""),
            "path": info.get("path", ""),
            "session_id": session_id,
            "severity": severity
        }))
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
                await websocket.send_text(json.dumps({"type": "denied", "reason": "User denied"}))
                await websocket.close(code=4000, reason="Denied by user")
                return
        except Exception as e:
            logger.error("Approval error: %s", e)
            await websocket.send_text(json.dumps({"type": "denied", "reason": "Approval error"}))
            await websocket.close(code=4000, reason="Approval error")
            return

    # Execute command in pseudo-terminal
    logger.info("Forking PTY for command: %s", command[:100])
    pid, master_fd = pty.fork()
    if pid == 0:
        try:
            os.setsid()
        except OSError:
            pass
        os.execvp("/bin/sh", ["/bin/sh", "-c", command])
        os._exit(1)

    logger.debug("Forked child PID: %d", pid)

    flags = fcntl.fcntl(master_fd, fcntl.F_GETFL)
    fcntl.fcntl(master_fd, fcntl.F_SETFL, flags | os.O_NONBLOCK)

    loop = asyncio.get_running_loop()
    output_chunks = []
    exit_status = None

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

    async def wait_for_exit():
        nonlocal exit_status
        _, status = await loop.run_in_executor(None, os.waitpid, pid, 0)
        exit_status = os.waitstatus_to_exitcode(status)
        logger.info("Process %d exited with status %d", pid, exit_status)
        return exit_status

    async def read_pty():
        total_bytes = 0
        while True:
            data = await reader_queue.get()
            if data is None:
                logger.debug("Reader received EOF")
                break
            chunk_size = len(data)
            if total_bytes + chunk_size > MAX_WEBSOCKET_OUTPUT_BYTES:
                allowed = MAX_WEBSOCKET_OUTPUT_BYTES - total_bytes
                if allowed > 0:
                    truncated = data[:allowed]
                    output_chunks.append(truncated)
                    await websocket.send_bytes(truncated)
                    total_bytes += allowed
                warning = b"\n[OUTPUT TRUNCATED: Exceeded 150 KB limit]\n"
                output_chunks.append(warning)
                await websocket.send_bytes(warning)
                logger.warning("Output truncated for command %s", command[:50])
                break
            else:
                output_chunks.append(data)
                await websocket.send_bytes(data)
                total_bytes += chunk_size

    async def write_ws_to_pty():
        try:
            while True:
                msg = await websocket.receive()
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
            logger.info("Client disconnected during write")

    reader_task = asyncio.create_task(read_pty())
    writer_task = asyncio.create_task(write_ws_to_pty())
    exit_task = asyncio.create_task(wait_for_exit())

    await exit_task

    loop.remove_reader(master_fd)
    await reader_queue.put(None)

    try:
        await asyncio.wait_for(reader_task, timeout=1)
    except (asyncio.CancelledError, asyncio.TimeoutError):
        pass

    writer_task.cancel()

    final_output = b"".join(output_chunks).decode(errors="replace")
    logger.info("Sending exit message with code %d", exit_status if exit_status is not None else -1)
    await websocket.send_text(json.dumps({
        "type": "exit",
        "code": exit_status if exit_status is not None else -1,
        "output": final_output
    }))

    await websocket.close()

    try:
        os.close(master_fd)
    except OSError as e:
        logger.error("Error closing master fd: %s", e)