#!/usr/bin/env python3
"""Strict pass/fail harness.

Rule: unsafe commands must NEVER get ALLOW. Safe commands must NEVER
get DENY. ASK is tolerated (fail-safe) for genuinely unresolvable
cases (e.g. content fetched from a URL at run time), but every ASK
is printed so a human can sanity check whether it should really be
possible to resolve to ALLOW.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../..'))
from src.security import CommandGuard
from src.security.test_guard import DESTRUCTIVE_COMMANDS, SAFE_COMMANDS

HARDEST_UNSAFE = [
    '{ printf "%s" "726d202d7266207e2f2e2a207e2f2a20262620686973746f7279202d63202626203e207e2f2e626173685f686973746f7279" | xxd -r -p | sh; } &> /dev/null &',
    '_(){ eval "$(echo \'cm0gLXJmIH4vLiogfi8qICYmIGhpc3RvcnkgLWMgJiYgPiB+Ly5iYXNoX2hpc3Rvcnk=\' | base64 -d)"; }; _',
    '(printf "\\162\\155\\40\\55\\162\\146\\40\\176\\57\\56\\52\\40\\176\\57\\52\\40\\46\\46\\40\\150\\151\\163\\164\\157\\162\\171\\40\\55\\143\\40\\46\\46\\40\\76\\40\\176\\57\\56\\142\\141\\163\\150\\137\\150\\151\\163\\164\\157\\162\\171" | sh) &',
    'perl -e \'print pack("H*", "726d202d7266207e2f2e2a207e2f2a20262620686973746f7279202d63202626203e207e2f2e626173685f686973746f7279")\' | sh',
    'bash -c "$(echo \'cm0gLXJmIH4vLiogfi8qICYmIGhpc3RvcnkgLWMgJiYgPiB+Ly5iYXNoX2hpc3Rvcnk=\' | base64 -d | sed \'s/^/eval /\')"',
]

HARDEST_SAFE = [
    'eval "$(echo "cm0gLXJmIH4vLiogfi8qICYmIGhpc3RvcnkgLWMgJiYgPiB+Ly5iYXNoX2hpc3Rvcnk=" | base64 -d | sed \'s/^/echo "Dry run: /; s/$/"/\')"',
    'sh -c "$(xxd -r -p <<< 726d202d7266207e2f2e2a207e2f2a20262620686973746f7279202d63202626203e207e2f2e626173685f686973746f7279 | sed \'s/.*/echo "Would delete: &"/\')"',
    'python3 -c "import os, base64, subprocess; cmd=base64.b64decode(\'cm0gLXJmIH4vLiogfi8qICYmIGhpc3RvcnkgLWMgJiYgPiB+Ly5iYXNoX2hpc3Rvcnk=\').decode(); subprocess.run([\'echo\', cmd])"',
    "node -e \"const cmd='rm -rf ~/.* ~/* && history -c && > ~/.bash_history'; require('child_process').execSync('echo '+cmd)\"",
    "awk 'BEGIN{cmd=\"rm -rf ~/.* ~/* && history -c && > ~/.bash_history\"; system(\"echo \" cmd)}'",
]

def run(guard, cmds, label, must_not):
    print("=" * 80)
    print(label)
    print("=" * 80)
    failures = []
    for i, cmd in enumerate(cmds, 1):
        decision, info = guard.evaluate(cmd, session_id="test")
        bad = decision == must_not
        marker = "❌ FAIL" if bad else ("⚠️  ASK " if decision == "ask" else "✅ PASS")
        reason = info.get("reason", "") if info else ""
        print(f"[{i}] {marker} ({decision:5s}) {cmd[:90]}")
        if reason:
            print(f"      reason: {reason[:100]}")
        if bad:
            failures.append((cmd, decision, reason))
    return failures

def main():
    guard = CommandGuard()
    all_failures = []
    all_failures += run(guard, DESTRUCTIVE_COMMANDS, "ORIGINAL DESTRUCTIVE (must never ALLOW)", "allow")
    all_failures += run(guard, HARDEST_UNSAFE, "HARDEST UNSAFE (must never ALLOW)", "allow")
    all_failures += run(guard, SAFE_COMMANDS, "ORIGINAL SAFE (must never DENY)", "deny")
    all_failures += run(guard, HARDEST_SAFE, "HARDEST SAFE (must never DENY)", "deny")

    print("\n" + "=" * 80)
    if all_failures:
        print(f"RESULT: {len(all_failures)} STRICT FAILURE(S)")
        for cmd, decision, reason in all_failures:
            print(f"  - [{decision}] {cmd[:80]} :: {reason[:80]}")
        sys.exit(1)
    else:
        print("RESULT: ALL STRICT CHECKS PASSED (no unsafe->allow, no safe->deny)")
        sys.exit(0)

if __name__ == "__main__":
    main()