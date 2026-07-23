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
    # Protect *args / **kwargs only when they are NOT part of a bold/italic pair
    (r"(?<!`)(\*{1,2}\w+)(?!`)(?!.*\*)", r"`\1`"),
    (r"(?<!`)\b(\w+\s*\*\s*\w+)\b(?!`)", r"`\1`"),
    (r"(?<!`)(?<!\*)\b(\w+\*\w+)\b(?!\*)(?!`)", r"`\1`"),
]

_FENCE_RE = re.compile(r"^```(\w*)$")

_CITATION_RE = re.compile(r"\s*-\s*\d{1,3}\s*")

_TLD_LIST = (
    r"co\.uk|com|org|net|io|de|info|biz|edu|gov|mil|app|dev|ai|sh|gg|co"
)
_DOMAIN_RE = re.compile(
    rf"(?<![`a-zA-Z0-9._%+-/])"
    rf"((?:[a-zA-Z0-9](?:[a-zA-Z0-9-]*[a-zA-Z0-9])?\.)+"
    rf"(?:{_TLD_LIST}))"
    rf"(?![a-zA-Z0-9._%+-/`])"
)

_URL_RE = re.compile(r"(?<!`)(https?://[^\s\)\]>]+?)(?=[\s\)\]>]|$)(?!`)")

_EMAIL_RE = re.compile(r"(?<!`)([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})(?!`)")

_PRICE_ITEM_RE = re.compile(r"(\w[\w\s]*?:\s*\$\d[\d.,]*\s*(?:USD|EUR|GBP)?)")


def _replace_smart_quotes(text: str) -> str:
    for k, v in _SMART_QUOTE_MAP.items():
        text = text.replace(k, v)
    return text


def _is_blank(line: str) -> bool:
    return line.strip() == ""


def _normalize_horizontal_whitespace(text: str) -> str:
    return re.sub(r"[\u00a0\u1680\u180e\u2000-\u200a\u202f\u205f\u3000\t]", " ", text)


def _strip_citations(text: str) -> str:
    # 1. Remove citation numbers and their invisible hyphen prefix
    text = _CITATION_RE.sub(" ", text)
    # 2. Remove orphan hyphens left by link‑only citation badges
    text = re.sub(r"(\S)-(\s|$)", r"\1\2", text)
    # 3. Clean up spacing around punctuation
    text = re.sub(r"\s+([.,;:!?])", r"\1", text)
    text = re.sub(r"  +", " ", text)
    return text


def _wrap_urls_and_emails(prose: str) -> str:
    prose = _normalize_horizontal_whitespace(prose)
    protected = re.split(r"(`[^`]+`)", prose)
    for idx, chunk in enumerate(protected):
        if chunk.startswith("`") and chunk.endswith("`"):
            continue
        chunk = _URL_RE.sub(r"`\1`", chunk)
        chunk = _EMAIL_RE.sub(r"`\1`", chunk)
        chunk = _DOMAIN_RE.sub(r"`\1`", chunk)
        protected[idx] = chunk
    return "".join(protected)


def _split_price_list(line: str) -> str | list[str]:
    items = _PRICE_ITEM_RE.findall(line)
    if len(items) >= 3:
        return [f"* {item.strip()}" for item in items]
    return line


def _split_inline_lists(text: str) -> str:
    lines = text.split("\n")
    result = []
    for line in lines:
        # ● or • bullet lists (treat as unordered)
        if re.match(r"^((?:[•●]\s+[^•●]+\s*){2,})$", line):
            items = re.findall(r"[•●]\s+(.+?)(?=\s*[•●]\s+|$)", line)
            for item in items:
                result.append(f"* {item.strip()}")
            continue
        # o or O bullet lists (sub‑lists used by DeepSeek)
        if re.match(r"^((?:[oO]\s+[^oO]+\s*){2,})$", line):
            items = re.findall(r"[oO]\s+(.+?)(?=\s*[oO]\s+|$)", line)
            for item in items:
                result.append(f"* {item.strip()}")
            continue
        if re.match(r"^((?:\*\s+[^*]+\s*){2,})$", line):
            items = re.findall(r"\*\s+(.+?)(?=\s*\*\s+|$)", line)
            for item in items:
                result.append(f"* {item.strip()}")
            continue
        if re.match(r"^((?:\d+\.\s+[^\d]+\s*){2,})$", line):
            items = re.findall(r"\d+\.\s+(.+?)(?=\s*\d+\.\s+|$)", line)
            for i, item in enumerate(items, 1):
                result.append(f"{i}. {item.strip()}")
            continue

        split_result = _split_price_list(line)
        if isinstance(split_result, list):
            result.extend(split_result)
            continue

        result.append(line)
    return "\n".join(result)


