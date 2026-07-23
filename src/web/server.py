import asyncio
import re
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


# Known language identifiers that DeepSeek may use as bare code fences
KNOWN_LANGUAGES = (
    "python", "javascript", "js", "bash", "sh", "html", "css",
    "json", "yaml", "yml", "sql", "text", "markdown", "md",
    "rust", "go", "java", "c", "cpp", "csharp", "typescript", "ts",
    "ruby", "php", "swift", "kotlin", "r", "scala", "perl",
)


def fix_broken_fences(text: str) -> str:
    """
    DeepSeek sometimes prematurely closes a fenced code block
    and continues the code outside. Merge those back together.
    """
    lines = text.split("\n")
    result = []
    i = 0
    while i < len(lines):
        line = lines[i]
        result.append(line)

        stripped = line.strip()
        if stripped.startswith("```"):
            i += 1
            while i < len(lines):
                if lines[i].strip() == "```":
                    peek = i + 1
                    while peek < len(lines) and lines[peek].strip() == "":
                        peek += 1
                    if peek < len(lines) and (
                        lines[peek].startswith("    ") or lines[peek].startswith("\t")
                    ):
                        result.pop()  # remove premature closing fence
                        i += 1
                        while i < len(lines):
                            line = lines[i]
                            stripped = line.strip()
                            if stripped == "":
                                ahead = i + 1
                                while ahead < len(lines) and lines[ahead].strip() == "":
                                    ahead += 1
                                if ahead >= len(lines) or not (
                                    lines[ahead].startswith("    ") or lines[ahead].startswith("\t")
                                ):
                                    result.append("```")
                                    break
                                else:
                                    result.append(line)
                            elif stripped.startswith("```"):
                                result.append("```")
                                i -= 1
                                break
                            else:
                                result.append(line)
                            i += 1
                        else:
                            result.append("```")
                        break
                    else:
                        i += 1
                        break
                else:
                    result.append(lines[i])
                    i += 1
        i += 1

    return "\n".join(result)


def fix_inline_code_patterns(text: str) -> str:
    """
    Protect Python‑style patterns that Markdown parsers misinterpret
    when they appear outside code blocks.

    - `@decorator`  → wrapped in backticks
    - `__dunder__`  → wrapped in backticks
    - `*args`, `**kwargs` → wrapped in backticks
    """
    # Split text into fenced blocks and non‑fenced prose.
    # We only modify the prose parts.
    parts = re.split(r"(```[\s\S]*?```)", text)
    for idx, part in enumerate(parts):
        if part.startswith("```"):
            continue  # leave code blocks untouched

        # @decorator patterns (e.g., @lru_cache, @staticmethod)
        # Only match when preceded by word boundary, not already in backticks.
        part = re.sub(
            r"(?<!`)\b(@\w+(?:\.\w+)*)\b(?!`)",
            r"`\1`",
            part,
        )

        # __dunder__ patterns (e.g., __name__, __main__, __init__)
        part = re.sub(
            r"(?<!`)\b(__\w+__)\b(?!`)",
            r"`\1`",
            part,
        )

        # *args and **kwargs
        part = re.sub(
            r"(?<!`)(\*{1,2}\w+)(?!`)",
            r"`\1`",
            part,
        )

        parts[idx] = part

    return "".join(parts)


def clean_deepseek_markdown(text: str) -> str:
    """
    Clean DeepSeek's non‑standard markdown so standard parsers can render it.
    """

    # 1. Replace literal "\n" strings with actual newlines
    text = text.replace("\\n", "\n")

    # 2. Remove "Copy" and "Download" tokens that DeepSeek injects
    text = re.sub(r"```(\w*)\nCopy\nDownload\n", r"```\1\n", text)
    text = re.sub(r"\nCopy\nDownload\n", "\n", text)

    # 3. Fix HTML entities that sometimes appear
    text = text.replace("&lt;", "<").replace("&gt;", ">")

    # 4. Auto‑wrap indented code blocks missing opening fences
    def wrap_indented_code(match):
        lang = match.group(1)
        code = match.group(2).rstrip("\n")
        return f"```{lang}\n{code}\n```"

    text = re.sub(
        r"(?:(?<=\n\n)|(?<=^))(" + "|".join(KNOWN_LANGUAGES) + r")\n((?:(?: {4}|\t).*\n?)+)",
        wrap_indented_code,
        text,
        flags=re.MULTILINE,
    )

    # 5. Fallback: wrap non‑indented code blocks after a bare language tag
    def wrap_non_indented_code(match):
        lang = match.group(1)
        code = match.group(2).rstrip("\n")
        return f"```{lang}\n{code}\n```"

    text = re.sub(
        r"(?:(?<=\n\n)|(?<=^))(" + "|".join(KNOWN_LANGUAGES) + r")\n((?:[^\n]+\n)+?)(?=\n|$)",
        wrap_non_indented_code,
        text,
        flags=re.MULTILINE,
    )

    # 6. Merge prematurely‑closed fenced blocks
    text = fix_broken_fences(text)

    # 7. Protect inline code patterns from markdown misinterpretation
    text = fix_inline_code_patterns(text)

    return text


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

    thinking = clean_deepseek_markdown(response.get("thinking", ""))
    answer = clean_deepseek_markdown(response.get("answer", ""))

    return ChatResponse(thinking=thinking, answer=answer)