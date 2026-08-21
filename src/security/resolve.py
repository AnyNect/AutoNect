import re
import ast
from .decoder import decode_obfuscated

def apply_sed_substitutions(text: str, sed_script: str) -> str | None:
    """Apply a small subset of sed 's/.../.../' commands."""
    commands = [c.strip() for c in sed_script.split(';') if c.strip()]
    if not commands:
        return None
    result = text
    for c in commands:
        if not c.startswith('s'):
            return None
        delim = c[1]
        parts = c[2:].split(delim)
        if len(parts) < 3:
            return None
        pattern = parts[0]
        replacement = parts[1]
        if pattern == '^':
            result = replacement + result
        elif pattern == '$':
            result = result + replacement
        elif pattern in ('.*', '^.*$'):
            result = replacement.replace('&', result)
        else:
            return None
    return result

def extract_inside_parentheses(text: str, start_delim: str = '(', end_delim: str = ')') -> str | None:
    """Extract content inside matching parentheses, respecting nesting."""
    s = text.strip()
    start_idx = s.find(start_delim)
    if start_idx == -1:
        return None
    depth = 0
    i = start_idx + 1
    n = len(s)
    while i < n:
        if s[i] == start_delim:
            depth += 1
        elif s[i] == end_delim:
            if depth == 0:
                return s[start_idx+1:i].strip()
            depth -= 1
        i += 1
    return None

def decode_ansi_c(text: str) -> str:
    """Decode bash ANSI C string quoting like $'\\162\\155' -> 'rm'."""
    def replace(match):
        inner = match.group(1)
        try:
            b_str = ast.literal_eval("b'" + inner.replace("'", "\\'") + "'")
            return b_str.decode('utf-8', 'ignore')
        except Exception:
            return match.group(0)
    return re.sub(r"\$'(.*?)'", replace, text)

def inline_variables(text: str) -> str:
    """Attempt to resolve basic variable assignments inline."""
    lines = re.split(r';|\n', text)
    env = {}
    out = []
    for line in lines:
        line = line.strip()
        if not line: continue
        
        assign_match = re.match(r'^(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)=("[^"]*"|\'[^\']*\'|\S+)$', line)
        if assign_match:
            var_name = assign_match.group(1)
            val = assign_match.group(2)
            if val.startswith('"') and val.endswith('"'): val = val[1:-1]
            elif val.startswith("'") and val.endswith("'"): val = val[1:-1]
            env[var_name] = val
            continue
        
        for _ in range(3):
            line = re.sub(r'\$\{([A-Za-z_][A-Za-z0-9_]*)\}', lambda m: env.get(m.group(1), m.group(0)), line)
            line = re.sub(r'\$([A-Za-z_][A-Za-z0-9_]*)\b', lambda m: env.get(m.group(1), m.group(0)), line)
        out.append(line)
    return " ; ".join(out)

def inline_aliases(text: str) -> str:
    """Resolve bash aliases inline."""
    lines = re.split(r';|\n', text)
    aliases = {}
    out = []
    for line in lines:
        line = line.strip()
        alias_match = re.match(r"^alias\s+([A-Za-z0-9_]+)=['\"]?(.*?)['\"]?$", line)
        if alias_match:
            aliases[alias_match.group(1)] = alias_match.group(2)
            continue
        
        for k, v in aliases.items():
            line = re.sub(r'\b' + re.escape(k) + r'\b', v, line)
        out.append(line)
    return " ; ".join(out)

def inline_env_vars(text: str) -> str:
    """Resolves inline env assignments like: env CMD="rm -rf" sh -c '$CMD'
    
    Now handles multiple env assignments and sudo env.
    """
    # Strip leading sudo
    stripped = re.sub(r'^(?:sudo\s+)?', '', text)
    
    # Match one or more VAR=VALUE assignments
    prefix = r'^env\s+'
    rest_after_env = stripped
    var_vals = {}
    
    # Match: env VAR1=VAL1 VAR2="VAL2" ... command
    m = re.match(prefix + r'((?:[A-Za-z_][A-Za-z0-9_]*=(?:"[^"]*"|\'[^\']*\'|[^\s]+)\s*)+)(.*)', stripped)
    if m:
        assignments_str = m.group(1)
        rest = m.group(2)
        # Parse individual assignments
        for am in re.finditer(r'([A-Za-z_][A-Za-z0-9_]*)=("[^"]*"|\'[^\']*\'|[^\s]+)', assignments_str):
            var, val = am.group(1), am.group(2)
            if val.startswith('"') and val.endswith('"'): val = val[1:-1]
            elif val.startswith("'") and val.endswith("'"): val = val[1:-1]
            var_vals[var] = val
        # Substitute variables in rest
        for var, val in var_vals.items():
            rest = rest.replace(f'${{{var}}}', val)
            rest = rest.replace(f'${var}', val)
        return rest
    
    return text

def is_inert_echo_statement(cmd: str) -> bool:
    """Check if a command is a simple, inert echo/print statement with no subshells or risky redirects."""
    s = cmd.strip()
    if not (s.startswith('echo ') or s.startswith('printf ') or s == 'echo' or s == 'printf'):
        return False
    if '$(' in s or '`' in s or '>' in s or '<' in s or ';' in s or '|' in s or '&' in s:
        return False
    # Reject printf/echo that contains IFS manipulation or variable construction
    if '${IFS}' in s:
        return False
    # Reject if it looks like it's building a command (has rm, chmod, etc.)
    if re.search(r'\brm\b|\bchmod\b|\bsh\b|\bbash\b', s):
        return False
    return True

