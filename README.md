# AutoNect

<p align="center">
  <a href="https://github.com/AnyNect/AutoNect/stargazers"><img src="https://img.shields.io/github/stars/AnyNect/AutoNect?style=flat&color=2563eb&logo=github&logoColor=white" alt="Stars"></a>
  <a href="https://github.com/AnyNect/AutoNect/blob/main/LICENSE"><img src="https://img.shields.io/github/license/AnyNect/AutoNect?style=flat&color=059669&logo=opensourceinitiative&logoColor=white" alt="License"></a>
  <img src="https://img.shields.io/badge/Python-3.10%2B-3776AB?style=flat&logo=python&logoColor=white" alt="Python">
  <img src="https://img.shields.io/badge/FastAPI-009688?style=flat&logo=fastapi&logoColor=white" alt="FastAPI">
  <img src="https://img.shields.io/badge/Playwright-2EAD33?style=flat&logo=playwright&logoColor=white" alt="Playwright">
  <img src="https://img.shields.io/badge/Security-Command%20Guard-10b981?style=flat&logo=windows-terminal&logoColor=white" alt="Command Guard">
  <img src="https://img.shields.io/badge/Status-Beta-d97706?style=flat&logo=gitbook&logoColor=white" alt="Status">
</p>

![AutoNect Banner](banner.svg)

**An autonomous AI–Shell bridge that controls web‑based AI through your browser and executes commands on your local machine.**

---

## 📖 Overview

AutoNect lets you talk to AI providers (starting with DeepSeek) through browser automation, then safely execute the suggested shell commands directly from the chat interface. It combines a lightweight browser controller, a modern web chat UI, and a layered security system into one cohesive tool.

> **Current status:** the browser bridge, chat interface, chat history, and CLI are fully working. The command‑execution layer is in place, with ongoing refinements to security and user experience.

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
| **💾 Chat History** | Persistent conversations stored in a local SQLite database. Sidebar with rename, pin, and delete. DeepSeek sessions are re‑navigated automatically when you open an old chat. |
| **⌨️ AnyNect CLI** | Single global command (`AnyNect`) with subcommands for `start`, `setup`, `login`, `test`, and `version`. `AutoNect` remains as a backward‑compatible alias. |

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

## 🚀 Quick Install (one command block)

```bash
git clone https://github.com/AnyNect/AutoNect.git
cd AutoNect
chmod +x setup.sh
./setup.sh
source .venv/bin/activate
AnyNect start
```

> **fish users:** replace `source .venv/bin/activate` with `source .venv/bin/activate.fish`.
> **No‑activation alternative:** replace the last two lines with `.venv/bin/AnyNect start`.

### What the setup does

`setup.sh` is idempotent — safe to run as many times as you like. It:

- Checks Python version (3.10+) and creates `.venv` if missing.
- Installs all dependencies (`base`, `dev`, `terminal` if Konsole is present).
- Installs Playwright Chromium.
- Detects your browser (Thorium, Chromium, or Chrome) and generates `config/settings.json` **only if it does not already exist**.
- Writes `src/ai/providers/deepseek_selectors.json` with up‑to‑date CSS selectors.
- Writes `src/web/launcher.py` (the CLI) — backed up to `.bak` if it changes.
- Installs the package in editable mode, registering the `AnyNect` and `AutoNect` commands.
- Creates a `User/` folder for personal AI context **only if missing**.
- Generates `src/prompts/system.txt` from `system_template.txt` if a template exists, otherwise preserves an existing prompt.
- Takes a single `.bak` snapshot of any generated file before overwriting it.

### The `AnyNect` CLI

After the one‑time setup, you have a global command:

```bash
AnyNect                     # start the server (default subcommand)
AnyNect start --port 8099   # start on a custom port
AnyNect start --host 0.0.0.0 --port 8000 --reload
AnyNect login               # open DeepSeek in your browser for first-time login
AnyNect test all            # run the full test suite
AnyNect test config         # run just the config tests
AnyNect setup               # re-run setup.sh (idempotent)
AnyNect version             # print the version
```

`AutoNect` is registered as a backwards‑compatible alias for every subcommand.

---

## ⚙️ Configuration

All settings are stored in `config/settings.json`. The file is created automatically by `setup.sh` — and **never overwritten if it already exists**, so your customisations survive re‑runs.

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

The file `src/ai/providers/deepseek_selectors.json` contains all selectors used to interact with the DeepSeek UI. It is regenerated by `setup.sh` each time it runs (with a `.bak` snapshot if the contents change), so it stays up to date when DeepSeek ships UI updates:

