# AutoNect

**AutoNect** is a personal autonomous AI–Shell bridge.  
It lets you talk to web‑based AI providers (starting with DeepSeek) through
browser automation, then safely execute commands on your local machine.

> 🚧 **Current stage:** the browser bridge is fully working.
> A web chat UI and a markdown cleaner are under active development on the
> `Chat-UI` branch.  The shell‑execution layer is coming next.

---

## ✨ Features

- **No API key required** – AutoNect controls the real DeepSeek web UI via Playwright.
- **Persistent browser session** – log in once, chat forever.
- **Event‑driven waiting** – zero `time.sleep()` calls; pure DOM mutation observers.
- **Perfect extraction** – captures all thinking blocks, search results, and code fences.

---

## 🖥️ Web Chat UI & Markdown Cleaner

A modern dark web chat interface and a companion Markdown cleaner are under active
development on the **`Chat-UI`** branch.  That branch adds:

### Web Chat UI
- Send button and input box
- User and assistant message rendering
- Markdown display with collapsible thinking blocks
- Beautiful Catppuccin‑inspired design

### Markdown Cleaner
- Balanced code fences
- Inline code wrapping for `__dunder__`, `@decorators`, URLs, emails
- Proper headings, bullet lists, emoji spacing
- Stripped citation numbers and UI artifacts

Once complete, they will be merged into `main`.

---

## 🏗️ Architecture

```
User
 ↓
AutoNect (terminal or web UI)
 ↓
DeepSeekProvider (Playwright browser automation)
 ↓
Response Parser & Markdown Cleaner
 ↓
Display (terminal or web UI)
```

Planned:
```
 ↓
Command Extractor → Approval Layer → Persistent Shell → Output feeds back to AI
```

---

## 🚀 Quick Start

### 1. Clone & enter the project

```bash
git clone <your-repo-url>
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

### 6. Test the bridge (terminal)

```bash
python -m src.test_deepseek
```

You'll see the thinking and answer extracted in the terminal.

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
├── web/                         # (Chat-UI branch)
│   ├── server.py                # FastAPI backend + markdown cleaner
│   ├── templates/
│   │   └── index.html
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

- [ ] **Chat UI** – finish web interface (in progress on `Chat-UI`)
- [ ] **Command extraction** – identify shell commands in AI responses
- [ ] **Safety approval** – interactive yes/no before execution
- [ ] **Persistent shell session** – maintain state across commands
- [ ] **Conversation history** – full context across multiple back‑and‑forths
- [ ] **Multi‑provider support** – Gemini, Claude, Qwen, Kimi
- [ ] **Self‑healing selectors** – automatic recovery when DeepSeek's DOM changes

---

## 🛠️ Tech stack

- **Browser automation:** Playwright + Patchright (Thorium)
- **Backend:** Python 3.12+ / FastAPI / uvicorn (web UI on `Chat-UI`)
- **Frontend:** Vanilla HTML/CSS/JS + marked.js (on `Chat-UI`)
- **Markdown cleaning:** custom regex pipeline (on `Chat-UI`)

---

## ⚠️ Disclaimer

AutoNect is a personal research project.  Use it responsibly and respect the
terms of service of the AI providers you connect to.