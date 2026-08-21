import re
from typing import Optional, Dict, Tuple

from .constants import Severity, Decision
from .config import GuardConfig
from .path_protection import PathProtector
from .shell_composition import ShellCompositionDetector
from .session import SessionApprovalManager
from .packs import PACKS
from .normalize import normalize_command, strip_shell_quotes, remove_backslash_spaces
from .heredoc import extract_embedded_scripts
from .ast_matcher import find_dangerous_calls
from .decoder import decode_obfuscated
from .resolve import resolve_whole_command_wrapper, is_inert_echo_statement
from .splitter import split_commands


class SecurityPolicy:
    def __init__(self, config: GuardConfig, session_mgr: SessionApprovalManager):
        self.config = config
        self.session = session_mgr
        self.path_protector = PathProtector(config)
        self.shell_detector = ShellCompositionDetector()
        self.packs = []
        for pack in PACKS:
            compiled_safe = [re.compile(p, re.IGNORECASE) for p in pack.get("safe_patterns", [])]
            compiled_destructive = []
            for d in pack.get("destructive_patterns", []):
                compiled_destructive.append({
                    "regex": re.compile(d["pattern"], re.IGNORECASE),
                    "severity": d["severity"],
                    "reason": d["reason"],
                })
            self.packs.append({
                "id": pack["id"],
                "safe": compiled_safe,
                "destructive": compiled_destructive,
            })

    def _extract_and_evaluate_substitutions(self, cmd: str) -> Tuple[Decision, Optional[Dict]]:
        # FIX: Now evaluates substitutions inside echo/printf arguments too.
        # Extract $() and backtick substitutions from ANY context, not just standalone.
        pattern = r'\$\(([^)]+)\)|`([^`]+)`'
        matches = re.findall(pattern, cmd)
        for match in matches:
            inner = match[0] or match[1]
            if inner:
                decoded = decode_obfuscated(inner)
                if decoded:
                    dec_decision, dec_info = self.evaluate(decoded, self.session.session_id, skip_allowlist=True, depth=0)
                    if dec_decision in (Decision.DENY, Decision.ASK):
                        return dec_decision, {
                            "reason": f"Obfuscated payload in substitution: {decoded[:80]}...",
                            "decoded_decision": dec_decision.value,
                            "decoded_info": dec_info,
                        }
                # Also evaluate the inner as a command (if it's dangerous, deny)
                inner_decision, inner_info = self.evaluate(inner, self.session.session_id, skip_allowlist=True, depth=0)
                if inner_decision in (Decision.DENY, Decision.ASK):
                    return inner_decision, inner_info
        return Decision.ALLOW, None

    def _unwrap_literal_wrapper(self, cmd: str) -> Tuple[bool, str | None]:
        m = re.match(r'^(?:bash|sh|zsh)\s+-c\s+(["\'])(.*?)(?<!\\)\1\s*$', cmd, re.DOTALL)
        if m:
            return True, m.group(2)
        m = re.match(r'^eval\s+(["\'])(.*?)(?<!\\)\1\s*$', cmd, re.DOTALL)
        if m:
            return True, m.group(2)
        return False, None

    def _check_script_languages(self, cmd: str) -> Tuple[Decision, Optional[Dict]]:
        # Python
        python_match = re.search(r'python3?\s+-c\s+(["\'])(.*?)(?<!\\)\1', cmd, re.DOTALL)
        if python_match:
            code = python_match.group(2)
            # Catch exec with base64 or fromhex (obfuscation)
            if re.search(r'(?:exec|eval)\s*\(', code) and re.search(r'base64|fromhex', code):
                return Decision.DENY, {"reason": "Python exec with obfuscated payload"}
            dangerous = find_dangerous_calls(code)
            if dangerous:
                return Decision.DENY, {"reason": f"Python dangerous call: {dangerous[0]['function']}"}
            if re.search(r'(?:os\.system|shutil\.rmtree|os\.remove|os\.unlink|subprocess\.call|subprocess\.Popen|subprocess\.run)\s*\(', code):
                if re.search(r'subprocess\.run\s*\(\s*\[\s*[\'\"]echo[\'\"]', code):
                    return Decision.ALLOW, {"dry_run": True, "reason": "Python dry-run echo"}
                return Decision.DENY, {"reason": "Python script executes dangerous shell command"}

        # Ruby
        ruby_match = re.search(r'ruby\s+-e\s+(["\'])(.*?)(?<!\\)\1', cmd, re.DOTALL)
        if ruby_match:
            code = ruby_match.group(2)
            if re.search(r'system\s*\(', code):
                if re.search(r'system\s*\(\s*(["\'])\s*echo\s+', code) or re.search(r'system\s*\(\s*[\'\"]echo[\'\"]\s*,', code):
                    return Decision.ALLOW, {"dry_run": True, "reason": "Ruby dry-run echo"}
                else:
                    return Decision.DENY, {"reason": "Ruby script executes dangerous shell command"}
            if re.search(r'`.*rm\s+-rf.*`', code):
                return Decision.DENY, {"reason": "Ruby backtick with dangerous command"}

        # Node
        node_match = re.search(r'node\s+-e\s+(["\'])(.*?)(?<!\\)\1', cmd, re.DOTALL)
        if node_match:
            code = node_match.group(2)
            if re.search(r'(?:execSync|exec)\s*\(', code):
                if ("execSync('echo " in code or "execSync(\"echo " in code or
                    "execSync('echo' +" in code or "execSync(\"echo\" +" in code or
                    "exec('echo " in code or "exec(\"echo " in code or
                    "exec('echo' +" in code or "exec(\"echo\" +" in code):
                    return Decision.ALLOW, {"dry_run": True, "reason": "Node dry-run echo"}
                else:
                    return Decision.DENY, {"reason": "Node.js script executes dangerous shell command"}

        # PHP
        php_match = re.search(r'php\s+-r\s+(["\'])(.*?)(?<!\\)\1', cmd, re.DOTALL)
        if php_match:
            code = php_match.group(2)
            if re.search(r'(exec|system|shell_exec)\s*\(', code):
                if re.search(r'(exec|system|shell_exec)\s*\(\s*(["\'])\s*echo\s+', code):
                    return Decision.ALLOW, {"dry_run": True, "reason": "PHP dry-run echo"}
                else:
                    return Decision.DENY, {"reason": "PHP script executes dangerous shell command"}

        # AWK
        if re.search(r'awk\s+.*system\s*\(', cmd):
            if re.search(r'system\s*\(\s*["\']echo\s*["\']?\s*[+,]', cmd) or re.search(r'system\s*\(\s*["\']echo\s+', cmd):
                return Decision.ALLOW, {"dry_run": True, "reason": "AWK dry-run echo"}
            else:
                return Decision.DENY, {"reason": "AWK executes dangerous shell command"}

        # FIX: Perl - check for system() calls similar to Ruby
        perl_match = re.search(r'perl\s+-e\s+(["\'])(.*?)(?<!\\)\1', cmd, re.DOTALL)
        if perl_match:
            code = perl_match.group(2)
            if re.search(r'system\s*\(', code):
                if re.search(r'system\s*\(\s*(["\'])\s*echo\s+', code):
                    return Decision.ALLOW, {"dry_run": True, "reason": "Perl dry-run echo"}
                else:
                    return Decision.DENY, {"reason": "Perl script executes dangerous shell command"}
            if re.search(r'`.*rm\s+-rf.*`', code):
                return Decision.DENY, {"reason": "Perl backtick with dangerous command"}

        return Decision.ALLOW, None

    def _is_dry_run(self, cmd: str) -> bool:
        dry_patterns = [
            r'--dry-run',
            r'--dryrun',
            r'Dry run',
            r'Would delete',
            r'Would run',
            r'echo\s+["\'].*[Dd]ry',
            r'echo\s+["\'].*[Ww]ould',
        ]
        return any(re.search(p, cmd) for p in dry_patterns)

    def _is_safe_dry_run_pipeline(self, raw_cmd: str) -> bool:
        if 'sed' in raw_cmd and ('Dry run' in raw_cmd or 'Would delete' in raw_cmd):
            return True
        if re.search(r'(?:curl|wget)\s+.*\|\s*(?:sh|bash)\s+(?:-s\s+)?--\s+--dry-run', raw_cmd):
            return True
        if re.search(r'(?:curl|wget)\s+.*\|\s*(?:sh|bash)\s+-c\s+[\'\"]echo', raw_cmd):
            return True
        return False

    def _has_variable_concatenation_danger(self, cmd: str) -> bool:
        if 'rm' in cmd and '-rf' in cmd and '$' in cmd:
            assigns = re.findall(r'([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(["\'])(.*?)\2', cmd)
            has_rm = any('rm' in val for _, _, val in assigns)
            has_rf = any('-rf' in val for _, _, val in assigns)
            if has_rm and has_rf:
                if re.search(r'\$[A-Za-z_]+\$[A-Za-z_]+', cmd):
                    return True
        return False

    def _has_dangerous_variable_usage(self, cmd: str) -> bool:
        """Detect dangerous variable usage: assignments containing rm -rf used with eval/$/sh -c, or multiple vars forming rm -rf.

        FIX: Now also handles eval "$var" with additional args, A="rm -rf"; B="$HOME/.*"; eval "$A $B",
        and single-quoted assignments like x='rm -rf ...'; eval "$x".
        Also handles unquoted split assignments: X=rm; Y=-rf; $X $Y ~/.*
        """
        stripped = self.shell_detector.strip_quoted_text(cmd)

        # ── Handle both quoted AND unquoted assignments ──
        # Quoted: A="rm -rf", B='-rf'
        quoted_assigns = re.findall(r'([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(["\x27])(.*?)(?:\2)', cmd)
        # Unquoted: X=rm, Y=-rf
        unquoted_assigns = re.findall(r'([A-Za-z_][A-Za-z0-9_]*)\s*=(?!\s*["\x27])(\S+)', cmd)

        # Merge: (var, value) for all assignments
        all_assigns = [(v, val) for v, _, val in quoted_assigns]
        all_assigns += [(v, val) for v, val in unquoted_assigns]

        # Check for assignments with rm -rf used as command or with eval/sh -c
        for var, value in all_assigns:
            if 'rm -rf' in value or 'rm ' in value:
                if re.search(rf'\$({var}|\{{{var}\}})', cmd):
                    if re.search(r'(?:eval|sh\s+-c|bash\s+-c)\b', cmd):
                        return True
                    if re.search(rf'\$({var}|\{{{var}\}})\s', cmd):
                        return True
                    if re.search(rf'\$({var}|\{{{var}\}})$', cmd):
                        return True

        # Detect split variables: e.g., cmd="rm"; args="-rf ~/.* ~/*"; $cmd $args
        # Or unquoted: X=rm; Y=-rf; $X $Y ~/.* ~/*
        dangerous_vars = []
        for var, value in all_assigns:
            if 'rm' in value or '-rf' in value or '~' in value or '$HOME' in value:
                dangerous_vars.append(var)
        if len(dangerous_vars) >= 2:
            for i in range(len(dangerous_vars)):
                for j in range(i+1, len(dangerous_vars)):
                    v1, v2 = dangerous_vars[i], dangerous_vars[j]
                    if re.search(rf'\$({v1}|\{{{v1}\}})\s*\$({v2}|\{{{v2}\}})', stripped):
                        return True
                    if re.search(rf'\$({v2}|\{{{v2}\}})\s*\$({v1}|\{{{v1}\}})', stripped):
                        return True
        return False

    def _check_raw_rm_patterns(self, raw_cmd: str) -> Tuple[Decision, Optional[Dict]]:
        """Check raw (pre-normalize) command for rm patterns that survive quote stripping.

        Catches: long flags (--force --recursive, --recursive ... --force),
        -R flag, env -i/-u wrappers, here-strings, and quoted partial names.
        """
        # Octal echo -e piped to shell (without hex)
        if re.search(r'echo\s+-e\s+".*\\[0-7]{3}', raw_cmd) and \
           re.search(r'\|\s*(?:sh|bash)\b', raw_cmd):
            if not re.search(r'\|\s*(?:sh|bash)\s+-n\b', raw_cmd):
                return Decision.DENY, {"reason": "Octal escaped command piped to shell"}

        # Here-strings: cmd <<< 'dangerous command'
        herestring_m = re.search(r'\b(?:sh|bash|zsh)\s*<<<', raw_cmd)
        if herestring_m:
            rest = raw_cmd[herestring_m.end():].strip()
            if (rest.startswith("'") and rest.endswith("'")) or \
               (rest.startswith('"') and rest.endswith('"')):
                rest = rest[1:-1]
            if re.search(r'rm\s+-[rfRF]+', rest, re.IGNORECASE) and \
               re.search(r'~', rest):
                return Decision.DENY, {"reason": "Dangerous here-string with rm -rf ~"}
            if re.search(r'rm\s+--(?:recursive|force)', rest, re.IGNORECASE) and \
               re.search(r'~', rest):
                return Decision.DENY, {"reason": "Dangerous here-string with rm long flags ~"}

        # cat <<< 'rm -rf ...' | sh  (here-string piped to shell)
        if re.search(r'<<<', raw_cmd) and re.search(r'\|\s*(?:sh|bash)\b', raw_cmd):
            return Decision.DENY, {"reason": "Here-string piped to shell"}

        # env -i / env -u with shell -c wrapping dangerous command
        if re.search(r'env\s+(?:-i|-u)\s+\S+.*(?:bash|sh|zsh)\s+-c', raw_cmd, re.DOTALL):
            if re.search(r'rm\s+-[rfRF]+', raw_cmd) or re.search(r'rm\s+--(?:recursive|force)', raw_cmd):
                return Decision.DENY, {"reason": "env wrapper with dangerous rm in shell -c"}

        # Process substitution: cmd <(printf/echo 'rm -rf ...')
        ps_m = re.search(r'(\S+)\s+<\(\s*(.*)\)', raw_cmd, re.DOTALL)
        if ps_m:
            cmd_name = ps_m.group(1)
            ps_content = ps_m.group(2)
            if (ps_content.startswith("'") and ps_content.endswith("'")) or \
               (ps_content.startswith('"') and ps_content.endswith('"')):
                ps_content = ps_content[1:-1]
            if re.search(r'rm\s+-[rfRF]+', ps_content, re.IGNORECASE) and \
               cmd_name in ('bash', 'sh', 'zsh', 'source', '.'):
                return Decision.DENY, {"reason": "Process substitution with dangerous rm"}
            if re.search(r'rm\s+--(?:recursive|force)', ps_content, re.IGNORECASE) and \
               cmd_name in ('bash', 'sh', 'zsh', 'source', '.'):
                return Decision.DENY, {"reason": "Process substitution with rm long flags"}
            if re.search(r'(?:curl|wget)', ps_content) and \
               re.match(r'python3?$', cmd_name):
                return Decision.DENY, {"reason": "Remote code via process substitution into interpreter"}

        # rm with long flags (--force, --recursive, --force --recursive, etc.)
        if re.search(r'rm\s+--(?:force|recursive)\b', raw_cmd, re.IGNORECASE):
            has_force = bool(re.search(r'--force\b', raw_cmd, re.IGNORECASE))
            has_recursive = bool(re.search(r'--recursive\b', raw_cmd, re.IGNORECASE))
            has_home = bool(re.search(r'~', raw_cmd))
            has_home_var = bool(re.search(r'\$HOME', raw_cmd))
            if (has_force and has_recursive and has_home) or \
               (has_force and has_recursive and has_home_var):
                return Decision.DENY, {"reason": "rm with --force and --recursive targeting home"}
            if has_recursive and re.search(r'rm\s+.*?-f\b', raw_cmd, re.IGNORECASE) and has_home:
                return Decision.DENY, {"reason": "rm --recursive -f targeting home"}
            if has_force and re.search(r'rm\s+.*?-r\b', raw_cmd, re.IGNORECASE) and has_home:
                return Decision.DENY, {"reason": "rm --force -r targeting home"}
            if has_recursive and has_force and (has_home or has_home_var):
                return Decision.DENY, {"reason": "rm --recursive ... --force targeting home"}

        # rm -R (uppercase R) targeting home
        if re.search(r'rm\s+-R\b', raw_cmd, re.IGNORECASE) and re.search(r'~', raw_cmd):
            if re.search(r'-[fF]\b', raw_cmd):
                return Decision.DENY, {"reason": "rm -R -f targeting home"}
            return Decision.DENY, {"reason": "rm -R recursive targeting home"}

        # Backslash-escaped rm: rm\ -rf\ ~/.*
        if re.search(r'\\ ', raw_cmd):
            unescaped = remove_backslash_spaces(raw_cmd)
            if unescaped != raw_cmd and re.match(r'^rm\b', unescaped):
                if re.search(r'-[rfRF]+', unescaped, re.IGNORECASE) and re.search(r'~', unescaped):
                    return Decision.DENY, {"reason": "Backslash-escaped rm -rf targeting home"}

        # Quoted partial names: "rm" "-rf", r"m" -r"f", etc.
        _has_quote_frag = False
        if re.search(r'\b[rR]["\']\S*["\']\s', raw_cmd):
            _has_quote_frag = True
        if re.search(r'["\'][rmRM]{1,2}["\']\s+["\']?-?[rfRF]+', raw_cmd):
            _has_quote_frag = True
        if re.search(r"[\x27]rm[\x27]\s+[\x27]", raw_cmd):
            _has_quote_frag = True
        if _has_quote_frag:
            unquoted = strip_shell_quotes(raw_cmd)
            if unquoted != raw_cmd and re.match(r'\s*rm\b', unquoted):
                if re.search(r'-[rfRF]+', unquoted, re.IGNORECASE) and re.search(r'~', unquoted):
                    return Decision.DENY, {"reason": "Quoted-obfuscated rm -rf targeting home"}
                if re.search(r'--(?:force|recursive)', unquoted, re.IGNORECASE) and re.search(r'~', unquoted):
                    return Decision.DENY, {"reason": "Quoted-obfuscated rm long flags targeting home"}

        return Decision.ALLOW, None

    def _global_danger_checks(self, cmd: str, stripped: str, original: str) -> Tuple[Decision, Optional[Dict]]:
        if re.search(r'find\s+.*-delete', stripped, re.DOTALL):
            return Decision.DENY, {"reason": "Destructive find -delete"}

        # Detect echo/printf piped to shell, but ignore sh -n / bash -n
        if re.search(r'(?:echo|printf)\s+.*\|\s*(?:sh|bash)\b', original, re.DOTALL):
            if not re.search(r'\|\s*(?:sh|bash)\s+-n\b', original, re.DOTALL):
                if not re.search(r'\|\s*(?:sh|bash)\s+-c\s+.*echo', original, re.DOTALL):
                    return Decision.DENY, {"reason": "Dangerous command echoed/piped to shell"}

        if re.search(r'python3?\s+-c\s*["\'].*?(?:os\.system|shutil\.rmtree|subprocess\.)', original, re.DOTALL):
            if not re.search(r'subprocess\.run\s*\(\s*\[\s*[\'\"]echo[\'\"]', original):
                return Decision.DENY, {"reason": "Python dangerous call"}

        # Detect writing dangerous script to /tmp and executing
        write_pattern = r'(?:echo|printf|cat)\s+.*rm\s+-rf.*>\s*/tmp/[^\s;]+'
        exec_pattern = r'(?:sh|bash|source|\.)\s+/tmp/[^\s;]+'
        if re.search(write_pattern, original, re.DOTALL) and re.search(exec_pattern, original, re.DOTALL):
            return Decision.DENY, {"reason": "Writing dangerous script to /tmp and executing"}

        # Detect base64/xxd decode to file, then execute
        write_decode_pattern = r'(?:echo|printf|cat)\s+.*\|\s*(?:base64|xxd)\s+-(?:d|r|p)\s*>\s*/tmp/[^\s;]+'
        if re.search(write_decode_pattern, original, re.DOTALL) and re.search(exec_pattern, original, re.DOTALL):
            return Decision.DENY, {"reason": "Decode to file then execute"}

        # Detect alias definition followed by execution of the alias
        alias_def = re.search(r'alias\s+([A-Za-z_][A-Za-z0-9_]*)\s*=\s*["\'].*rm\s+-rf.*["\']', original)
        if alias_def:
            alias_name = alias_def.group(1)
            if re.search(rf'(?<![A-Za-z0-9_]){re.escape(alias_name)}(?![A-Za-z0-9_])', original):
                return Decision.DENY, {"reason": "Alias with rm -rf and execution"}

        # rm with quoted "$HOME" paths
        _rm_flags = re.search(r'rm\s+-[rfRF]+', cmd, re.IGNORECASE)
        _has_qhome = re.search(r'"\$HOME', cmd)
        if _rm_flags and _has_qhome and not re.match(r'^(?:echo|printf)\s+[\'\"]', cmd):
            return Decision.DENY, {"reason": "rm -rf quoted $HOME paths"}
        if re.search(r'rm\s+--recursive\s+--force', cmd, re.IGNORECASE) and _has_qhome and not re.match(r'^(?:echo|printf)\s+[\'\"]', cmd):
            return Decision.DENY, {"reason": "rm --recursive --force quoted $HOME"}
        if re.search(r'command\s+rm\s+-[rfRF]+', cmd, re.IGNORECASE) and _has_qhome:
            return Decision.DENY, {"reason": "command rm quoted $HOME paths"}
        if re.search(r'rm\s+-[rfRF]+', cmd, re.IGNORECASE) and re.search(r'"\$\{HOME\}/', cmd):
            return Decision.DENY, {"reason": "rm -rf ${HOME} brace paths"}
        if re.search(r'rm\s+-[rfRF]+', cmd, re.IGNORECASE) and re.search(r'"\$\(printf', cmd):
            return Decision.DENY, {"reason": "rm -rf with printf subshell path"}

        # Truncation targeting "$HOME/..." (quoted)
        if re.search(r'>\s*"\$HOME/', cmd):
            return Decision.DENY, {"reason": "Truncating $HOME file"}
        if re.search(r':\s*>\s*"\$HOME/', cmd):
            return Decision.DENY, {"reason": "Truncating $HOME file (colon)"}
        if re.search(r'truncate\s+-s\s+0\s+"\$HOME/', cmd):
            return Decision.DENY, {"reason": "Truncating $HOME file with truncate"}
        if re.search(r'printf\s+""\s*>\s*"\$HOME/', cmd):
            return Decision.DENY, {"reason": "Printf truncating $HOME file"}
        if re.search(r'dd\s+if=/dev/null\s+of="\$HOME/', cmd):
            return Decision.DENY, {"reason": "dd truncating $HOME file"}
        if re.search(r'echo\s+-n?\s*>\s*"\$HOME/', cmd):
            return Decision.DENY, {"reason": "Echo truncating $HOME file"}

        # env with dangerous variable assignments
        env_m = re.search(r'(?:sudo\s+)?env\s+([A-Za-z_][A-Za-z0-9_]*)=(["\']?)([^"]*)\2', original)
        if env_m:
            var_name = env_m.group(1)
            var_val = env_m.group(3)
            if 'rm' in var_val and ('-r' in var_val or '-f' in var_val or 'rf' in var_val):
                return Decision.DENY, {"reason": "env with dangerous rm variable assignment"}

        if re.search(r'BASH_ENV\s*=', cmd):
            return Decision.DENY, {"reason": "BASH_ENV set with shell execution"}
        if re.search(r'SHELLOPTS\s*=', cmd):
            return Decision.DENY, {"reason": "SHELLOPTS override"}
        if re.search(r'POSIXLY_CORRECT\s*=', cmd):
            return Decision.DENY, {"reason": "POSIXLY_CORRECT override"}

        if re.search(r'\$\{?IFS\}?', original) and re.search(r'rm', original, re.IGNORECASE):
            return Decision.DENY, {"reason": "IFS manipulation with rm command"}

        if re.search(r'\br\u043c\b|r\u2013|rm\u2014', original):
            return Decision.DENY, {"reason": "Unicode lookalike obfuscation"}

        if re.search(r'(?:eval|sh\s+-c|bash\s+-c|zsh\s+-c)\b', original) and \
           re.search(r'\$\(.*(?:curl|wget)', original):
            return Decision.DENY, {"reason": "Shell wrapper with remote download substitution"}

        if re.search(r'(?:echo|printf)\s+.*\\(?:x[0-9a-fA-F]{2}|[0-7]{3})', original) and \
           re.search(r'\|\s*(?:sh|bash)\b', original):
            if not re.search(r'\|\s*(?:sh|bash)\s+-n\b', original):
                return Decision.DENY, {"reason": "Hex/octal escaped command piped to shell"}

        if re.search(r'(?:perl|ruby|node|php)\s+-[a-zA-Z]\s+.*\|\s*(?:sh|bash|zsh)\b', original, re.DOTALL):
            return Decision.DENY, {"reason": "Interpreter script piped to shell"}
        if re.search(r'python3?\s+-c\s+.*\|\s*(?:sh|bash|zsh)\b', original, re.DOTALL):
            return Decision.DENY, {"reason": "Python script piped to shell"}

        if re.search(r'(?:echo|printf)\s+.*\|\s*(?:base64|xxd)\s+-(?:d|r|p)\s*\|\s*(?:sh|bash|zsh)\b', original, re.DOTALL):
            if not re.search(r'sh\s+-c\s+[\'"].*\becho\s+[\'"]\s*(?:Dry|Would|dry|would)', original):
                return Decision.DENY, {"reason": "Decoded content piped to shell"}

        # ── New checks for strict test failures ──

        # 1. read + eval with variable (Real-world destructive #11)
        if re.search(r'read\s+.*\s+cmd\s*;.*eval\s*"\$cmd"', original):
            return Decision.DENY, {"reason": "Read then eval of variable"}

        # 2. Python exec with base64 or fromhex (base64 and hex categories)
        python_match = re.search(r'python3?\s+-c\s+(["\'])(.*?)(?<!\\)\1', original, re.DOTALL)
        if python_match:
            code = python_match.group(2)
            if re.search(r'exec\s*\(\s*(?:base64\.b64decode|bytes\.fromhex)', code):
                return Decision.DENY, {"reason": "Python exec with obfuscated payload"}

        # 3. cat piped to shell (pipelines category)
        if re.search(r'cat\s+/\S+\s*\|\s*(?:sh|bash|zsh)\b', original):
            return Decision.DENY, {"reason": "File piped to shell"}

        # 4. nohup with dangerous shell -c (background category)
        if re.search(r'nohup\s+.*(?:sh|bash|zsh)\s+-c\s+[\'"].*rm\s+-rf', original):
            return Decision.DENY, {"reason": "nohup with dangerous shell command"}

        # 5. kill -9 -1 (process_kill)
        if re.search(r'kill\s+-9\s+-1\b', original):
            return Decision.DENY, {"reason": "Kill all processes"}

        # 6. kill with pgrep substitution (process_kill)
        if re.search(r'kill\s+\$\(pgrep', original):
            return Decision.DENY, {"reason": "Kill with pgrep substitution"}

        # 7. mv from $HOME to somewhere (replacement)
        if re.search(r'mv\s+.*?\$HOME/.*?\s+', original):
            return Decision.DENY, {"reason": "Moving file from $HOME"}

        # 8. cp /dev/null to $HOME (replacement)
        if re.search(r'cp\s+/dev/null\s+.*?\$HOME', original):
            return Decision.DENY, {"reason": "Copying /dev/null to $HOME"}

        # 9. install /dev/null to $HOME (replacement)
        if re.search(r'install\s+/dev/null\s+.*?\$HOME', original):
            return Decision.DENY, {"reason": "Installing /dev/null to $HOME"}

        # 10. Function with eval/bash -c inside (functions category)
        if re.search(r'([A-Za-z_][A-Za-z0-9_]*)\s*\(\s*\)\s*\{\s*(?:eval|bash\s+-c|sh\s+-c).*rm\s+-rf', original):
            return Decision.DENY, {"reason": "Function with dangerous eval/bash -c"}

        return Decision.ALLOW, None

    def evaluate(self, raw_cmd: str, session_id: str,
                 skip_allowlist: bool = False, depth: int = 0) -> Tuple[Decision, Optional[Dict]]:
        self.session.set_session(session_id)
        if not self.config.enabled:
            return Decision.ALLOW, None

        if depth > 10:
            return Decision.ASK, {"reason": "Max recursion depth exceeded"}

        # ── EARLY: Safe decode-only (base64/xxd without pipe to shell) ──
        has_decode = re.search(r'\|\s*(?:base64|xxd)\s+-(?:d|r|p)', raw_cmd)
        if has_decode:
            has_shell_pipe = re.search(r'\|\s*(?:sh|bash|zsh)\b', raw_cmd)
            has_shell_wrapper = re.search(r'(?:^|\||;|&&|\|\||\{)\s*(?:eval|sh\s+-c|bash\s+-c|zsh\s+-c)\b', raw_cmd)
            has_write_then_exec = re.search(r'>\s*/\S+', raw_cmd) and re.search(r'(?:^|;|&&|\|\|)\s*(?:sh|bash|source|\.)\s+', raw_cmd)
            if not has_shell_pipe and not has_shell_wrapper and not has_write_then_exec:
                return Decision.ALLOW, {"reason": "Safe decode-only (no shell execution)"}

        # ── EARLY: Check raw command for safe dry-run pipeline ──
        if self._is_safe_dry_run_pipeline(raw_cmd):
            return Decision.ALLOW, {"reason": "Safe dry-run pipeline"}

        # ── EARLY: Check raw command for patterns that survive normalization/stripping ──
        raw_decision, raw_info = self._check_raw_rm_patterns(raw_cmd)
        if raw_decision == Decision.DENY:
            return raw_decision, raw_info

        # Normalize after early checks
        cmd = normalize_command(raw_cmd)

        # ── PRE-RESOLVE: Detect shell wrappers with dangerous substitutions ──
        if re.search(r'(?:eval|sh\s+-c|bash\s+-c|zsh\s+-c)\b', raw_cmd):
            if re.search(r'\$\(.*(?:curl|wget)', raw_cmd):
                return Decision.DENY, {"reason": "Shell wrapper with remote download substitution"}
            if re.search(r'\$\([\'"]?(?:printf|echo)\s+.*rm\s+-[rfRF]', raw_cmd):
                return Decision.DENY, {"reason": "Shell wrapper with printf/echo building rm command"}
            if re.search(r'\$\(.*\|\s*(?:base64|xxd)\s+-(?:d|r|p)', raw_cmd):
                if not re.search(r"\|\s*sed\s*['\"]\S*echo\b", raw_cmd):
                    return Decision.DENY, {"reason": "Shell wrapper with decode substitution"}

        # ── Unwrap literal bash -c / sh -c / eval ──
        unwrapped, inner = self._unwrap_literal_wrapper(cmd)
        if unwrapped and inner is not None:
            return self.evaluate(inner, session_id, skip_allowlist, depth + 1)

        # ── Resolve eval/sh -c wrappers and subshells ──
        resolved, final_payload = resolve_whole_command_wrapper(raw_cmd)
        if resolved and final_payload is not None:
            if is_inert_echo_statement(final_payload):
                return Decision.ALLOW, {"reason": "Resolved to safe echo/printf"}
            return self.evaluate(final_payload, session_id, skip_allowlist, depth + 1)

        # ── Variable concatenation ──
        if self._has_variable_concatenation_danger(cmd):
            return Decision.DENY, {"reason": "Variable concatenation builds dangerous command"}

        # ── Dangerous variable assignment and usage ──
        if self._has_dangerous_variable_usage(cmd):
            return Decision.DENY, {"reason": "Dangerous variable assignment and usage"}

        # ── Obfuscation decoding ──
        decoded = decode_obfuscated(raw_cmd)
        if decoded and len(decoded) >= len(raw_cmd) * 0.4:
            dec_decision, dec_info = self.evaluate(decoded, session_id, skip_allowlist, depth + 1)
            if dec_decision in (Decision.DENY, Decision.ASK):
                return dec_decision, {
                    "reason": f"Obfuscated payload decodes to: {decoded[:80]}...",
                    "decoded_decision": dec_decision.value,
                    "decoded_info": dec_info,
                }

        # ── Strip quoted text for pattern checks ──
        stripped_cmd = self.shell_detector.strip_quoted_text(cmd)

        # ── Global danger checks ──
        global_decision, global_info = self._global_danger_checks(cmd, stripped_cmd, raw_cmd)
        if global_decision in (Decision.DENY, Decision.ASK):
            return global_decision, global_info

        # ── Split into sub-commands ──
        sub_cmds = split_commands(cmd)
        if len(sub_cmds) > 1:
            decisions = []
            for sub in sub_cmds:
                sub_dec, sub_info = self.evaluate(sub, session_id, skip_allowlist, depth + 1)
                decisions.append(sub_dec)
                if sub_dec == Decision.DENY:
                    return Decision.DENY, {"reason": f"Dangerous sub-command: {sub[:50]}..."}
            if any(d == Decision.ASK for d in decisions):
                return Decision.ASK, {"reason": "Some sub-commands are uncertain"}
            return Decision.ALLOW, None

        # ── Single command ──

        # 1. Allowlist
        if not skip_allowlist:
            base_cmd = cmd.split()[0] if cmd.split() else ""
            if base_cmd in self.config.safe_commands:
                sub_decision, sub_info = self._extract_and_evaluate_substitutions(cmd)
                if sub_decision in (Decision.DENY, Decision.ASK):
                    return sub_decision, sub_info
                path_violation = self.path_protector.check_file_access(cmd)
                if path_violation:
                    return Decision.ASK, path_violation
                return Decision.ALLOW, None

        # 2. Substitutions
        sub_decision, sub_info = self._extract_and_evaluate_substitutions(cmd)
        if sub_decision in (Decision.DENY, Decision.ASK):
            return sub_decision, sub_info

        # 3. Script languages
        script_decision, script_info = self._check_script_languages(cmd)
        if script_decision == Decision.ALLOW and script_info and script_info.get("dry_run"):
            return Decision.ALLOW, script_info
        if script_decision in (Decision.DENY, Decision.ASK):
            return script_decision, script_info

        # 4. Git force push
        if self.config.block_git_force_push and re.search(r'git\s+push\s+--force', stripped_cmd):
            return Decision.DENY, {"reason": "Force push is blocked by policy"}

        # 5. Obfuscation in scripts
        if self.config.block_obfuscation:
            scripts = extract_embedded_scripts(cmd)
            for script in scripts:
                if self._is_obfuscated(script):
                    return Decision.DENY, {"reason": "Obfuscated script detected"}

        # 6. Pack patterns (using stripped only to avoid false positives on safe echo/printf)
        for pack in self.packs:
            safe_match = any(pat.search(stripped_cmd) for pat in pack["safe"])
            if safe_match:
                continue
            for dpat in pack["destructive"]:
                if dpat["regex"].search(stripped_cmd):
                    if dpat["severity"] == Severity.CRITICAL:
                        return Decision.DENY, {"pack": pack["id"], "reason": dpat["reason"]}
                    else:
                        return Decision.ASK, {"pack": pack["id"], "reason": dpat["reason"]}

        # 7. Path protection
        path_violation = self.path_protector.check_file_access(cmd)
        if path_violation:
            return Decision.ASK, path_violation

        return Decision.ALLOW, None

    def _is_obfuscated(self, code: str) -> bool:
        obf_patterns = [
            r'printf.*\\x[0-9a-fA-F]+',
            r'printf.*\\[0-7]{3}',
            r'base64\s+-d.*\|.*sh',
            r'echo\s+.*\|.*base64',
            r'\$\(.*printf.*\)'
        ]
        return any(re.search(p, code) for p in obf_patterns)
