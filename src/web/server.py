import asyncio
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


@app.get("/", response_class=HTMLResponse)
async def index():
    return HTMLResponse(content=INDEX_HTML)


@app.post("/api/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    if not provider:
        return JSONResponse(status_code=500, content={"error": "Provider not initialized"})

    loop = asyncio.get_running_loop()

    def send_and_get():
        full_prompt = f"{SYSTEM_PROMPT}\n\n{request.prompt}" if SYSTEM_PROMPT else request.prompt
        provider.send_prompt(full_prompt)
        return provider.get_response()

    response = await loop.run_in_executor(None, send_and_get)

    thinking = response.get("thinking", "")
    answer = response.get("answer", "")

    # Extract commands from the answer
    answer_commands = extract_commands(answer)

    # Filter out commands that appeared in thinking
    thinking_commands = extract_commands(thinking)
    thinking_codes = {cmd["code"] for cmd in thinking_commands}
    commands = [cmd for cmd in answer_commands if cmd["code"] not in thinking_codes]

    # Remove ```command blocks from the answer so the markdown bubble
    # doesn't show a duplicate
    answer = re.sub(r'```command\s*\n.*?```\n?', '', answer, flags=re.DOTALL)

    return ChatResponse(thinking=thinking, answer=answer, commands=commands)


@app.post("/api/execute", response_model=ExecuteResponse)
async def execute(request: ExecuteRequest):
    """Run a shell command and return stdout, stderr, exit_code."""
    print(f"[Execute] Received command: {request.command[:100]}...")
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

        print(f"[Execute] Exit code: {exit_code}, stdout len: {len(stdout_str)}, stderr len: {len(stderr_str)}")

        return ExecuteResponse(
            stdout=stdout_str,
            stderr=stderr_str,
            exit_code=exit_code,
        )
    except Exception as e:
        print(f"[Execute] Error: {e}")
        return ExecuteResponse(stdout="", stderr=str(e), exit_code=1)