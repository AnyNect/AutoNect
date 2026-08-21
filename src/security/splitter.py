def split_commands(cmd: str) -> list[str]:
    """
    Split a shell command at `&&`, `||`, `;`, `&` (background), or newline,
    but NOT at `|` (pipe). Respects single and double quotes and escapes.
    Returns a list of stripped sub‑commands.
    """
    tokens = []
    current = []
    i = 0
    n = len(cmd)
    in_single = False
    in_double = False
    escape = False

    while i < n:
        c = cmd[i]
        if escape:
            current.append(c)
            escape = False
            i += 1
            continue
        if c == '\\':
            escape = True
            i += 1
            continue
        if in_single:
            current.append(c)
            if c == "'":
                in_single = False
            i += 1
            continue
        if in_double:
            current.append(c)
            if c == '"':
                in_double = False
            i += 1
            continue
        if c == "'":
            in_single = True
            current.append(c)
            i += 1
            continue
        if c == '"':
            in_double = True
            current.append(c)
            i += 1
            continue

        # Multi‑character operators: &&, ||
        if c == '&' and i + 1 < n and cmd[i + 1] == '&':
            if current:
                tokens.append(''.join(current).strip())
                current = []
            i += 2
            continue
        if c == '|' and i + 1 < n and cmd[i + 1] == '|':
            if current:
                tokens.append(''.join(current).strip())
                current = []
            i += 2
            continue

        # Single‑character separators: ;, & (background), \n
        if c == ';' or c == '&' or c == '\n':
            if current:
                tokens.append(''.join(current).strip())
                current = []
            i += 1
            continue

        # Note: we do NOT split on '|' (pipe)
        current.append(c)
        i += 1

    if current:
        tokens.append(''.join(current).strip())

    return [t for t in tokens if t]