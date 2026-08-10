import re
import base64

def decode_printf_hex(command: str) -> str | None:
    match = re.search(r'printf\s+(["\'])((?:\\x[0-9a-fA-F]{2}\s*)+)\1', command, re.DOTALL)
    if match:
        hex_str = match.group(2)
        try:
            hex_pairs = re.findall(r'\\x([0-9a-fA-F]{2})', hex_str)
            return bytes(int(h, 16) for h in hex_pairs).decode('utf-8', errors='replace')
        except Exception:
            return None
    return None

def decode_printf_octal(command: str) -> str | None:
    match = re.search(r'printf\s+(["\'])((?:\\[0-7]{3}\s*)+)\1', command, re.DOTALL)
    if match:
        octal_str = match.group(2)
        try:
            octal_pairs = re.findall(r'\\([0-7]{3})', octal_str)
            return bytes(int(o, 8) for o in octal_pairs).decode('utf-8', errors='replace')
        except Exception:
            return None
    return None

def decode_printf_raw_hex_piped_to_xxd(command: str) -> str | None:
    # printf "%s" "<hexdigits>" | xxd -r -p
    match = re.search(
        r'printf\s+(["\'])%s\1\s+(["\'])([0-9a-fA-F]+)\2\s*\|\s*xxd\s+-(?:r\s+-p|p\s+-r)',
        command
    )
    if match:
        try:
            return bytes.fromhex(match.group(3)).decode('utf-8', errors='replace')
        except Exception:
            return None
    return None

def decode_base64(command: str) -> str | None:
    match = re.search(r'echo\s+(["\'])([A-Za-z0-9+/=]+)\1\s*\|\s*base64\s+-d', command)
    if match:
        try:
            return base64.b64decode(match.group(2)).decode('utf-8', errors='replace')
        except Exception:
            return None
    match = re.search(r'base64\s+-d\s+<<<\s*(["\']?)([A-Za-z0-9+/=]+)\1', command)
    if match:
        try:
            return base64.b64decode(match.group(2)).decode('utf-8', errors='replace')
        except Exception:
            return None
    return None

def decode_perl_printf(command: str) -> str | None:
    match = re.search(r"perl\s+-e\s+'print\s+([\"'])((?:\\x[0-9a-fA-F]{2}\s*)+)\1'", command, re.DOTALL)
    if match:
        hex_str = match.group(2)
        try:
            hex_pairs = re.findall(r'\\x([0-9a-fA-F]{2})', hex_str)
            return bytes(int(h, 16) for h in hex_pairs).decode('utf-8', errors='replace')
        except Exception:
            return None
    match = re.search(r"perl\s+-e\s+'print\s+([\"'])((?:\\[0-7]{3}\s*)+)\1'", command, re.DOTALL)
    if match:
        octal_str = match.group(2)
        try:
            octal_pairs = re.findall(r'\\([0-7]{3})', octal_str)
            return bytes(int(o, 8) for o in octal_pairs).decode('utf-8', errors='replace')
        except Exception:
            return None
    return None

def decode_perl_pack(command: str) -> str | None:
    match = re.search(
        r"perl\s+-e\s+['\"]print\s+pack\s*\(\s*['\"]H\*['\"]\s*,\s*['\"]([0-9a-fA-F]+)['\"]\s*\)['\"]",
        command
    )
    if match:
        try:
            return bytes.fromhex(match.group(1)).decode('utf-8', errors='replace')
        except Exception:
            return None
    return None

def decode_xxd_hex(command: str) -> str | None:
    # echo "<hex>" | xxd -r -p
    match = re.search(
        r'echo\s+(["\'])([0-9a-fA-F]+)\1\s*\|\s*xxd\s+-(?:r\s+-p|p\s+-r)',
        command
    )
    if match:
        try:
            return bytes.fromhex(match.group(2)).decode('utf-8', errors='replace')
        except Exception:
            return None
    # xxd -r -p <<< <hex>
    match = re.search(
        r'xxd\s+-(?:r\s+-p|p\s+-r)\s*<<<\s*(["\']?)([0-9a-fA-F]+)\1',
        command
    )
    if match:
        try:
            return bytes.fromhex(match.group(2)).decode('utf-8', errors='replace')
        except Exception:
            return None
    return None

def decode_echo_escapes(command: str) -> str | None:
    match = re.search(r"echo\s+-e\s+([\"'])(.*?)\1", command, re.DOTALL)
    if match:
        escaped_str = match.group(2)
        try:
            def replace_octal(m):
                return chr(int(m.group(1), 8))
            decoded = re.sub(r'\\([0-7]{3})', replace_octal, escaped_str)
            def replace_hex(m):
                return chr(int(m.group(1), 16))
            decoded = re.sub(r'\\x([0-9a-fA-F]{2})', replace_hex, decoded)
            return decoded.encode('latin-1').decode('utf-8', errors='replace')
        except Exception:
            return None
    return None

def decode_eval_substitution(command: str) -> str | None:
    match = re.search(r'(?:eval|bash\s+-c|sh\s+-c)\s+(["\'])?\$\(([^)]+)\)(?(1)\1)', command)
    if match:
        inner = match.group(2)
        decoded = decode_obfuscated(inner)
        if decoded:
            return decoded
    return None

def decode_obfuscated(command: str) -> str | None:
    for decoder in [
        decode_printf_hex,
        decode_printf_octal,
        decode_printf_raw_hex_piped_to_xxd,
        decode_base64,
        decode_perl_printf,
        decode_perl_pack,
        decode_xxd_hex,
        decode_echo_escapes,
        decode_eval_substitution,
    ]:
        result = decoder(command)
        if result:
            return result
    return None