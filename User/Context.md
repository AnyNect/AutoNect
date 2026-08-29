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
