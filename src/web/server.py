import asyncio
import re
from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from src.ai.providers.deepseek import DeepSeekProvider

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
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


class ChatRequest(BaseModel):
    prompt: str


class ChatResponse(BaseModel):
    thinking: str
    answer: str


KNOWN_LANGUAGES = {
    "python", "javascript", "js", "bash", "sh", "html", "css",
    "json", "yaml", "yml", "sql", "text", "markdown", "md",
    "rust", "go", "java", "c", "cpp", "csharp", "typescript", "ts",
    "ruby", "php", "swift", "kotlin", "r", "scala", "perl",
}

_SMART_QUOTE_MAP = {
    "\u201c": '"', "\u201d": '"',
    "\u2018": "'", "\u2019": "'",
    "\u2013": "-", "\u2014": "--",
    "\u2011": "-", "\u2026": "...",
    "\u00a0": " ",
}

_INLINE_PATTERNS = [
    (r"(?<!`)\b(@\w+(?:\.\w+)*)\b(?!`)", r"`\1`"),
    (r"(?<!`)\b(__\w+__)\b(?!`)", r"`\1`"),
    (r"(?<!`)(\*{1,2}\w+)(?!`)", r"`\1`"),
    (r"(?<!`)\b(\w+\s*\*\s*\w+)\b(?!`)", r"`\1`"),
    (r"(?<!`)(?<!\*)\b(\w+\*\w+)\b(?!\*)(?!`)", r"`\1`"),
]

_FENCE_RE = re.compile(r"^```(\w*)$")

# Regex patterns for citation stripping and URL/email wrapping
_CITATION_RE = re.compile(r"\s*-\s*\d+\s*")
_URL_RE = re.compile(r"(?<!`)(https?://[^\s\)\]>]+?)(?=[\s\)\]>]|$)(?!`)")
_EMAIL_RE = re.compile(r"(?<!`)([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})(?!`)")


def _replace_smart_quotes(text: str) -> str:
    for k, v in _SMART_QUOTE_MAP.items():
        text = text.replace(k, v)
    return text


def _is_blank(line: str) -> bool:
    return line.strip() == ""


def _strip_citations(text: str) -> str:
    """Remove DeepSeek inline citation numbers (e.g., ' -1', '-79')."""
    # Replace " -1" or "-\n1" with a single space, careful not to merge words
    text = re.sub(r"\s*-\s*\d{1,3}\s*", " ", text)
    # Remove trailing "-\n" that might remain
    text = re.sub(r"\s*-\s*\n\s*", " ", text)
    return text


def _wrap_urls_and_emails(prose: str) -> str:
    """Wrap bare URLs and email addresses in backticks."""
    prose = _URL_RE.sub(r"`\1`", prose)
    prose = _EMAIL_RE.sub(r"`\1`", prose)
    return prose


def fix_all_fences(text: str) -> str:
    lines = text.split("\n")
    result = []
    i = 0
    n = len(lines)

    while i < n:
        line = lines[i]
        s = line.strip()

        # (A) Bare language tag
        if s in KNOWN_LANGUAGES and (i == 0 or _is_blank(lines[i - 1])):
            result.append(f"```{s}")
            i += 1
            while i < n:
                li = lines[i]
                st = li.strip()

                if st == "```":
                    ahead = i + 1
                    while ahead < n and _is_blank(lines[ahead]):
                        ahead += 1
                    if ahead < n and (
                        lines[ahead].startswith("    ") or
                        lines[ahead].startswith("\t")
                    ):
                        i += 1
                        continue
                    else:
                        result.append("```")
                        i += 1
                        break

                result.append(li)
                i += 1
            else:
                result.append("```")
            continue

        # (B) Existing fence
        if _FENCE_RE.match(s):
            result.append(line)
            i += 1
            while i < n:
                li = lines[i]
                st = li.strip()

                if _FENCE_RE.match(st):
                    ahead = i + 1
                    while ahead < n and _is_blank(lines[ahead]):
                        ahead += 1
                    if ahead < n and (
                        lines[ahead].startswith("    ") or
                        lines[ahead].startswith("\t")
                    ):
                        i += 1
                        continue
                    else:
                        result.append(li)
                        i += 1
                        break

                result.append(li)
                i += 1
            else:
                result.append("```")
            continue

        # (C) Normal line
        result.append(line)
        i += 1

    return "\n".join(result)


def fix_inline_code_patterns(text: str) -> str:
    parts = re.split(r"(```[\s\S]*?```)", text)
    for idx, part in enumerate(parts):
        if part.startswith("```"):
            continue
        # Strip citations and wrap URLs/emails only in prose
        part = _strip_citations(part)
        part = _wrap_urls_and_emails(part)
        for pattern, replacement in _INLINE_PATTERNS:
            part = re.sub(pattern, replacement, part)
        parts[idx] = part
    return "".join(parts)


def clean_deepseek_markdown(text: str) -> str:
    text = _replace_smart_quotes(text)
    text = text.replace("\\n", "\n")
    text = text.replace('\\"', '"')
    text = re.sub(r"```(\w*)\nCopy\nDownload\n", r"```\1\n", text)
    text = re.sub(r"\nCopy\nDownload\n", "\n", text)
    text = text.replace("&lt;", "<").replace("&gt;", ">")
    text = fix_all_fences(text)
    text = fix_inline_code_patterns(text)
    return text


@app.get("/", response_class=HTMLResponse)
async def index():
    return HTMLResponse(content=INDEX_HTML)


@app.post("/api/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    if not provider:
        return JSONResponse(status_code=500, content={"error": "Provider not initialized"})

    loop = asyncio.get_running_loop()

    def send_and_get():
        provider.send_prompt(request.prompt)
        return provider.get_response()

    response = await loop.run_in_executor(None, send_and_get)

    thinking = clean_deepseek_markdown(response.get("thinking", ""))
    answer = clean_deepseek_markdown(response.get("answer", ""))

    return ChatResponse(thinking=thinking, answer=answer)