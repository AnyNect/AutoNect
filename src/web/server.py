import asyncio
from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from src.ai.providers.deepseek import DeepSeekProvider

# Singleton provider — shared across requests
provider: DeepSeekProvider | None = None

BASE_DIR = Path(__file__).parent
TEMPLATES_DIR = BASE_DIR / "templates"
STATIC_DIR = BASE_DIR / "static"
INDEX_HTML = (TEMPLATES_DIR / "index.html").read_text(encoding="utf-8")


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

# Serve static files (CSS, JS)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


class ChatRequest(BaseModel):
    prompt: str


class ChatResponse(BaseModel):
    thinking: str
    answer: str


@app.get("/", response_class=HTMLResponse)
async def index():
    return HTMLResponse(content=INDEX_HTML)


@app.post("/api/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    if not provider:
        return JSONResponse(
            status_code=500, content={"error": "Provider not initialized"}
        )

    loop = asyncio.get_running_loop()

    def send_and_get():
        provider.send_prompt(request.prompt)
        return provider.get_response()

    response = await loop.run_in_executor(None, send_and_get)
    return ChatResponse(
        thinking=response.get("thinking", ""),
        answer=response.get("answer", ""),
    )