import asyncio
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

    # Extract commands from the already‑clean markdown
    commands = extract_commands(answer)

    return ChatResponse(thinking=thinking, answer=answer, commands=commands)


@app.post("/api/execute", response_model=ExecuteResponse)
async def execute(request: ExecuteRequest):
    try:
        proc = await asyncio.create_subprocess_shell(
            request.command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()
        return ExecuteResponse(
            stdout=stdout.decode(errors="replace"),
            stderr=stderr.decode(errors="replace"),
            exit_code=proc.returncode or 0,
        )
    except Exception as e:
        return ExecuteResponse(stdout="", stderr=str(e), exit_code=1)