def resolve_whole_command_wrapper(raw_cmd: str, depth: int = 0) -> tuple[bool, str | None]:
    """Handle eval, subshells, aliases, variables, ANSI strings, and heredocs with strict depth guard."""
    if depth > 5:
        return False, None

    s = raw_cmd.strip()
    original_s = s  # Remember original before decoding
    
    # Decode ANSI-C quoting first
    decoded_ansi = decode_ansi_c(s)
    if decoded_ansi != s:
        # FIX: If ANSI decoding produced a dangerous command, return it for evaluation
        if re.search(r'rm\s+-rf|rm\s+--', decoded_ansi, re.IGNORECASE):
            return True, decoded_ansi
        s = decoded_ansi
    
    s = inline_env_vars(s)
    s = inline_aliases(inline_variables(s))

    # Heredoc: << ...  (only full script bodies, not <<< here-strings)
    m_hd = re.search(r'<<\s*(-?)[\'"]?([A-Za-z0-9_]+)[\'"]?\s*\n(.*?)\n\2', s, re.DOTALL)
    if m_hd:
        return True, m_hd.group(3)

    inner = None

    # FIX: Expanded prefix match to include sudo env, env, and sudo with various env prefixes
    m = re.match(r'^(?:(?:sudo\s+)?(?:env\s+-?[iu]\s+\S+\s+)*)?(?:eval|sh\s+-c|bash\s+-c|zsh\s+-c|sudo\s+sh\s+-c|sudo\s+bash\s+-c|command\s+sh\s+-c)\s+', s)
    if m:
        rest = s[m.end():].strip()
        if (rest.startswith('"$(') and rest.endswith(')"')) or (rest.startswith("'$(") and rest.endswith(")'")):
            inner = rest[3:-2].strip()
        elif rest.startswith('$(') and rest.endswith(')'):
            inner = rest[2:-1].strip()
        elif rest.startswith('"') and rest.endswith('"'):
            inner = rest[1:-1].strip()
        elif rest.startswith("'") and rest.endswith("'"):
            inner = rest[1:-1].strip()
        else:
            inner = rest
    
    elif s.startswith('$(') and s.endswith(')'):
        inner = s[2:-1].strip()
        
    elif s.startswith('(') and s.endswith(')'):
        extracted = extract_inside_parentheses(s)
        if extracted is not None:
            inner = extracted

    # Only extract subshells if the whole command is exactly that subshell (no extra tokens)
    if inner is None:
        # If the whole command is exactly $(...) or `...`
        if re.match(r'^\$\(.*\)$', s):
            return True, s[2:-1].strip()
        if re.match(r'^`.*`$', s):
            return True, s[1:-1].strip()

    target = inner if inner is not None else s
    
    sed_m = re.search(r"\|\s*sed\s+(['\"])(.*)\1\s*$", target, re.DOTALL)
    if sed_m:
        pre = target[:sed_m.start()]
        sed_script = sed_m.group(2)
        decoded = decode_obfuscated(pre)
        if decoded is not None:
            transformed = apply_sed_substitutions(decoded, sed_script)
            if transformed is not None:
                return True, transformed

    decoded = decode_obfuscated(target)
    if decoded is not None and decoded != target:
        # Don't use partial decode that lost significant command content
        # (e.g., decoded only the first printf in a multi-command string)
        if len(decoded) < len(target) * 0.4:
            pass  # Fall through, let the command be split and evaluated normally
        else:
            return True, decoded

    # FIX: Flag normalization — reorder flags to front while preserving paths.
    # Only normalize when flags are already consolidated (not split around paths).
    # Split-flag cases (rm PATH -rf, rm --recursive PATH --force) are caught by pack patterns.
    norm_rm = None
    # Only normalize when -rf (or equivalent) appears before any path-like argument
    m_flags = re.match(r'(\brm\b\s+.*?-[rfRF]+)', target)
    if m_flags and '~' not in m_flags.group(1) and '$HOME' not in m_flags.group(1):
        # Flags are before any home path — safe to normalize
        norm_rm = re.sub(
            r'\brm\b\s+(?:.*?)(-[rfRF]+)',
            'rm -rf ',
            target,
            count=1
        )
    # Also handle: rm -rf -- ... → already has --, keep it
    norm_rm2 = re.sub(
        r'\brm\b\s+-[rfRF]+\s+--\s+',
        'rm -rf -- ',
        target
    )
    if norm_rm2 != target:
        if re.sub(r'\s+', ' ', norm_rm2).strip() == re.sub(r'\s+', ' ', target).strip():
            pass  # whitespace only changed, fall through to other patterns
        else:
            return True, norm_rm2

    if norm_rm and norm_rm != target:
        stripped_norm = re.sub(r'\s+', ' ', norm_rm).strip()
        stripped_orig = re.sub(r'\s+', ' ', target).strip()
        if stripped_norm == stripped_orig:
            return False, None  # whitespace only changed
        # Don't return if normalization lost all path args
        if re.match(r'^rm\s+-rf\s*$', stripped_norm, re.IGNORECASE):
            return False, None
        return True, norm_rm

    if target != raw_cmd.strip():
        is_wrapped, deeper_target = resolve_whole_command_wrapper(target, depth + 1)
        if is_wrapped:
            return True, deeper_target
        return True, target

    return False, None