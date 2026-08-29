# AI Guidelines

## Shell Safety

- When writing `.md` files or any content with backticks, use `cat << 'EOF'` (single quotes) or single-quoted strings.
- Never use `echo` with double quotes when content includes backticks or `$`.

## Efficiency Tips

- To write a file with backticks (```), use `printf '%s\n' "line1" "line2" ... > file` or write with Python to avoid shell interpretation.
- Do NOT use `cat << 'EOF'` with backticks inside; it will break.
- Prefer Python for writing any file containing code blocks.

## General Instructions

- Always read `User/Context.md` at the start of a conversation to maintain context.
- Append important decisions, discoveries, or user feedback to `Context.md` as they occur.
- Follow the permissions and guidelines strictly.
