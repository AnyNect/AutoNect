# AutoNect

**AutoNect** is a personal autonomous AI–Shell bridge.  
It lets you talk to web‑based AI providers (starting with DeepSeek) through
browser automation, then safely execute commands on your local machine.

> 🚧 **Current stage:** the browser bridge is fully working and wrapped in a
> web chat UI (in progress).  The shell‑execution layer is coming next.

---

## ✨ Features

- **No API key required** – AutoNect controls the real DeepSeek web UI via Playwright.
- **Persistent browser session** – log in once, chat forever.
- **Event‑driven waiting** – zero `time.sleep()` calls; pure DOM mutation observers.
- **Perfect extraction** – captures all thinking blocks, search results, and code fences.
- **Markdown cleaner** – transforms DeepSeek's non‑standard output into standard Markdown:
  - balanced code fences
  - inline code wrapping for `__dunder__`, `@decorators`, URLs, emails
  - proper headings, bullet lists, emoji spacing
  - stripped citation numbers and UI artifacts
- **Web chat UI (in progress)** – modern dark chat interface with Markdown rendering.

---

## 🖥️ Web Chat UI – Status

### ✅ What's added
- Send button
- Input box
- User and assistant message rendering

### ❌ What's missing
- Correct Markdown rendering for:
  - Titles
  - Bullet points
  - Tables
  - Code blocks (with integrated copy button)
- Copy full assistant answer button
- Thinking mode toggle
- Search mode toggle

---

## 🏗️ Structure

```
User
 ↓
AutoNect Web UI (FastAPI)
 ↓
DeepSeekProvider (Playwright browser automation)
 ↓
Response Parser & Markdown Cleaner
 ↓
Web UI (displayed as rich Markdown)
```

Planned:
```
 ↓
Command Extractor → Approval Layer → Persistent Shell → Output feeds back to AI
```

---

## 🚀 Installation

### 1. Clone & enter the project

```bash
git clone https://github.com/ZizouuRL/AutoNect
cd AutoNect
```

### 2. Create a virtual environment

```bash
python -m venv .venv
source .venv/bin/activate   # on Fish: source .venv/bin/activate.fish
```

### 3. Install dependencies

```bash
pip install fastapi uvicorn playwright patchright jinja2
python -m playwright install chromium
```

### 4. Configure the browser

Edit `config/settings.json` – set the path to your **Thorium** browser executable:

```json
{
  "browser": {
    "headless": false,
    "thorium_path": "/usr/bin/thorium-browser",
    "profile_path": "~/.config/autonect-browser"
  }
}
```

> If you don't have Thorium, you can use regular Chrome/Chromium – just
> update `src/browser/manager.py` or install Thorium from
> [thorium.rocks](https://thorium.rocks).

### 5. Log in to DeepSeek

Start the browser helper once and log in manually:

```bash
python -m src.test_browser
```

Press Enter when done.  Your login cookies are saved in the profile directory.

### 6. Launch the web chat

```bash
python -m uvicorn src.web.server:app --reload --host 127.0.0.1 --port 8000
```

Open **http://127.0.0.1:8000** and start chatting.

---

## 📁 Project structure

```
src/
├── ai/
│   ├── provider.py              # Abstract AI provider interface
│   └── providers/
│       └── deepseek.py          # DeepSeek provider (Playwright)
├── browser/
│   ├── manager.py               # Browser lifecycle
│   └── observer.py              # DOM mutation observer
├── core/
│   └── config.py                # JSON config loader
├── web/
│   ├── server.py                # FastAPI backend + markdown cleaner
│   ├── templates/
│   │   └── index.html           # Chat UI
│   └── static/
│       ├── styles.css
│       └── script.js
├── test_browser.py              # Launch browser for login
├── test_deepseek.py             # Direct bridge test (terminal)
└── test_cleaner.py              # Markdown cleaner test suite
```

---

## 🧪 Running the tests

The markdown cleaner has a test script with real DeepSeek responses:

```bash
python -m src.web.test_cleaner
```

You can also test the raw bridge without the web UI:

```bash
python -m src.test_deepseek
```

---

## 🔮 Roadmap

- [ ] **UI polish** – finish Markdown rendering, copy buttons, toggles
- [ ] **Command extraction** – identify shell commands in AI responses
- [ ] **Safety approval** – interactive yes/no before execution
- [ ] **Persistent shell session** – maintain state across commands
- [ ] **Conversation history** – full context across multiple back‑and‑forths
- [ ] **Multi‑provider support** – Gemini, Claude, Qwen, Kimi
- [ ] **Self‑healing selectors** – automatic recovery when DeepSeek's DOM changes

---

## 🛠️ Tech stack

- **Browser automation:** Playwright + Patchright (Thorium)
- **Backend:** Python 3.12+ / FastAPI / uvicorn
- **Frontend:** Vanilla HTML/CSS/JS + marked.js
- **Markdown cleaning:** custom regex pipeline

---

## ⚠️ Disclaimer

AutoNect is a personal research project.  Use it responsibly and respect the
terms of service of the AI providers you connect to.