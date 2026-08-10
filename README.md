# AutoNect

**An autonomous AI–Shell bridge that controls web‑based AI through your browser and executes commands on your local machine.**

---

## 📖 Overview

AutoNect lets you talk to AI providers (starting with DeepSeek) through browser automation, then safely execute the suggested shell commands directly from the chat interface. It combines a lightweight browser controller, a modern web chat UI, and a layered security system into one cohesive tool.

> 🚧 **Current status:** the browser bridge and chat interface are fully working. The command‑execution layer is in place, with ongoing refinements to security and user experience.

---

## ✨ Features

| Category | Capabilities |
|----------|--------------|
| **🤖 Browser Automation** | Controls the real DeepSeek web UI via Playwright/Patchright – no API key required. Persistent session: log in once, chat forever. |
| **📦 Markdown Pipeline** | Cleans and normalises DeepSeek's output into standard Markdown. Balances code fences, wraps inline code (`__dunder__`, `@decorators`, URLs, emails), fixes headings, bullet lists, and strips UI artefacts. |
| **🖥️ Web Chat UI** | Modern dark interface with Markdown rendering (via `marked.js` + Highlight.js). Interactive command cards with integrated xterm.js terminals. Task queue with reorder, edit, pause/resume. |
| **🔒 Security Layer** | Layered command guard with allow/deny/ask decisions. Detects and blocks destructive commands (`rm -rf`, `find -delete`, obfuscated payloads). Path protection, shell‑composition detection, AST analysis for Python scripts. Session‑based approvals (once / session). |
| **🖱️ Command Execution** | Click‑to‑run commands inside the chat. Live terminal output via WebSocket. AI feedback loop: command output is sent back to the AI for analysis. |
| **🗂️ Task Queue** | Queue up multiple prompts while the AI is generating or a command is running. Drag‑to‑reorder, edit, pause/resume. |

---

## 🏗️ Architecture

```
User
  │
  ▼
┌─────────────────────────────────────────────────────────────┐
│  AutoNect Web UI (FastAPI + WebSockets)                    │
│  • Static files: index.html, styles.css, script.js         │
│  • REST endpoints: /api/chat, /api/ai‑feedback             │
│  • WebSocket: /ws/execute                                  │
└─────────────────────────────────────────────────────────────┘
  │
  ▼
┌─────────────────────────────────────────────────────────────┐
│  DeepSeekProvider (src/ai/providers/deepseek.py)           │
│  • BrowserManager launches Thorium/Chromium                │
│  • DOMObserver waits for response without time.sleep()     │
│  • Extracts thinking, answer, and command blocks           │
└─────────────────────────────────────────────────────────────┘
  │
  ▼
┌─────────────────────────────────────────────────────────────┐
│  Markdown Cleaner (src/web/server.py)                      │
│  • Code‑block placeholders → HTML cards with copy buttons  │
│  • Balanced fences, whitespace normalisation               │
│  • Task‑list conversion, emoji spacing                     │
└─────────────────────────────────────────────────────────────┘
  │
  ▼
┌─────────────────────────────────────────────────────────────┐
│  Security Layer (src/security/)                            │
│  • CommandGuard evaluates every command                    │
│  • PathProtection checks filesystem access                 │
│  • Decoders detect obfuscated payloads (base64, xxd, ...) │
│  • AST matcher for Python dangerous calls                  │
│  • Session‑based approvals                                 │
└─────────────────────────────────────────────────────────────┘
  │
  ▼
┌─────────────────────────────────────────────────────────────┐
│  Execution (WebSocket + PTY)                               │
│  • pty.fork() for interactive shell sessions               │
│  • Terminal emulation via xterm.js                         │
│  • Output streaming back to the UI                         │
└─────────────────────────────────────────────────────────────┘
```

---

## 🚀 Installation

### 1. Clone the repository

