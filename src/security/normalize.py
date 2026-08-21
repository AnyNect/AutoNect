import re

def normalize_command(raw: str) -> str:
    """Strip leading sudo/doas, absolute paths, and normalise spaces."""
    cmd = raw.strip()
    # Remove sudo / doas at the start
    cmd = re.sub(r'^(sudo|doas)\s+', '', cmd)
    # Remove absolute binary paths
    cmd = re.sub(r'^(/usr/bin/|/bin/|/usr/local/bin/)', '', cmd)
    # Normalise multiple spaces
    cmd = re.sub(r'\s+', ' ', cmd)
    # Normalise Unicode dashes to ASCII hyphens (U+2013 en-dash, U+2014 em-dash)
    cmd = cmd.replace('\u2013', '-').replace('\u2014', '-')
    cmd = cmd.replace('\u2013', '-').replace('\u2014', '-')
    return cmd

def strip_shell_quotes(text: str) -> str:
    """Remove surrounding shell quotes from individual tokens.

    Handles: "rm" -> rm, 'rm' -> rm, r"m" -> rm, r'm' -> rm, "-rf" -> -rf, etc.
    Also handles partial quotes: r"m" -> rm, -r"f" -> -rf.
    """
    # Remove r/R/b/B prefix before quotes (raw string prefix)
    # e.g., r"m" -> rm, R'm' -> Rm (prefix char + quoted content)
    result = re.sub(r'\b([rRbB])(["\x27])(.*?)(?:\2)', lambda m: m.group(1) + m.group(3), text)
    # Remove surrounding double quotes from tokens: "rm" -> rm
    result = re.sub(r'"([^"]*?)"', r'\1', result)
    # Remove surrounding single quotes from tokens: 'rm' -> rm  
    result = re.sub(r"'([^']*?)'", r'\1', result)
    return result

def remove_backslash_spaces(text: str) -> str:
    r"""Remove shell backslash-space escaping only: rm\ -rf\ -> rm -rf

    Does NOT touch \n, \t etc. — only \\ (backslash before space/end).
    """
    return re.sub(r'\\(?=\s|$)', '', text)
