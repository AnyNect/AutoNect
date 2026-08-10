import re
from typing import Optional, Dict, Tuple

from .constants import Severity, Decision
from .config import GuardConfig
from .path_protection import PathProtector
from .shell_composition import ShellCompositionDetector
from .session import SessionApprovalManager
from .packs import PACKS
from .normalize import normalize_command
from .heredoc import extract_embedded_scripts
from .ast_matcher import find_dangerous_calls
from .decoder import decode_obfuscated
from .resolve import resolve_whole_command_wrapper, is_inert_echo_statement


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
        pattern = r'\$\(([^)]+)\)|`([^`]+)`'
        matches = re.findall(pattern, cmd)
        for match in matches:
            inner = match[0] or match[1]
            if inner:
                decoded = decode_obfuscated(inner)
                if decoded:
                    dec_decision, dec_info = self.evaluate(decoded, self.session.session_id, skip_allowlist=True)
                    if dec_decision in (Decision.DENY, Decision.ASK):
                        return dec_decision, {
                            "reason": f"Obfuscated payload in substitution: {decoded[:80]}...",
                            "decoded_decision": dec_decision.value,
                            "decoded_info": dec_info,
                        }
        return Decision.ALLOW, None

    def _check_script_languages(self, cmd: str) -> Tuple[Decision, Optional[Dict]]:
        # Python
        python_match = re.search(r'python3?\s+-c\s+(["\'])(.*?)(?<!\\)\1', cmd, re.DOTALL)
        if python_match:
            code = python_match.group(2)
            dangerous = find_dangerous_calls(code)
            if dangerous:
                return Decision.DENY, {"reason": f"Python dangerous call: {dangerous[0]['function']}"}
            if re.search(r'(?:os\.system|shutil\.rmtree|os\.remove|os\.unlink|subprocess\.call|subprocess\.Popen|subprocess\.run)\s*\(', code):
                return Decision.DENY, {"reason": "Python script executes dangerous shell command"}

        # Ruby
        ruby_match = re.search(r'ruby\s+-e\s+(["\'])(.*?)(?<!\\)\1', cmd, re.DOTALL)
        if ruby_match:
            code = ruby_match.group(2)
            if re.search(r'system\s*\(.*rm\s+-rf', code) or re.search(r'`.*rm\s+-rf.*`', code):
                return Decision.DENY, {"reason": "Ruby script executes dangerous shell command"}

        # Node
        node_match = re.search(r'node\s+-e\s+(["\'])(.*?)(?<!\\)\1', cmd, re.DOTALL)
        if node_match:
            code = node_match.group(2)
            if re.search(r'(?:execSync|exec|spawn)\s*\(.*rm\s+-rf', code):
                return Decision.DENY, {"reason": "Node.js script executes dangerous shell command"}

        # PHP – refined to allow dry‑run echos
        php_match = re.search(r'php\s+-r\s+(["\'])(.*?)(?<!\\)\1', cmd, re.DOTALL)
        if php_match:
            code = php_match.group(2)
            call_match = re.search(r'(exec|system|shell_exec)\s*\(', code)
            if call_match:
                # Check if the argument is a quoted string starting with 'echo ' or "echo "
                if re.search(r'(exec|system|shell_exec)\s*\(\s*(["\'])\s*echo\s+', code):
                    # This is a dry‑run; mark it so we can skip later pack checks
                    return Decision.ALLOW, {"dry_run": True, "reason": "PHP dry-run echo"}
                else:
                    return Decision.DENY, {"reason": "PHP script executes dangerous shell command"}

        # AWK
        if re.search(r'awk\s+.*system\s*\(.*rm\s+-rf', cmd):
            return Decision.DENY, {"reason": "AWK executes dangerous shell command"}

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

    def evaluate(self, raw_cmd: str, session_id: str,
                 skip_allowlist: bool = False) -> Tuple[Decision, Optional[Dict]]:
        self.session.set_session(session_id)
        if not self.config.enabled:
            return Decision.ALLOW, None

        cmd = normalize_command(raw_cmd)

        # ── NEW: Resolve eval/sh -c wrappers with optional sed transforms ──
        resolved, final_payload = resolve_whole_command_wrapper(raw_cmd)
        if resolved and final_payload is not None:
            if is_inert_echo_statement(final_payload):
                return Decision.ALLOW, {"reason": "Resolved to safe echo/printf"}
            return self.evaluate(final_payload, session_id, skip_allowlist=True)

        # ── EARLY CHECKS (before dry-run) ──

        # 1. Python dangerous calls
        if 'python' in cmd and '-c' in cmd:
            if 'os.system' in cmd or 'shutil.rmtree' in cmd or 'subprocess' in cmd:
                if not re.search(r'subprocess\.run\s*\(\s*\[\s*[\'"]echo[\'"]', cmd):
                    return Decision.DENY, {"reason": "Python script with dangerous call"}

        # 2. Dangerous echo/printf pipes – only if not a dry-run
        if not self._is_dry_run(cmd):
            if (('echo' in cmd or 'printf' in cmd) and 
                re.search(r'\|\s*(?:sh|bash)(?:\s+|$)', cmd)):
                if not re.search(r'\|\s*(?:sh|bash)\s+-c\s+.*echo', cmd):
                    return Decision.DENY, {"reason": "Dangerous command echoed/piped to shell"}

            if 'find' in cmd and '-delete' in cmd:
                return Decision.DENY, {"reason": "Destructive find -delete"}

        # ── Obfuscation decoding ──
        decoded = decode_obfuscated(raw_cmd)
        if decoded:
            decoded_decision, decoded_info = self.evaluate(decoded, session_id, skip_allowlist=True)
            if decoded_decision in (Decision.DENY, Decision.ASK):
                return decoded_decision, {
                    "reason": f"Obfuscated payload decodes to: {decoded[:80]}...",
                    "decoded_decision": decoded_decision.value,
                    "decoded_info": decoded_info,
                }

        # ── Command substitution extraction ──
        sub_decision, sub_info = self._extract_and_evaluate_substitutions(cmd)
        if sub_decision in (Decision.DENY, Decision.ASK):
            return sub_decision, sub_info

        # ── Allowlist ──
        if not skip_allowlist:
            base_cmd = cmd.split()[0] if cmd.split() else ""
            if base_cmd in self.config.safe_commands:
                path_violation = self.path_protector.check_file_access(cmd)
                if path_violation:
                    return Decision.ASK, path_violation
                return Decision.ALLOW, None

        # ── Script language checks (BEFORE shell composition and packs) ──
        script_decision, script_info = self._check_script_languages(cmd)
        if script_decision == Decision.ALLOW and script_info and script_info.get("dry_run"):
            # Dry‑run confirmed; skip further checks
            return Decision.ALLOW, script_info
        if script_decision in (Decision.DENY, Decision.ASK):
            return script_decision, script_info

        # ── Shell composition (always checked) ──
        if self.shell_detector.has_composition(cmd):
            return Decision.ASK, {"reason": "Shell composition detected", "cmd": cmd}

        # ── Git force push ──
        if self.config.block_git_force_push and re.search(r'git\s+push\s+--force', cmd):
            return Decision.DENY, {"reason": "Force push is blocked by policy"}

        # ── Obfuscation in embedded scripts ──
        if self.config.block_obfuscation:
            scripts = extract_embedded_scripts(cmd)
            for script in scripts:
                if self._is_obfuscated(script):
                    return Decision.DENY, {"reason": "Obfuscated script detected"}

        # ── Pattern matching (packs) ──
        for pack in self.packs:
            safe_match = any(pat.search(cmd) for pat in pack["safe"])
            if safe_match:
                continue
            for dpat in pack["destructive"]:
                if dpat["regex"].search(cmd):
                    if dpat["severity"] == Severity.CRITICAL:
                        return Decision.DENY, {"pack": pack["id"], "reason": dpat["reason"]}
                    else:
                        return Decision.ASK, {"pack": pack["id"], "reason": dpat["reason"]}

        # ── Path protection ──
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