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

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request, File, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from starlette.middleware.base import BaseHTTPMiddleware

from src.ai.providers.deepseek import DeepSeekProvider
from src.parser.commands import extract_commands
from src.security import CommandGuard
from src.core.config import config
from src.database import upsert_chat, add_message, get_chat_list, get_chat, update_chat, delete_chat, update_chat_name

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

MAX_WEBSOCKET_OUTPUT_BYTES = config.get("websocket", "max_output_bytes", default=150_000)
TERMINAL_COMMAND_TEMPLATE = config.get("terminal", "command", default=["konsole", "-e", "bash", "-c", "{command}; exec bash"])
FALLBACK_TERMINALS = config.get("terminal", "fallback_terminals", default=["gnome-terminal", "xterm"])
OUTPUT_FILE_THRESHOLD = 10 * 1024  # 10 KB

# ── Output cache ──
_output_cache = {}  # key: output_id, value: stdout string

# ── Temporary directory for large outputs ──
TMP_DIR = Path("data/tmp")
TMP_DIR.mkdir(parents=True, exist_ok=True)

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

        deepseek_url = provider.page.url if provider.page else None
        chat_name = request.prompt[:50] if request.session_id not in session_data else None
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
    if not stdout and request.output_id:
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
        stdout_content = stdout
        command_display = request.command or ""

        if request.commands and not stdout_content:
            combined_output = ""
            combined_command = ""
            for cmd in request.commands:
                combined_output += f"Command: {cmd.get('command', '')}\n"
                combined_output += f"Exit code: {cmd.get('exit_code', -1)}\n"
                combined_output += f"stdout:\n{cmd.get('stdout', '')}\n"
                combined_output += f"stderr:\n{cmd.get('stderr', '')}\n\n"
                if not combined_command:
                    combined_command = cmd.get('command', '')
                else:
                    combined_command += " | " + cmd.get('command', '')
            if len(combined_output) > OUTPUT_FILE_THRESHOLD:
                stdout_content = combined_output
                command_display = combined_command or "multiple commands"
            else:
                wrapped = build_wrapped_commands_output(request.commands)
                provider.send_prompt(wrapped)
                return provider.get_response()

        if stdout_content and len(stdout_content) > OUTPUT_FILE_THRESHOLD:
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
                    f"[SYSTEM_COMMAND_OUTPUT]\nCommand: {command_display or 'unknown'}\nThe output is attached as a file.\n[/SYSTEM_COMMAND_OUTPUT]"
                )
            except Exception as e:
                logger.error("Failed to upload output file: %s", e)
                truncated = stdout_content[:1000] + "...\n[Output truncated, too large to include]"
                if request.commands:
                    wrapped = f"[SYSTEM_COMMAND_OUTPUT]\nCommand: {command_display}\nstdout:\n{truncated}\n[/SYSTEM_COMMAND_OUTPUT]"
                else:
                    wrapped = build_wrapped_command_output(
                        request.command, request.exit_code, truncated, request.stderr or ""
                    )
                provider.send_prompt(wrapped)
            finally:
                try:
                    if temp_file.exists():
                        temp_file.unlink()
                except Exception:
                    pass
        else:
            if request.commands:
                wrapped = build_wrapped_commands_output(request.commands)
            else:
                wrapped = build_wrapped_command_output(
                    request.command, request.exit_code, stdout_content or "", request.stderr or ""
                )
            provider.send_prompt(wrapped)
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


# ── File upload ──

@app.post("/api/upload")
async def upload_file(file: UploadFile = File(...)):
    if not provider or not provider.page:
        logger.error("Provider or page not available")
        return JSONResponse(status_code=500, content={"error": "Browser not available"})

    content = await file.read()
    file_name = file.filename
    mime_type = file.content_type or "application/octet-stream"
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