```json
{
  "textarea": "textarea[placeholder=\"Message DSeek\"]",
  "send_button": "div[role=\"button\"].ds-button--primary.ds-button--filled:not(.ds-button--disabled)",
  "retry_button": "div[role=\"button\"].ds-button--warning",
  "thinking_block": ".ds-think-content",
  "assistant_container": ".ds-assistant-message-main-content",
  "language_tag": ".d813de27",
  "code_block": ".md-code-block",
  "primary_button": "div[role=\"button\"].ds-button--primary:not(.ds-button--disabled)",
  "file_input": "input[type=\"file\"]",
  "chat_title": "#root > div > div.c3ecdb44 > div._7780f2e > div > div._2be88ba > div.f8d1e4c0.the-header > div > div"
}
```

The `chat_title` selector is used by the frontend to read the current DeepSeek chat name and sync it to your local chat history. The frontend applies a fallback chain in `script.js` (see `extractChatTitleFromPage`) so a single selector change on DeepSeek's side does not break chat naming.

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
│   │       └── deepseek_selectors.json  # CSS selectors (regenerated at setup)
│   │
│   ├── browser/
│   │   ├── manager.py             # Browser lifecycle (Thorium/Chromium)
│   │   └── observer.py            # DOM mutation observer
│   │
│   ├── core/
│   │   └── config.py              # JSON config loader
│   │
│   ├── database/                  # SQLite chat history
│   │   └── __init__.py            # upsert_chat, add_message, get_chat, ...
│   │
│   ├── parser/
│   │   └── commands.py            # Extract ```command blocks from text
│   │
│   ├── prompts/
│   │   ├── system_template.txt    # Template for system prompt (substituted at setup)
│   │   ├── system.txt             # Generated system prompt (preserved on re-run)
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
│   │   ├── launcher.py            # AnyNect CLI entry point (installed by setup)
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
├── setup.py                       # Package installer (registers AnyNect + AutoNect)
├── setup.sh                       # One‑command setup script (idempotent)
├── generate_prompt.sh             # Environment detection script
└── LICENSE                        # MIT License
```

---

## 🧪 Testing

All tests are in the `tests/` directory. Run them from the project root, or use the CLI wrapper:

```bash
# Using the CLI (recommended)
AnyNect test all
AnyNect test config
AnyNect test browser

# Direct module invocation
python -m tests.test_config
python -m tests.test_browser           # also useful for re-login
python -m tests.test_markdown
python -m tests.test_commands
python -m tests.test_deepseek
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
  - Exit codes are recovered from the WebSocket close frame if the in‑band exit message is lost in transit, so `-1` placeholders are never reported for successful commands

### Chat History

- Persistent conversations stored in a local SQLite database.
- Sidebar with **rename**, **pin**, and **delete** for each chat.
- Reopening an old chat re‑navigates the browser to the saved DeepSeek URL.
- Titles are synced from the DeepSeek UI via the `chat_title` selector chain.
- Custom titles are preserved across syncs (`is_custom_name` flag).

### Task Queue

- Automatically appears when you send a message while the AI is busy.
- **Drag to reorder** – grab the handle (six dots) and drag.
- **Double‑click a task** to edit it.
- **Pause / Resume** – temporarily stop the queue from processing.
- **Cancel** – remove a task from the queue.
- Messages are queued while **any** command in the current group is still executing — not just while the AI is thinking. The queue drains exactly once, after the last command of the group finishes.

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
| **Chat history** | SQLite |
| **Logging** | Python `logging` with rotating file handler |
| **Dependency management** | `dependencies/` folder with split `base`, `dev`, `terminal` |
| **CLI** | `argparse` + setuptools console_scripts |

---

## 🗺️ Roadmap

- [x] Auto‑Allow queue for sequential command execution
- [x] Native terminal integration (configurable emulator)
- [x] Professional logging across all modules
- [x] CSS cleanup and UI polish
- [x] One‑command setup script (idempotent)
- [x] Moved tests into `tests/` directory
- [x] Global `AnyNect` command (with `AutoNect` alias) and configurable port
- [x] Configurable WebSocket output limit and terminal command
- [x] CSS selectors moved to external JSON file
- [x] AI response timeout and base URL configurable
- [x] **Chat history** – persistent conversations in SQLite with rename, pin, delete
- [x] Fixed SIGTERM self‑kill (`-15`) in PTY command executor
- [x] Fixed dropped exit codes when the WebSocket writer finishes first
- [x] Chat title sync from DeepSeek UI
- [x] Queue no longer bypasses during command execution
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