import asyncio
import uuid
from typing import Optional
import re
from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI
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

# Session tracking: store if system prompt has been sent
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


class ExecuteRequest(BaseModel):
    command: str


class ExecuteResponse(BaseModel):
    stdout: str
    stderr: str
    exit_code: int


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
    """Extract thinking, answer, and commands from a provider response dict."""
    thinking = response.get("thinking", "")
    answer = response.get("answer", "")
    commands = response.get("commands", [])

    # If DOM extraction found nothing, fall back to regex on the answer.
    if not commands:
        commands = extract_commands(answer)

    # Also scan the thinking text for commands we should filter out.
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

    # Determine the full prompt and session handling before entering executor
    if request.session_id is None or request.session_id not in session_data:
        # First message for this session: send system prompt
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


@app.post("/api/execute", response_model=ExecuteResponse)
async def execute(request: ExecuteRequest):
    """Run a shell command and return stdout, stderr, exit_code immediately."""
    print(f"[Execute] Running: {request.command[:100]}...")
    try:
        proc = await asyncio.create_subprocess_shell(
            request.command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()
        stdout_str = stdout.decode(errors="replace") if stdout else ""
        stderr_str = stderr.decode(errors="replace") if stderr else ""
        exit_code = proc.returncode if proc.returncode is not None else -1
    except Exception as e:
        stdout_str = ""
        stderr_str = str(e)
        exit_code = 1

    print(f"[Execute] Exit code: {exit_code}")
    return ExecuteResponse(
        stdout=stdout_str,
        stderr=stderr_str,
        exit_code=exit_code,
    )


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