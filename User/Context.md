# AI Context – Persistent Chat Log

This file is for the AI to record important information, decisions, and context that should persist across chat sessions.

---
*(Start of log – entries will be appended here by the AI as needed.)*

---
### 2026-08-29 – User folder structure finalized

- Created `User/` folder with professional notes system:
  - `README.md` – overview
  - `Context.md` – persistent AI log (this file)
  - `User.md` – user profile & permissions
  - `Guidelines.md` – AI instructions (shell safety, efficiency)
  - `Journal.md` – mistakes & happy moments
  - `Plans.md` – user goals & roadmap
- The original `USER.md` is kept untouched as a reference.
- Old `user_notes/` folder has been removed after content migration.

Next steps: Populate `User.md` (name, preferences) and `Plans.md` with initial goals.

---
### 2026-08-29 – Squibview integration reverted

- Integrated Squibview on branch `feature/squibview-AI` (commits `a8a2166`, `f57b00c`, `d1f9a26`).
- It **did not render** correctly – likely due to browser cache or CDN issues.
- The branch has been **reset** to `eb70113` (`AutoNect-AI` state) and force-pushed.
- The `User/` folder remains intact. 
- **Lesson:** Always test thoroughly before committing; and **ask permission before any commit/push**.

---
### 2026-08-30 – System prompts fully dynamic

- Modified `src/prompts/system.txt` and `src/prompts/system_restricted.txt` to remove hardcoded references to CachyOS and Konsole.
- Added a runtime environment detection block to be executed at the start of each session, capturing OS, kernel, shell, terminal emulator, package manager, etc.
- The AI now adapts its terminal commands (e.g., pop-up windows) based on detected `TERMINAL_EMULATOR`, `SHELL`, etc.
- Backups of the old files were created as `*.bak` in the same directory.
- Task logged in `Plans.md` as `[x]` complete.

- **Refinement:** Made environment detection mandatory at session start (not just recommended).

- **Final solution:** System prompts are now auto-generated at startup with actual environment values embedded.

- **Additional environment details added:** Python, Node, Docker, Git versions; editor, browser, timezone, Git user/email.

- **Removed Git user/email from prompts; improved editor/browser detection** (now checks PATH).

- **Browser detection fixed:** now prioritises `thorium-browser` (installed binary).

- **Editor default changed:** prioritises `code` (VS Code) over vim.

- **Editor fallback:** added `kate` as second choice after `code`.
