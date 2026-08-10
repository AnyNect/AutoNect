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
    return cmd