```bash
git clone https://github.com/ZizouuRL/AutoNect.git
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

Edit `config/settings.json` to point to your browser executable:

```json
{
  "browser": {
    "headless": false,
    "thorium_path": "/usr/bin/thorium-browser",
    "profile_path": "/home/youruser/.autonect/browser-profile"
  },
  "ai": {
    "provider": "deepseek",
    "timeout_seconds": 60
  },
  "safety": {
    "auto_approve": false,
    "blocker_enabled": true
  },
  "logging": {
    "level": "INFO"
  }
}
```

> If you don't have Thorium, install it from [thorium.rocks](https://thorium.rocks) or modify `src/browser/manager.py` to use regular Chrome/Chromium.

### 5. Log in to DeepSeek

Start the browser helper once and log in manually:

```bash
python -m src.test_browser
```

Press Enter when done. Your login cookies are saved in the profile directory.

### 6. Launch the web chat

```bash
python -m uvicorn src.web.server:app --reload --host 127.0.0.1 --port 8000
```

Open **http://127.0.0.1:8000** and start chatting.

---

## 📁 Project Structure

```
AutoNect/
├── config/
│   ├── settings.json              # Main configuration
│   ├── guard_config.json          # Security policy (paths, patterns)
│   ├── guard_settings.json        # Guard runtime settings
│   └── safe_commands.txt          # Allowlisted commands
│
├── src/
│   ├── ai/
│   │   ├── provider.py            # Abstract AI provider interface
│   │   └── providers/
│   │       └── deepseek.py        # DeepSeek provider (Playwright)
│   │
│   ├── browser/
│   │   ├── manager.py             # Browser lifecycle (Thorium/Chromium)
│   │   └── observer.py            # DOM mutation observer
│   │
│   ├── core/
│   │   └── config.py              # JSON config loader
│   │
│   ├── parser/
│   │   └── commands.py            # Extract ```command blocks from text
│   │
│   ├── prompts/
│   │   ├── system.txt             # System prompt for CachyOS (bash)
│   │   └── system_restricted.txt  # System prompt for Fish shell
│   │
│   ├── security/
│   │   ├── command_guard.py       # Main security entry point
│   │   ├── config.py              # Guard configuration loader
│   │   ├── constants.py           # Enums: Severity, Decision, ApprovalMode
│   │   ├── decoder.py             # Obfuscation decoders (base64, xxd, perl, ...)
│   │   ├── heredoc.py             # Extract embedded scripts from -c / heredoc
│   │   ├── normalize.py           # Strip sudo, normalise spaces
│   │   ├── packs.py               # Pattern packs (filesystem, git, system, obfuscation)
│   │   ├── path_protection.py     # Filesystem path protection
│   │   ├── policy.py              # Core evaluation logic
│   │   ├── resolve.py             # Resolve eval/sh -c wrappers with sed
│   │   ├── session.py             # Session‑based approval manager
│   │   ├── shell_composition.py   # Detect &&, ||, ;, | in commands
│   │   ├── ast_matcher.py         # AST analysis for Python scripts
│   │   ├── test_guard.py          # Unit test suite for destructive/safe commands
│   │   └── test_guard_strict.py   # Strict pass/fail harness
│   │
│   ├── web/
│   │   ├── server.py              # FastAPI app + WebSocket endpoint
│   │   ├── templates/
│   │   │   └── index.html         # Chat UI
│   │   └── static/
│   │       ├── styles.css         # All styling (incl. command cards, queue)
│   │       └── script.js          # Client‑side logic (chat, queue, terminal)
│   │
│   ├── test_browser.py            # Launch browser for login
│   ├── test_deepseek.py           # Direct bridge test (terminal)
│   ├── test_deepseek_diagnostic.py # DOM mutation diagnostics
│   ├── test_markdown.py           # Comprehensive Markdown test prompt
│   ├── test_commands.py           # Test command extraction
│   ├── test_config.py             # Test config loader
│   └── main.py                    # (placeholder – future entry point)
│
├── README.md                      # This file
├── requirements.txt               # (currently empty – use pip install manually)
└── AutoNect_DATABASE.md           # Generated file snapshot (not part of the project)
```

---

## 🧪 Testing

### Command Guard (security layer)

Run the test suite to verify that destructive commands are blocked and safe commands are allowed:

```bash
python -m src.security.test_guard
```

For strict pass/fail (no unsafe → allow, no safe → deny):

```bash
python -m src.security.test_guard_strict
```

### Browser Bridge (raw, without UI)

```bash
python -m src.test_deepseek
```

### Markdown Cleaner

```bash
python -m src.web.test_cleaner
```

### Comprehensive Markdown Rendering Test

```bash
python -m src.test_markdown
```

---

## 🖥️ Web UI Details

### Chat Interface
- **Send** – type a message, press Enter (Shift+Enter for newline).
- **Thinking block** – collapsible section showing the AI's reasoning.
- **Markdown rendering** – headings, lists, tables, code blocks, blockquotes, footnotes, emojis.
- **Command cards** – each ````command` block becomes an interactive card with:
  - Safety tag: `SAFE` / `UNSURE` / `UNSAFE`
  - **Allow** / **Decline** buttons
  - **Open Terminal** – pops up a full‑screen interactive terminal (xterm.js)
  - On Allow: live terminal output via WebSocket, then AI feedback analysis