# ── Heading detection ──
_HEADING_EXCLUDED = {
    "Here is a breakdown of my findings:",
    "It offers three versions of the tool:",
    "The page lists three versions of the device:",
    "Here's what my research indicates:",
}

_HEADING_CANDIDATE_RE = re.compile(
    r"^(?![\*\-\d>|`])(?![a-z])(?!.*\.$)(.{3,120})$", re.MULTILINE
)


def _add_headings(text: str) -> str:
    parts = re.split(r"(```[\s\S]*?```)", text)
    for idx, part in enumerate(parts):
        if part.startswith("```"):
            continue
        lines = part.split("\n")
        n = len(lines)
        for i in range(n):
            line = lines[i]
            stripped = line.strip()
            if stripped.startswith("#") or stripped in _HEADING_EXCLUDED:
                continue
            if not _HEADING_CANDIDATE_RE.match(stripped):
                continue
            prev_ok = i == 0 or _is_blank(lines[i - 1])
            next_ok = i == n - 1 or _is_blank(lines[i + 1])
            if prev_ok and next_ok:
                lines[i] = f"### {stripped}"
        parts[idx] = "\n".join(lines)
    return "".join(parts)


def _normalise_list_spacing(text: str) -> str:
    """Reduce multiple spaces after a list marker to a single space."""
    text = re.sub(r"^(\s*)(\*)( {2,})", r"\1\2 ", text, flags=re.MULTILINE)
    text = re.sub(r"^(\s*)(\d+\.)( {2,})", r"\1\2 ", text, flags=re.MULTILINE)
    return text


def _normalise_emoji_spacing(text: str) -> str:
    """
    Ensure there is a single space between an emoji and any adjacent
    non‑space character that is not itself an emoji.
    """
    text = re.sub(
        r"([\U0001F300-\U0001F9FF\u2600-\u27BF\u2B50-\u2B55\u231A-\u231B"
        r"\u23CF\u23E9-\u23F3\u23F8-\u23FA\u25AA-\u25AB\u25B6\u25C0"
        r"\u25FB-\u25FE\u2934-\u2935\u3030\u303D\u3297\u3299])"
        r"(?=[^\s\U0001F300-\U0001F9FF\u2600-\u27BF\u2B50-\u2B55\u231A-\u231B"
        r"\u23CF\u23E9-\u23F3\u23F8-\u23FA\u25AA-\u25AB\u25B6\u25C0"
        r"\u25FB-\u25FE\u2934-\u2935\u3030\u303D\u3297\u3299])",
        r"\1 ",
        text,
        flags=re.MULTILINE,
    )
    return text


def _post_process_cleanup(text: str) -> str:
    text = re.sub(r"\s+([.,;:!?)])", r"\1", text)
    text = re.sub(r" {2,}", " ", text)
    text = re.sub(r"[ \t]+$", "", text, flags=re.MULTILINE)
    return text


def fix_all_fences(text: str) -> str:
    lines = text.split("\n")
    result = []
    i = 0
    n = len(lines)

    while i < n:
        line = lines[i]
        s = line.strip()

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

        result.append(line)
        i += 1

    return "\n".join(result)


def fix_inline_code_patterns(text: str) -> str:
    parts = re.split(r"(```[\s\S]*?```)", text)
    for idx, part in enumerate(parts):
        if part.startswith("```"):
            continue
        part = _strip_citations(part)
        part = _wrap_urls_and_emails(part)
        # Remove citation hyphens that still cling to backtick‑wrapped elements
        part = re.sub(r"(`[^`]*`)-(\s|$)", r"\1\2", part)
        for pattern, replacement in _INLINE_PATTERNS:
            part = re.sub(pattern, replacement, part)
        part = _split_inline_lists(part)
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
    text = _add_headings(text)
    text = _post_process_cleanup(text)
    text = _normalise_list_spacing(text)
    text = _normalise_emoji_spacing(text)
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