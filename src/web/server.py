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
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from src.ai.providers.deepseek import DeepSeekProvider
from src.parser.commands import extract_commands

provider: DeepSeekProvider | None = None

BASE_DIR = Path(__file__).parent
TEMPLATES_DIR = BASE_DIR / "templates"
STATIC_DIR = BASE_DIR / "static"
INDEX_HTML = (TEMPLATES_DIR / "index.html").read_text(encoding="utf-8")

SYSTEM_PROMPT_PATH = Path("src/prompts/system.txt")
try:
    SYSTEM_PROMPT = SYSTEM_PROMPT_PATH.read_text(encoding="utf-8").strip()
except FileNotFoundError:
    SYSTEM_PROMPT = ""

# Session tracking
session_data = {}


@asynccontextmanager
async def lifespan(app: FastAPI):
    global provider
    loop = asyncio.get_running_loop()
    provider = DeepSeekProvider()
    await loop.run_in_executor(None, provider.connect)
    yield
    if provider:
        await loop.run_in_executor(None, provider.close)


app = FastAPI(title="AutoNect Chat", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


class ChatRequest(BaseModel):
    prompt: str
    session_id: Optional[str] = None


class ChatResponse(BaseModel):
    thinking: str
    answer: str
    commands: list[dict] = []


class AIFeedbackRequest(BaseModel):
    command: str
    stdout: str
    stderr: str
    exit_code: int


class AIFeedbackResponse(BaseModel):
    thinking: str
    answer: str
    commands: list[dict] = []


def build_wrapped_command_output(command: str, exit_code: int, stdout: str, stderr: str) -> str:
    return (
        f"[SYSTEM_COMMAND_OUTPUT]\n"
        f"Command: {command}\n"
        f"Exit code: {exit_code}\n"
        f"stdout:\n{stdout}\n"
        f"stderr:\n{stderr}\n"
        f"[/SYSTEM_COMMAND_OUTPUT]"
    )


def _extract_response(response: dict) -> tuple[str, str, list[dict]]:
    thinking = response.get("thinking", "")
    answer = response.get("answer", "")
    commands = response.get("commands", [])

    if not commands:
        commands = extract_commands(answer)

    thinking_commands = extract_commands(thinking)
    thinking_codes = {cmd["code"] for cmd in thinking_commands}
    commands = [cmd for cmd in commands if cmd["code"] not in thinking_codes]

    return thinking, answer, commands


@app.get("/", response_class=HTMLResponse)
async def index():
    return HTMLResponse(content=INDEX_HTML)


@app.post("/api/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    if not provider:
        return JSONResponse(status_code=500, content={"error": "Provider not initialized"})

    loop = asyncio.get_running_loop()

    if request.session_id is None or request.session_id not in session_data:
        if request.session_id is None:
            request.session_id = str(uuid.uuid4())
        full_prompt = f"{SYSTEM_PROMPT}\n\n{request.prompt}" if SYSTEM_PROMPT else request.prompt
        session_data[request.session_id] = True
    else:
        full_prompt = request.prompt

    def send_and_get():
        provider.send_prompt(full_prompt)
        return provider.get_response()

    response = await loop.run_in_executor(None, send_and_get)
    thinking, answer, commands = _extract_response(response)
    return ChatResponse(thinking=thinking, answer=answer, commands=commands)


@app.websocket("/ws/execute")
async def websocket_execute(websocket: WebSocket):
    await websocket.accept()

    # Receive command from client
    init_msg = await websocket.receive_text()
    try:
        cmd_data = json.loads(init_msg)
        command = cmd_data.get("command", "")
    except Exception:
        await websocket.close(code=4000, reason="Invalid JSON")
        return

    if not command:
        await websocket.close(code=4000, reason="No command provided")
        return

    print(f"[WebSocket] Running: {command[:100]}...")

    # Fork PTY
    pid, master_fd = pty.fork()
    if pid == 0:
        # Child: become session leader (creates new process group)
        try:
            os.setsid()
        except OSError:
            pass

        # Execute command via shell
        os.execvp("/bin/sh", ["/bin/sh", "-c", command])
        os._exit(1)

    # Parent: set master_fd to non-blocking (write safety)
    flags = fcntl.fcntl(master_fd, fcntl.F_GETFL)
    fcntl.fcntl(master_fd, fcntl.F_SETFL, flags | os.O_NONBLOCK)

    loop = asyncio.get_running_loop()
    output_chunks = []
    exit_status = None

    # Read from PTY using asyncio reader event
    reader_queue = asyncio.Queue()

    def pty_reader_callback():
        try:
            data = os.read(master_fd, 4096)
            if data:
                reader_queue.put_nowait(data)
            else:
                reader_queue.put_nowait(None)  # EOF
        except (OSError, BlockingIOError):
            pass

    loop.add_reader(master_fd, pty_reader_callback)

    # Wait for process exit in a thread
    async def wait_for_exit():
        nonlocal exit_status
        _, status = await loop.run_in_executor(None, os.waitpid, pid, 0)
        exit_status = os.waitstatus_to_exitcode(status)
        return exit_status

    async def read_pty():
        while True:
            data = await reader_queue.get()
            if data is None:
                break
            output_chunks.append(data)
            await websocket.send_bytes(data)

    async def write_ws_to_pty():
        try:
            while True:
                msg = await websocket.receive()
                if "text" in msg:
                    try:
                        obj = json.loads(msg["text"])
                    except json.JSONDecodeError:
                        # Treat as raw stdin
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
                            print(f"Resize error: {e}")
                    elif obj.get("type") == "signal":
                        sig = getattr(signal, obj.get("signal", ""), None)
                        if sig and pid > 0:
                            try:
                                os.killpg(pid, sig)
                            except OSError:
                                pass
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
            pass

    reader_task = asyncio.create_task(read_pty())
    writer_task = asyncio.create_task(write_ws_to_pty())
    exit_task = asyncio.create_task(wait_for_exit())

    # Wait for process to finish
    await exit_task

    # Stop the reader and drain final bytes
    loop.remove_reader(master_fd)
    await reader_queue.put(None)  # signal stop

    try:
        await asyncio.wait_for(reader_task, timeout=1)
    except (asyncio.CancelledError, asyncio.TimeoutError):
        pass

    writer_task.cancel()

    # Collect final output
    final_output = b"".join(output_chunks).decode(errors="replace")

    # Send exit message
    await websocket.send_text(json.dumps({
        "type": "exit",
        "code": exit_status if exit_status is not None else -1,
        "output": final_output
    }))

    await websocket.close()

    # Cleanup
    try:
        os.close(master_fd)
    except OSError:
        pass


@app.post("/api/ai-feedback", response_model=AIFeedbackResponse)
async def ai_feedback(request: AIFeedbackRequest):
    """Feed command output to the AI and return its analysis."""
    if not provider:
        return JSONResponse(status_code=500, content={"error": "Provider not initialized"})

    loop = asyncio.get_running_loop()

    def send_wrapped_and_get():
        wrapped = build_wrapped_command_output(
            request.command, request.exit_code, request.stdout, request.stderr
        )
        provider.send_prompt(wrapped)
        return provider.get_response()

    ai_response = await loop.run_in_executor(None, send_wrapped_and_get)
    thinking, answer, commands = _extract_response(ai_response)

    return AIFeedbackResponse(
        thinking=thinking,
        answer=answer,
        commands=commands,
    )