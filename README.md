# AutoNect

<p align="center">
  <img src="https://img.shields.io/github/stars/AnyNect/AutoNect?style=for-the-badge&color=blue" alt="Stars">
  <img src="https://img.shields.io/github/license/AnyNect/AutoNect?style=for-the-badge" alt="License">
  <img src="https://img.shields.io/badge/Python-3.10%2B-blue?style=for-the-badge&logo=python" alt="Python">
  <img src="https://img.shields.io/badge/Status-Beta-yellow?style=for-the-badge" alt="Status">
</p>

![AutoNect Banner](banner.svg)

**An autonomous AI–Shell bridge that controls web‑based AI through your browser and executes commands on your local machine.**

---

## 📖 Overview

AutoNect lets you talk to AI providers (starting with DeepSeek) through browser automation, then safely execute the suggested shell commands directly from the chat interface. It combines a lightweight browser controller, a modern web chat UI, and a layered security system into one cohesive tool.

> **Current status:** the browser bridge and chat interface are fully working. The command‑execution layer is in place, with ongoing refinements to security and user experience.

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
| **⚡ Auto‑Allow Mode** | When enabled, commands are automatically approved (after a countdown) and queued for sequential execution – no manual clicks needed. |
| **🖥️ Native Terminal** | "Open Terminal" button launches your preferred terminal emulator (configurable) and keeps it open after command completion. |

---

## 🏗️ Architecture

