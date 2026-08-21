from .constants import Severity

PACKS = [
    {
        "id": "core.filesystem",
        "safe_patterns": [
            r"rm\s+.*\.log",
            r"rm\s+-f\s+.*\.tmp",
            r"rm\s+-rf\s+/tmp/",
            r"rm\s+-rf\s+/var/tmp/",
            r"sh\s+-n\s+",
            r"bash\s+-n\s+",
            r"(?:curl|wget)\s+.*\|\s*(?:sh|bash)\s+(?:-s\s+)?--\s+--dry-run",
            r"(?:curl|wget)\s+.*\|\s*(?:sh|bash)\s+-c\s+['\"]echo",
            r"printf\s+%s",  # printf %s is string formatting, safe by itself
            r"printf\s+.*%s.*\n.*\|\s*cat",  # printf piped to cat is analysis
            r"echo\s+['\"].*rm\s+-rf.*['\"]\s*\|\s*cat",  # echo rm piped to cat is analysis
        ],
        "destructive_patterns": [
            # Root
            {"pattern": r"rm\s+-rf\s+/(?:$|\s)", "severity": Severity.CRITICAL, "reason": "Recursive force removal of root"},
            {"pattern": r"rm\s+-rf\s+--\s+/(?:$|\s)", "severity": Severity.CRITICAL, "reason": "Recursive force removal of root (with --)"},
            {"pattern": r"rm\s+-r\s+/(?:$|\s)", "severity": Severity.CRITICAL, "reason": "Recursive removal of root"},
            {"pattern": r"rm\s+-f\s+/(?:$|\s)", "severity": Severity.CRITICAL, "reason": "Force removal of root"},
            {"pattern": r"rm\s+-rf\s+/root", "severity": Severity.CRITICAL, "reason": "Removing /root directory"},

            # Home directory
            {"pattern": r"rm\s+-rf\s+~", "severity": Severity.CRITICAL, "reason": "Recursive force removal of home"},
            {"pattern": r"rm\s+-f\s+~", "severity": Severity.CRITICAL, "reason": "Force removal of home"},
            {"pattern": r"rm\s+-rf\s+~(/[^ ]*)?", "severity": Severity.CRITICAL, "reason": "Removing under home"},
            {"pattern": r"rm\s+-f\s+~(/[^ ]*)?", "severity": Severity.CRITICAL, "reason": "Removing under home"},
            {"pattern": r"rm\s+-rf\s+/home/", "severity": Severity.CRITICAL, "reason": "Removing under /home"},
            {"pattern": r"rm\s+-rf\s+\$HOME", "severity": Severity.CRITICAL, "reason": "Removing $HOME"},
            {"pattern": r'rm\s+-rf\s+"\$HOME"', "severity": Severity.CRITICAL, "reason": "Removing quoted $HOME"},
            # -- with globs
            {"pattern": r"rm\s+-rf\s+--\s+~[/\\s]", "severity": Severity.CRITICAL, "reason": "Home with --"},
            {"pattern": r"rm\s+-rf\s+--\s+\$HOME", "severity": Severity.CRITICAL, "reason": "$HOME with --"},
            {"pattern": r'rm\s+-rf\s+--\s+"\$HOME"', "severity": Severity.CRITICAL, "reason": "Quoted $HOME with --"},
            {"pattern": r"rm\s+-rf\s+--\s+\$HOME[/\\*\\.]", "severity": Severity.CRITICAL, "reason": "$HOME glob with --"},
            {"pattern": r'rm\s+-rf\s+--\s+"\$HOME"[/\\*\\.]', "severity": Severity.CRITICAL, "reason": "Quoted $HOME glob with --"},
            # --recursive --force variants
            {"pattern": r"rm\s+--recursive\s+--force\s+~", "severity": Severity.CRITICAL, "reason": "Home with --recursive --force"},
            {"pattern": r"rm\s+--force\s+--recursive\s+~", "severity": Severity.CRITICAL, "reason": "Home with --force --recursive"},
            {"pattern": r"rm\s+-[rfRF]+\s+~[/\\s]", "severity": Severity.CRITICAL, "reason": "Home with combined flags"},
            {"pattern": r"rm\s+~[/\\s].*?-[rfRF]+", "severity": Severity.CRITICAL, "reason": "Home with flags after path"},
            # Quoted $HOME with glob (no --)
            {"pattern": r'rm\s+-[rfRF]+\s+"\$HOME"[/\\*\\.]', "severity": Severity.CRITICAL, "reason": "Quoted $HOME glob rm"},
            {"pattern": r"rm\s+-rf\s+\$HOME[/\\*\\.]", "severity": Severity.CRITICAL, "reason": "$HOME glob rm"},
            # --recursive --force with quoted $HOME
            {"pattern": r'rm\s+--recursive\s+--force\s+"\$HOME"/', "severity": Severity.CRITICAL, "reason": "Quoted $HOME --recursive --force"},
            # Flag reordering with long flags
            {"pattern": r"rm\s+~[/\\s].*?\s+--(?:recursive|force)\b", "severity": Severity.CRITICAL, "reason": "Home rm with long flags after path"},
            {"pattern": r"rm\s+~[/\\s].*?\s+-[rfRF]+$", "severity": Severity.CRITICAL, "reason": "Home rm with flags trailing"},
            # Long flags split around paths
            {"pattern": r"rm\s+--recursive\b.*~[/\\s]", "severity": Severity.CRITICAL, "reason": "rm --recursive with home path (force may follow)"},
            {"pattern": r"rm\s+--force\b.*~[/\\s]", "severity": Severity.CRITICAL, "reason": "rm --force with home path (recursive may follow)"},
            # Both long flags present with home
            {"pattern": r"(?=.*--recursive)(?=.*--force).*\brm\b.*~[/\\s]", "severity": Severity.CRITICAL, "reason": "rm with both --recursive and --force targeting home"},
            # command rm
            {"pattern": r"command\s+rm\s+-rf\s+~", "severity": Severity.CRITICAL, "reason": "command rm -rf home"},
            {"pattern": r'command\s+rm\s+-rf\s+--\s+"\$HOME"/', "severity": Severity.CRITICAL, "reason": "command rm -rf -- quoted $HOME"},
            {"pattern": r"command\s+rm\s+-rf\s+--\s+~", "severity": Severity.CRITICAL, "reason": "command rm -rf -- home"},

            # Shell -c
            {"pattern": r"(?:bash|sh|zsh)\s+-c\s+['\"].*rm\s+-rf\s+~", "severity": Severity.CRITICAL, "reason": "Shell -c with rm -rf home"},
            # -R flag (uppercase R = recursive in GNU rm)
            {"pattern": r"rm\s+-R\s+", "severity": Severity.HIGH, "reason": "rm -R recursive"},
            # kill -9 -1 (kill all processes)
            {"pattern": r"kill\s+-9\s+-1\b", "severity": Severity.CRITICAL, "reason": "Kill all processes"},
            # kill $(pgrep ...) — process kill via command substitution
            {"pattern": r"kill\s+\$\(pgrep", "severity": Severity.CRITICAL, "reason": "Kill via pgrep substitution"},
            # mv/cp/install targeting $HOME (data replacement/exfiltration)
            {"pattern": r"mv\s+.*\$HOME", "severity": Severity.HIGH, "reason": "Moving file involving $HOME"},
            {"pattern": r"cp\s+/dev/null\s+.*\$HOME", "severity": Severity.HIGH, "reason": "Copying /dev/null to $HOME"},
            {"pattern": r"install\s+/dev/null\s+.*\$HOME", "severity": Severity.HIGH, "reason": "Installing /dev/null to $HOME"},
            # python3 <(curl ...) — remote interpreter execution
            {"pattern": r"python3?\s+<\(\s*(?:curl|wget)", "severity": Severity.CRITICAL, "reason": "Remote via process substitution into interpreter"},
            # bash/sh/source <(printf/echo 'rm ...') — process substitution
            {"pattern": r"(?:bash|sh|zsh|source|\.)\s+<\(\s*(?:printf|echo)\s+", "severity": Severity.CRITICAL, "reason": "Process substitution with printf/echo"},
            # cat /tmp/payload | sh — arbitrary file piped to shell
            {"pattern": r"cat\s+/\S+\s*\|\s*(?:sh|bash)\b", "severity": Severity.HIGH, "reason": "File piped to shell"},

            # Current directory and globs
            {"pattern": r"rm\s+-rf\s+\.", "severity": Severity.MEDIUM, "reason": "Recursive removal of current dir"},
            {"pattern": r"rm\s+-r\s+\.", "severity": Severity.MEDIUM, "reason": "Recursive removal of current dir"},
            {"pattern": r"rm\s+-f\s+\.", "severity": Severity.MEDIUM, "reason": "Force removal of current dir"},
            {"pattern": r"rm\s+-rf\s+\*", "severity": Severity.HIGH, "reason": "Recursive glob deletion"},

            # Variables in paths
            {"pattern": r"rm\s+-rf\s+\$[A-Za-z_]+", "severity": Severity.HIGH, "reason": "Removing with variable path"},
            {"pattern": r'rm\s+-rf\s+"\$[A-Za-z_]+"', "severity": Severity.HIGH, "reason": "Removing with quoted variable path"},
            {"pattern": r"rm\s+-rf\s+'[^']*\$[A-Za-z_]+[^']*'", "severity": Severity.HIGH, "reason": "Removing with single-quoted variable path"},
            {"pattern": r"rm\s+-f\s+\$[A-Za-z_]+", "severity": Severity.HIGH, "reason": "Removing file with variable path"},
            {"pattern": r'rm\s+-f\s+"\$[A-Za-z_]+"', "severity": Severity.HIGH, "reason": "Removing file with quoted variable path"},

            # Sensitive dotfiles
            {"pattern": r"rm\s+-rf\s+\.ssh", "severity": Severity.HIGH, "reason": "Removing .ssh"},
            {"pattern": r"rm\s+-rf\s+\.config", "severity": Severity.HIGH, "reason": "Removing .config"},
            {"pattern": r"rm\s+-rf\s+\.local", "severity": Severity.HIGH, "reason": "Removing .local"},
            {"pattern": r"rm\s+-rf\s+\.cache", "severity": Severity.MEDIUM, "reason": "Removing .cache"},
            {"pattern": r"rm\s+-rf\s+\.bash_history", "severity": Severity.MEDIUM, "reason": "Removing .bash_history"},

            # Find-based deletions
            {"pattern": r"find\s+.*\s+-exec\s+rm\s+", "severity": Severity.CRITICAL, "reason": "Find -exec rm"},
            {"pattern": r"find\s+.*-delete", "severity": Severity.CRITICAL, "reason": "Find -delete"},

            # Xargs with rm
            {"pattern": r"xargs\s+rm\s+", "severity": Severity.HIGH, "reason": "Xargs with rm"},
            {"pattern": r"xargs\s+-0\s+rm\s+", "severity": Severity.HIGH, "reason": "Xargs -0 with rm"},

            # Disk destruction
            {"pattern": r"dd\s+if=/dev/zero\s+of=/dev/", "severity": Severity.CRITICAL, "reason": "Overwriting disk"},
            {"pattern": r"dd\s+if=/dev/urandom\s+of=/dev/", "severity": Severity.CRITICAL, "reason": "Overwriting disk with random"},
            {"pattern": r"mkfs\..+", "severity": Severity.CRITICAL, "reason": "Formatting disk"},
            {"pattern": r"shred\s+.*/dev/", "severity": Severity.CRITICAL, "reason": "Shredding device"},
            {"pattern": r"wipefs\s+--all\s+/dev/", "severity": Severity.CRITICAL, "reason": "Wiping filesystem"},

            # Echo/printf piped to shell
            {"pattern": r"echo\s+['\"].*rm\s+-rf.*['\"]\s*\|\s*(?:sh|bash)\b", "severity": Severity.CRITICAL, "reason": "Echoed dangerous command piped to shell"},
            {"pattern": r"printf\s+['\"].*rm\s+-rf.*['\"]\s*\|\s*(?:sh|bash)\b", "severity": Severity.CRITICAL, "reason": "Printf dangerous command piped to shell"},
            {"pattern": r"echo\s+-e\s+.*\\[0-7]{3}.*\|\s*(?:sh|bash)", "severity": Severity.CRITICAL, "reason": "Echo -e with octal escapes piped to shell"},
            {"pattern": r"echo\s+-e\s+.*\\x[0-9a-fA-F]{2}.*\|\s*(?:sh|bash)", "severity": Severity.CRITICAL, "reason": "Echo -e with hex escapes piped to shell"},

            # ── Truncation / replacement ──
            # Quoted "$HOME/..." variants
            {"pattern": r'>\s*"\$HOME/[^"]+"', "severity": Severity.HIGH, "reason": "Truncating file in quoted $HOME"},
            {"pattern": r':\s*>\s*"\$HOME/[^"]+"', "severity": Severity.HIGH, "reason": "Truncating file in quoted $HOME (colon)"},
            {"pattern": r'truncate\s+-s\s+0\s+"\$HOME/', "severity": Severity.HIGH, "reason": "Truncating quoted $HOME file"},
            {"pattern": r'printf\s+""\s*>\s*"\$HOME/', "severity": Severity.HIGH, "reason": "Printf empty truncating quoted $HOME"},
            {"pattern": r'dd\s+if=/dev/null\s+of="\$HOME/', "severity": Severity.HIGH, "reason": "dd truncating quoted $HOME file"},
            {"pattern": r'echo\s+-n?\s*>\s*"\$HOME/', "severity": Severity.HIGH, "reason": "Echo truncating quoted $HOME"},
            # Unquoted variants (~ and /home/user)
            {"pattern": r">\s*[\"']?(?:~|/home/[^/\s]+)/[^/\s]+", "severity": Severity.HIGH, "reason": "Truncating file in home"},
            {"pattern": r":\s*>\s*[\"']?(?:~|/home/[^/\s]+)/[^/\s]+", "severity": Severity.HIGH, "reason": "Truncating file in home (colon)"},
            {"pattern": r"truncate\s+-s\s+0\s+[\"']?(?:~|/home/[^/\s]+)/[^/\s]+", "severity": Severity.HIGH, "reason": "Truncating file in home"},
            {"pattern": r"dd\s+if=/dev/null\s+of=[\"']?(?:~|/home/[^/\s]+)/[^/\s]+", "severity": Severity.HIGH, "reason": "Truncating file in home with dd"},
            {"pattern": r"mv\s+.*?\s+[\"']?(?:~|\$HOME|/home/[^/\s]+)/", "severity": Severity.HIGH, "reason": "Moving file into home"},
            {"pattern": r"cp\s+/dev/null\s+[\"']?(?:~|\$HOME|/home/[^/\s]+)/", "severity": Severity.HIGH, "reason": "Copying /dev/null to home"},
            {"pattern": r"install\s+/dev/null\s+[\"']?(?:~|\$HOME|/home/[^/\s]+)/", "severity": Severity.HIGH, "reason": "Installing /dev/null to home"},
            {"pattern": r"cat\s+/dev/null\s*>\s*[\"']?(?:~|/home/[^/\s]+)/", "severity": Severity.HIGH, "reason": "Cat /dev/null to home"},

            # Remote execution
            {"pattern": r"(?:curl|wget)\s+.*\|\s*(?:sh|bash)\b", "severity": Severity.CRITICAL, "reason": "Remote script piped to shell"},
            {"pattern": r"(?:bash|sh|zsh)\s+<\s*\(.*(?:curl|wget)", "severity": Severity.CRITICAL, "reason": "Process substitution with remote download"},
            # Remote interpreters
            {"pattern": r"python3?\s+<\(\s*(?:curl|wget)", "severity": Severity.CRITICAL, "reason": "Remote via process substitution into interpreter"},
            {"pattern": r"(?:bash|sh|zsh)\s+-c\s+['\"]\$\((?:curl|wget)", "severity": Severity.CRITICAL, "reason": "Shell -c with curl/wget substitution"},
            {"pattern": r"eval\s+['\"]\$\((?:curl|wget)", "severity": Severity.CRITICAL, "reason": "Eval with curl/wget substitution"},
            {"pattern": r"source\s+<\(\s*(?:curl|wget)", "severity": Severity.CRITICAL, "reason": "Source with curl/wget process substitution"},

            # Here-strings and heredocs
            {"pattern": r"<<<\s*['\"]?\s*rm\s+-rf", "severity": Severity.CRITICAL, "reason": "Here-string with rm -rf"},
            {"pattern": r"<<<\s*['\"]?\s*\$\(.*rm\s+-rf", "severity": Severity.CRITICAL, "reason": "Here-string with command substitution"},
            {"pattern": r"cat\s+<<\s*[A-Za-z0-9_]+\s*\|\s*(?:sh|bash)", "severity": Severity.CRITICAL, "reason": "Heredoc piped to shell"},
            {"pattern": r"cat\s+.*\|\s*(?:sh|bash)\b", "severity": Severity.CRITICAL, "reason": "Cat pipe to shell"},

            # Aliases
            {"pattern": r"alias\s+[A-Za-z_][A-Za-z0-9_]*\s*=\s*['\"].*rm\s+-rf.*['\"]", "severity": Severity.CRITICAL, "reason": "Alias with rm -rf"},

            # Perl system
            {"pattern": r"perl\s+-e\s+.*system\s*\(['\"].*rm\s+-rf", "severity": Severity.CRITICAL, "reason": "Perl system with rm -rf"},
            # Python exec with hex
            {"pattern": r"python3?\s+-c\s+.*exec\s*\(\s*bytes\.fromhex", "severity": Severity.HIGH, "reason": "Python exec with hex obfuscation"},
            # Kill commands
            {"pattern": r"kill\s+-9\s+-1\b", "severity": Severity.CRITICAL, "reason": "Kill all processes"},
            {"pattern": r"killall\s+-9\s+", "severity": Severity.HIGH, "reason": "Kill all by name"},
            {"pattern": r"pkill\s+-KILL\s+", "severity": Severity.HIGH, "reason": "Kill with KILL signal"},
            {"pattern": r"kill\s+-\d+\s+-\d+", "severity": Severity.CRITICAL, "reason": "Kill process group"},
            {"pattern": r"kill\s+\$\(pgrep", "severity": Severity.CRITICAL, "reason": "Kill with pgrep"},
            # sudo env
            {"pattern": r"sudo\s+env\s+[A-Za-z_]+=.*rm\s+-rf", "severity": Severity.CRITICAL, "reason": "sudo env with rm -rf"},
            # env (without sudo)
            {"pattern": r"(?:sudo\s+)?env\s+[A-Za-z_]+=.*rm\s+-rf", "severity": Severity.CRITICAL, "reason": "env with rm -rf variable"},

            # IFS manipulation
            {"pattern": r"rm\$\{IFS\}-rf", "severity": Severity.CRITICAL, "reason": "rm with IFS obfuscation"},
            {"pattern": r"\$\{IFS\}rm\$\{IFS\}", "severity": Severity.CRITICAL, "reason": "Command name with IFS obfuscation"},

            # Shell environment variables
            {"pattern": r"BASH_ENV\s*=", "severity": Severity.HIGH, "reason": "BASH_ENV set"},
            {"pattern": r"SHELLOPTS\s*=", "severity": Severity.HIGH, "reason": "SHELLOPTS override"},
        ]
    },
    {
        "id": "core.git",
        "safe_patterns": [
            r"git\s+commit",
            r"git\s+push",
            r"git\s+pull",
            r"git\s+status",
            r"git\s+log",
            r"git\s+diff",
        ],
        "destructive_patterns": [
            {"pattern": r"git\s+reset\s+--hard", "severity": Severity.HIGH, "reason": "Hard reset"},
            {"pattern": r"git\s+clean\s+-f", "severity": Severity.MEDIUM, "reason": "Force clean"},
            {"pattern": r"git\s+push\s+--force", "severity": Severity.HIGH, "reason": "Force push"},
            {"pattern": r"git\s+rebase\s+--(continue|abort|skip)", "severity": Severity.MEDIUM, "reason": "Destructive rebase"},
        ]
    },
    {
        "id": "core.system",
        "safe_patterns": [],
        "destructive_patterns": [
            {"pattern": r"systemctl\s+stop\s+", "severity": Severity.MEDIUM, "reason": "Stopping service"},
            {"pattern": r"systemctl\s+disable\s+", "severity": Severity.MEDIUM, "reason": "Disabling service"},
            {"pattern": r"kill\s+-9\s+-1\b", "severity": Severity.CRITICAL, "reason": "Kill all"},
            {"pattern": r"killall\s+-9\s+", "severity": Severity.HIGH, "reason": "Killall -9"},
            {"pattern": r"pkill\s+-KILL\s+", "severity": Severity.HIGH, "reason": "pkill KILL"},
            {"pattern": r"kill\s+-\d+\s+-\d+", "severity": Severity.CRITICAL, "reason": "Kill process group"},
            {"pattern": r"pkill\s+-9\s+-f\s+", "severity": Severity.HIGH, "reason": "Force kill by pattern"},
        ]
    },
    {
        "id": "core.obfuscation",
        "safe_patterns": [
            r"sh\s+-n\s+",
            r"bash\s+-n\s+",
        ],
        "destructive_patterns": [
            {"pattern": r"printf.*\\x[0-9a-fA-F]+.*\$\w+\s+\$\w+", "severity": Severity.HIGH, "reason": "Printf builds command"},
            {"pattern": r"printf.*\\[0-7]{3}.*\$\w+\s+\$\w+", "severity": Severity.HIGH, "reason": "Printf octal builds command"},
            {"pattern": r"base64\s+-d.*\|.*sh", "severity": Severity.HIGH, "reason": "base64 decode to shell"},
            {"pattern": r"echo\s+.*\|.*base64\s+-d.*\|.*sh", "severity": Severity.HIGH, "reason": "echo+base64+sh"},
            {"pattern": r"\$\(.*printf.*\)", "severity": Severity.HIGH, "reason": "Command substitution with printf"},
            {"pattern": r"sh\s+-c\s+.*printf", "severity": Severity.HIGH, "reason": "sh -c with printf"},
            {"pattern": r"perl\s+-e\s+.*pack\s*\(\s*['\"]H\*['\"]", "severity": Severity.HIGH, "reason": "Perl pack obfuscation"},
            {"pattern": r"echo\s+-e\s+.*\\[0-7]{3}.*\|\s*(?:sh|bash)", "severity": Severity.HIGH, "reason": "Echo octal to shell"},
            {"pattern": r"printf\s+.*\[0-7]{3}.*\|\s*(?:sh|bash)", "severity": Severity.HIGH, "reason": "Printf octal to shell"},
            {"pattern": r"printf\s+.*\\x[0-9a-fA-F]{2}.*\|\s*(?:sh|bash)", "severity": Severity.HIGH, "reason": "Printf hex to shell"},
            {"pattern": r'eval\s+"\s*\$\(.*(?:base64|printf|xxd|perl).*\)"', "severity": Severity.HIGH, "reason": "Eval with obfuscated substitution"},
            {"pattern": r'bash\s+-c\s+"\s*\$\(.*(?:base64|printf|xxd|perl).*\)"', "severity": Severity.HIGH, "reason": "Bash -c with obfuscated substitution"},
            {"pattern": r"xxd\s+-(?:r\s+-p|p\+-r).*\|.*sh", "severity": Severity.HIGH, "reason": "xxd decode to shell"},
            {"pattern": r"sh\s+-c\s+['\"]?\$[A-Za-z_]+\s+", "severity": Severity.HIGH, "reason": "sh -c with variable expansion"},
        ]
    },
]
