"""
Resolves decode‑then‑transform pipelines that wrap a final payload.

Used to determine if a command like
    eval "$(echo ... | base64 -d | sed 's/^/echo "Dry run: /; s/$/"/')"
actually executes `rm -rf` or just an `echo` statement.
"""
import re
from .decoder import decode_obfuscated

SAFE_DISPLAY_CMDS = ('echo', 'printf')

def apply_sed_substitutions(text: str, sed_script: str) -> str | None:
    """Apply a small, understood subset of sed 's/.../.../' commands.
    Returns None if the script uses anything we don't model.
    """
    commands = [c.strip() for c in sed_script.split(';') if c.strip()]
    if not commands:
        return None
    result = text
    for c in commands:
        m = re.match(r'^s(.)(.*)$', c, re.DOTALL)
        if not m:
            return None
        delim = m.group(1)
        parts = m.group(2).split(delim)
        if len(parts) < 2:
            return None
        pattern, replacement = parts[0], parts[1]
        if pattern == '^':
            result = replacement + result
        elif pattern == '$':
            result = result + replacement
        elif pattern in ('.*', '^.*$'):
            result = replacement.replace('&', result)
        else:
            return None
    return result

def is_inert_echo_statement(cmd: str) -> bool:
    """True if `cmd` is just an echo/printf of literal text."""
    s = cmd.strip()
    m = re.match(r'^(echo|printf)\b(\s+-[a-zA-Z]+)?\s*', s)
    if not m:
        return False
    rest = s[m.end():]
    if rest.strip() == '':
        return True
    i, n = 0, len(rest)
    saw_any_arg = False
    while i < n:
        c = rest[i]
        if c.isspace():
            i += 1
            continue
        if c == "'":
            j = rest.find("'", i + 1)
            if j == -1:
                return False
            saw_any_arg = True
            i = j + 1
            continue
        if c == '"':
            j = i + 1
            while j < n and rest[j] != '"':
                if rest[j] == '\\' and j + 1 < n:
                    j += 2
                    continue
                j += 1
            if j >= n:
                return False
            inner = rest[i + 1:j]
            if '$(' in inner or '`' in inner or '$' in inner:
                return False
            saw_any_arg = True
            i = j + 1
            continue
        # any unquoted non‑space char – cannot prove inertness
        return False
    return saw_any_arg

def resolve_whole_command_wrapper(raw_cmd: str) -> tuple[bool, str | None]:
    """
    Handle the narrow shape:
        eval "$( <pipeline> )"
        sh -c "$( <pipeline> )"
        bash -c "$(<pipeline>)"
    with nothing else outside.

    Returns (resolved, final_text):
      (True, text)  – fully resolved final payload
      (False, None) – could not resolve; caller must not assume safety
    """
    m = re.match(
        r'^(?:eval|sh\s+-c|bash\s+-c)\s+"\$\((.*)\)"\s*$',
        raw_cmd.strip(), re.DOTALL
    )
    if not m:
        return False, None
    inner = m.group(1)

    sed_m = re.search(r"\|\s*sed\s+(['\"])(.*)\1\s*$", inner, re.DOTALL)
    if sed_m:
        pre = inner[:sed_m.start()]
        sed_script = sed_m.group(2)
        decoded = decode_obfuscated(pre)
        if decoded is None:
            return False, None
        transformed = apply_sed_substitutions(decoded, sed_script)
        if transformed is None:
            return False, None
        return True, transformed

    decoded = decode_obfuscated(inner)
    if decoded is None:
        return False, None
    return True, decoded