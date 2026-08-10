class ShellCompositionDetector:
    """Quote-aware shell composition detection.

    Operators inside single quotes are completely ignored (they are
    literal). Operators inside double quotes are ignored UNLESS they
    are `$(` or backticks – those are still executed by the shell even
    inside double quotes. This avoids false positives on harmless
    commands like `echo "a && b"`.
    """

    OPERATORS = ['&&', '||', ';', '|', '$(', '`', '>', '>>', '<', '&', '\n']

    def has_composition(self, command: str) -> bool:
        cmd = command.strip()
        outside = self._strip_inert_quoted_text(cmd)
        return any(op in outside for op in self.OPERATORS)

    def _strip_inert_quoted_text(self, cmd: str) -> str:
        out = []
        i, n = 0, len(cmd)
        while i < n:
            c = cmd[i]
            if c == "'":
                j = cmd.find("'", i + 1)
                if j == -1:
                    # unterminated quote – keep the rest as-is (fail safe)
                    out.append(cmd[i:])
                    break
                i = j + 1
                continue
            if c == '"':
                j = i + 1
                while j < n and cmd[j] != '"':
                    if cmd[j] == '\\' and j + 1 < n:
                        j += 2
                        continue
                    j += 1
                inner = cmd[i + 1:j]
                # $() and backticks are still live inside double quotes
                if '$(' in inner or '`' in inner:
                    out.append(inner)
                if j >= n:
                    out.append(cmd[i:])
                    break
                i = j + 1
                continue
            out.append(c)
            i += 1
        return ''.join(out)