### Task Queue
- Automatically appears when you send a message while the AI is busy.
- **Drag to reorder** – grab the handle (six dots) and drag.
- **Double‑click a task** to edit it.
- **Pause / Resume** – temporarily stop the queue from processing.
- **Cancel** – remove a task from the queue.

### Terminal Modal
- Click **Open Terminal** on any command card to open a full‑screen xterm.js terminal.
- Fully interactive: type, resize, Ctrl+C, etc.
- Close with the red dot or Escape key.

---

## 🔒 Security Layer

The command guard (`src/security/`) is a multi‑stage evaluator:

1. **Normalisation** – strip `sudo`/`doas`, absolute paths, normalise spaces.
2. **Wrapper resolution** – unwrap `eval "$(…)"`, `sh -c "$(…)"`, handling `sed` transforms.
3. **Obfuscation decoding** – detect and decode:
   - `printf` hex/octal
   - `base64 -d`
   - `xxd -r -p`
   - `perl -e 'print pack("H*", …)'`
   - `echo -e` escapes
   - nested command substitution
4. **Script language checks** – AST analysis for Python, pattern matching for Ruby/Node/PHP/AWK.
5. **Allowlist** – exact match against `safe_commands.txt`.
6. **Shell composition detection** – quote‑aware detection of `&&`, `||`, `;`, `|`, `$(`.
7. **Pattern packs** – destructive patterns for filesystem, git, system, database, obfuscation.
8. **Path protection** – resolves symlinks, checks against `protected_paths`, enforces workspace boundary.
9. **Session approvals** – allow once, allow for session, or deny.

The guard returns one of three decisions: **ALLOW**, **ASK**, or **DENY**.

---

## 🛠️ Tech Stack

| Layer | Technology |
|-------|------------|
| **Browser automation** | Playwright + Patchright (Thorium) |
| **Backend** | Python 3.12+ / FastAPI / uvicorn |
| **Frontend** | Vanilla HTML/CSS/JS + marked.js + Highlight.js + xterm.js |
| **Markdown cleaning** | Custom regex pipeline |
| **Security** | AST parsing (Python), regex pattern matching, obfuscation decoders |
| **Terminal** | pty.fork() + xterm.js + WebSockets |

---

## 🗺️ Roadmap

- [ ] **UI polish** – correct Markdown for titles, bullet points, tables, code blocks (with integrated copy).
- [ ] **Copy full assistant answer** – one‑click copy of the entire response.
- [ ] **Thinking / Search toggles** – control AI behaviour from the UI.
- [ ] **Persistent shell session** – maintain state across multiple command executions.
- [ ] **Conversation history** – full context across multiple back‑and‑forths.
- [ ] **Multi‑provider support** – Gemini, Claude, Qwen, Kimi.
- [ ] **Self‑healing selectors** – automatic recovery when DeepSeek's DOM changes.

---

## ⚠️ Disclaimer

AutoNect is a personal research project. Use it responsibly and respect the terms of service of the AI providers you connect to. The security layer is designed to protect your system, but it is not a substitute for human judgement. Always review commands before allowing them to run.

---

## 📄 License

This project is for personal use only. No license is granted for redistribution or commercial use.

---

## 🤝 Acknowledgments

- [Playwright](https://playwright.dev/) – browser automation
- [FastAPI](https://fastapi.tiangolo.com/) – web framework
- [marked.js](https://marked.js.org/) – Markdown rendering
- [Highlight.js](https://highlightjs.org/) – syntax highlighting
- [xterm.js](https://xtermjs.org/) – terminal emulation
- [DeepSeek](https://chat.deepseek.com) – the AI provider

---

*Built with ❤️ by ZizouuRL*