```
User
  │
  ▼
┌─────────────────────────────────────────────────────────────┐
│  AutoNect Web UI (FastAPI + WebSockets)                    │
│  • Static files: index.html, styles.css, script.js         │
│  • REST endpoints: /api/chat, /api/ai‑feedback, /api/open‑terminal │
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

## 🚀 Quick Install (two commands)

```bash
git clone https://github.com/AnyNect/AutoNect.git
cd AutoNect
chmod +x setup.sh start.sh
./setup.sh
./start.sh
```

### What each script does

- **`setup.sh`** – one‑time setup:
  - Checks Python version (3.10+) and creates a virtual environment.
  - Installs all dependencies (split into `base`, `dev`, `terminal`).
  - Installs Playwright Chromium.
  - Detects your browser (Thorium, Chromium, or Chrome) and generates `config/settings.json`.
  - Creates `src/ai/providers/deepseek_selectors.json` with default CSS selectors.
  - Generates `src/prompts/system.txt` from `system_template.txt` (substituting environment variables).
  - Creates a `User/` folder for personal AI context.
  - Installs the package in editable mode – makes the `AutoNect` command available.

- **`start.sh`** – launches the server (and handles first‑time login):
  - Activates the virtual environment.
  - Checks if a browser profile exists (stored in `~/.autonect/browser-profile`).
  - If **no** profile → opens the browser for you to log in to DeepSeek once; waits for you to press Enter after logging in.
  - If **profile exists** → skips login and starts the server immediately.
  - Runs `AutoNect` (the server) – you see the URL in the terminal.

> **💡 First‑time only:** you will be prompted to log in to DeepSeek. Your session cookies are saved, so you only need to do this once.

---

## ⚙️ Configuration

All settings are stored in `config/settings.json`. The file is created automatically by `setup.sh`.

### Server settings

```json
"server": {
  "host": "127.0.0.1",
  "port": 8000,
  "reload": false
}
```

- `host` – bind address (use `0.0.0.0` to allow external connections).
- `port` – port number.
- `reload` – set to `true` for auto‑reload during development.

### Browser settings

```json
"browser": {
  "headless": false,
  "thorium_path": "thorium-browser",
  "profile_path": "/home/youruser/.autonect/browser-profile"
}
```

- `headless` – run browser in headless mode (not recommended; you need to log in).
- `thorium_path` – path to your Thorium/Chromium executable.
- `profile_path` – where browser cookies and session data are stored.

### AI provider settings (DeepSeek)

```json
"ai": {
  "provider": "deepseek",
  "timeout_seconds": 180,
  "response_timeout_ms": 180000,
  "base_url": "https://chat.deepseek.com"
}
```

- `provider` – currently only `"deepseek"`.
- `timeout_seconds` – overall timeout for AI operations.
- `response_timeout_ms` – maximum wait time for a response (in milliseconds).
- `base_url` – DeepSeek chat URL (can be changed if needed).

### WebSocket output limit

```json
"websocket": {
  "max_output_bytes": 150000
}
```

- `max_output_bytes` – maximum bytes of command output sent over WebSocket before truncation.

### Terminal emulator settings

```json
"terminal": {
  "command": ["konsole", "-e", "bash", "-c", "{command}; exec bash"],
  "fallback_terminals": ["gnome-terminal", "xterm"]
}
```

- `command` – list of command parts; `{command}` is replaced with the actual command.  
  Use this to adapt to any terminal emulator (e.g., `["alacritty", "-e", "bash", "-c", "{command}; exec bash"]`).
- `fallback_terminals` – if the primary terminal is not found, these are tried in order.

### Safety settings

```json
"safety": {
  "auto_approve": false,
  "blocker_enabled": true
}
```

- `auto_approve` – if `true`, all commands are auto‑approved (disables the security layer). Use with caution.
- `blocker_enabled` – enable/disable the command guard entirely.

### Logging

```json
"logging": {
  "level": "INFO"
}
```

- `level` – one of `DEBUG`, `INFO`, `WARNING`, `ERROR`.

### DeepSeek CSS selectors

The file `src/ai/providers/deepseek_selectors.json` contains all selectors used to interact with the DeepSeek UI. You can update it if DeepSeek changes its layout:

```json
{
  "textarea": "textarea[placeholder=\"Message DSeek\"]",
  "send_button": "div[role=\"button\"].ds-button--primary.ds-button--filled:not(.ds-button--disabled)",
  "retry_button": "div[role=\"button\"].ds-button--warning",
  "thinking_block": ".ds-think-content",
  "assistant_container": ".ds-assistant-message-main-content",
  "language_tag": ".d813de27",
  "code_block": ".md-code-block",
  "primary_button": "div[role=\"button\"].ds-button--primary:not(.ds-button--disabled)"
}
```

---

## 📁 Project Structure

```
AutoNect/
├── config/
│   ├── settings.json              # Main configuration (all values)
│   ├── guard_config.json          # Security policy (paths, patterns)
│   ├── guard_settings.json        # Guard runtime settings
│   └── safe_commands.txt          # Allowlisted commands
│
├── dependencies/
│   ├── base.txt                   # Core runtime dependencies
│   ├── dev.txt                    # Development dependencies (pytest, linters)
│   └── terminal.txt               # Optional terminal integration packages
│
├── src/
│   ├── ai/
│   │   ├── provider.py            # Abstract AI provider interface
│   │   └── providers/
│   │       ├── deepseek.py        # DeepSeek provider (Playwright)
│   │       └── deepseek_selectors.json  # CSS selectors (configurable)
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
│   │   ├── system_template.txt    # Template for system prompt (substituted at setup)
│   │   ├── system.txt             # Generated system prompt (ignored by Git)
│   │   └── system_restricted.txt  # Restricted system prompt
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
│   │   ├── launcher.py            # Entry point for the AutoNect command
│   │   ├── server.py              # FastAPI app + WebSocket endpoint
│   │   ├── templates/
│   │   │   └── index.html         # Chat UI
│   │   └── static/
│   │       ├── styles.css         # All styling (incl. command cards, queue)
│   │       └── script.js          # Client‑side logic (chat, queue, terminal)
│   │
├── tests/                         # All test files
│   ├── test_config.py
│   ├── test_browser.py
│   ├── test_markdown.py
│   ├── test_commands.py
│   ├── test_deepseek.py
│   └── test_deepseek_diagnostic.py
│
├── logs/                          # Application logs (rotating)
├── User/                          # Personal AI context (ignored by Git)
│   ├── README.md
│   ├── notes.md
│   ├── journal.md
│   ├── plans.md
│   └── context.md
├── .gitignore                     # Updated to ignore User/, prompts, logs
├── README.md                      # This file
├── setup.py                       # Package installer (creates AutoNect command)
├── setup.sh                       # One‑command setup script
├── start.sh                       # One‑command start script (login + server)
├── generate_prompt.sh             # Environment detection script
└── LICENSE                        # MIT License
```

---

## 🧪 Testing

All tests are in the `tests/` directory. Run them from the project root:

```bash
# Test configuration loader
python -m tests.test_config

