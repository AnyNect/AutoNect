class ShellCompositionDetector:
    """Quote‑aware shell composition detection with here‑string stripping."""

    OPERATORS = ['&&', '||', ';', '|', '$(', '`', '>', '>>', '<', '&', '\n']

    def has_composition(self, command: str) -> bool:
        cmd = command.strip()
        outside = self.strip_quoted_text(cmd)
        return any(op in outside for op in self.OPERATORS)

    def strip_quoted_text(self, cmd: str) -> str:
        """Remove quoted text and here‑string content."""
        out = []
        i, n = 0, len(cmd)
        while i < n:
            c = cmd[i]

            # Single quotes
            if c == "'":
                j = cmd.find("'", i + 1)
                if j == -1:
                    out.append(cmd[i:])
                    break
                i = j + 1
                continue

            # Double quotes
            if c == '"':
                j = i + 1
                while j < n and cmd[j] != '"':
                    if cmd[j] == '\\' and j + 1 < n:
                        j += 2
                        continue
                    j += 1
                inner = cmd[i + 1:j]
                if '$(' in inner or '`' in inner:
                    out.append(inner)
                if j >= n:
                    out.append(cmd[i:])
                    break
                i = j + 1
                continue

            # Here‑string: <<< followed by quoted or unquoted token
            if c == '<' and i + 2 < n and cmd[i+1] == '<' and cmd[i+2] == '<':
                i += 3
                # Skip whitespace
                while i < n and cmd[i].isspace():
                    i += 1
                # If quoted, skip the quoted string entirely
                if i < n and cmd[i] == "'":
                    j = cmd.find("'", i + 1)
                    if j != -1:
                        i = j + 1
                        continue
                elif i < n and cmd[i] == '"':
                    j = i + 1
                    while j < n and cmd[j] != '"':
                        if cmd[j] == '\\' and j + 1 < n:
                            j += 2
                            continue
                        j += 1
                    if j < n:
                        i = j + 1
                        continue
                # If not quoted, skip the token (space‑separated)
                while i < n and not cmd[i].isspace():
                    i += 1
                continue

            out.append(c)
            i += 1

        return ''.join(out)