# Launch browser (for login) – use if you need to re‑log in
python -m tests.test_browser

# Test Markdown rendering with a comprehensive prompt
python -m tests.test_markdown

# Test command extraction
python -m tests.test_commands

# Test DeepSeek provider with two‑turn conversation
python -m tests.test_deepseek

# Diagnostic test for DOM mutations
python -m tests.test_deepseek_diagnostic
```

For security tests (still in `src/security/`):

```bash
python -m src.security.test_guard
python -m src.security.test_guard_strict
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
  - **Open Terminal** – launches your configured terminal emulator (or fallback)
  - On Allow: live terminal output via WebSocket, then AI feedback analysis

### Task Queue

- Automatically appears when you send a message while the AI is busy.
- **Drag to reorder** – grab the handle (six dots) and drag.
- **Double‑click a task** to edit it.
- **Pause / Resume** – temporarily stop the queue from processing.
- **Cancel** – remove a task from the queue.

### Auto‑Allow Mode

When the **Auto‑Allow** toggle is activated:

- Commands marked `allow` are immediately queued for execution.
- `warn` commands show a 5‑second countdown, then auto‑approve and queue.
- `deny` commands show a 5‑second countdown, then auto‑decline.
- All approved commands run **sequentially** – the next command waits for the previous one to finish.

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
| **Backend** | Python 3.10+ / FastAPI / uvicorn |
| **Frontend** | Vanilla HTML/CSS/JS + marked.js + Highlight.js + xterm.js |
| **Markdown cleaning** | Custom regex pipeline |
| **Security** | AST parsing (Python), regex pattern matching, obfuscation decoders |
| **Terminal** | pty.fork() + WebSockets + xterm.js |
| **Logging** | Python `logging` with rotating file handler |
| **Dependency management** | `dependencies/` folder with split `base`, `dev`, `terminal` |

---

## 🗺️ Roadmap

- [x] Auto‑Allow queue for sequential command execution
- [x] Native terminal integration (configurable emulator)
- [x] Professional logging across all modules
- [x] CSS cleanup and UI polish
- [x] One‑command setup script
- [x] One‑command start script (login + server)
- [x] Moved tests into `tests/` directory
- [x] Global `AutoNect` command and configurable port
- [x] Configurable WebSocket output limit and terminal command
- [x] CSS selectors moved to external JSON file
- [x] AI response timeout and base URL configurable
- [ ] **Chat history** – persistent conversations using `localStorage` (next feature)
- [ ] User authentication and session management
- [ ] Support for more terminal emulators out‑of‑the‑box
- [ ] Cross‑platform support (Windows, macOS)
- [ ] Dark/light theme toggle

---

## ⚠️ Disclaimer

AutoNect is a personal research project. Use it responsibly and respect the terms of service of the AI providers you connect to. The security layer is designed to protect your system, but it is not a substitute for human judgement. Always review commands before allowing them to run.

---

## 📄 License

MIT License – see the [LICENSE](LICENSE) file for details.

---

## 🤝 Acknowledgments

- [Playwright](https://playwright.dev/) – browser automation
- [FastAPI](https://fastapi.tiangolo.com/) – web framework
- [marked.js](https://marked.js.org/) – Markdown rendering
- [Highlight.js](https://highlightjs.org/) – syntax highlighting
- [xterm.js](https://xtermjs.org/) – terminal emulation
- [DeepSeek](https://chat.deepseek.com) – the AI provider

---

## 🤝 Contributing

We welcome contributions! Please read our [Contributing Guide](CONTRIBUTING.md) to get started.

---

*Built with ❤️ by AnyNect*