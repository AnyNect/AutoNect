from .constants import Severity

PACKS = [
    {
        "id": "core.filesystem",
        "safe_patterns": [
            r"rm\s+.*\.log",
            r"rm\s+-f\s+.*\.tmp",
            r"rm\s+-rf\s+/tmp/",
            r"rm\s+-rf\s+/var/tmp/",
        ],
        "destructive_patterns": [
            # Root and critical paths
            {"pattern": r"rm\s+-rf\s+/", "severity": Severity.CRITICAL, "reason": "Recursive force removal of root"},
            {"pattern": r"rm\s+-rf\s+--\s+/", "severity": Severity.CRITICAL, "reason": "Recursive force removal of root (with --)"},
            {"pattern": r"rm\s+-r\s+/", "severity": Severity.CRITICAL, "reason": "Recursive removal of root"},
            {"pattern": r"rm\s+-f\s+/", "severity": Severity.CRITICAL, "reason": "Force removal of root"},
            {"pattern": r"rm\s+-rf\s+/root", "severity": Severity.CRITICAL, "reason": "Removing /root directory"},

            # Home directory
            {"pattern": r"rm\s+-rf\s+~", "severity": Severity.HIGH, "reason": "Recursive removal of home directory"},
            {"pattern": r"rm\s+-f\s+~", "severity": Severity.HIGH, "reason": "Force removal of home directory"},
            {"pattern": r"rm\s+-rf\s+~(/[^ ]*)?", "severity": Severity.HIGH, "reason": "Removing directory under home"},
            {"pattern": r"rm\s+-f\s+~(/[^ ]*)?", "severity": Severity.HIGH, "reason": "Removing file under home"},
            {"pattern": r"rm\s+-rf\s+/home/", "severity": Severity.HIGH, "reason": "Removing directory under /home"},

            # Current directory and globs
            {"pattern": r"rm\s+-rf\s+\.", "severity": Severity.MEDIUM, "reason": "Recursive removal of current directory"},
            {"pattern": r"rm\s+-r\s+\.", "severity": Severity.MEDIUM, "reason": "Recursive removal of current directory"},
            {"pattern": r"rm\s+-f\s+\.", "severity": Severity.MEDIUM, "reason": "Force removal of current directory"},
            {"pattern": r"rm\s+-rf\s+\*", "severity": Severity.HIGH, "reason": "Recursive glob deletion"},

            # Variables in paths
            {"pattern": r"rm\s+-rf\s+\$[A-Za-z_]+", "severity": Severity.HIGH, "reason": "Removing directory with variable path"},
            {"pattern": r"rm\s+-rf\s+\"\$[A-Za-z_]+\"", "severity": Severity.HIGH, "reason": "Removing directory with quoted variable path"},
            {"pattern": r"rm\s+-rf\s+\'[^\']*\$[A-Za-z_]+[^\']*\'", "severity": Severity.HIGH, "reason": "Removing directory with single-quoted variable path"},
            {"pattern": r"rm\s+-f\s+\$[A-Za-z_]+", "severity": Severity.HIGH, "reason": "Removing file with variable path"},
            {"pattern": r"rm\s+-f\s+\"\$[A-Za-z_]+\"", "severity": Severity.HIGH, "reason": "Removing file with quoted variable path"},

            # Sensitive dotfiles
            {"pattern": r"rm\s+-rf\s+\.ssh", "severity": Severity.HIGH, "reason": "Removing .ssh directory"},
            {"pattern": r"rm\s+-rf\s+\.config", "severity": Severity.HIGH, "reason": "Removing .config directory"},
            {"pattern": r"rm\s+-rf\s+\.local", "severity": Severity.HIGH, "reason": "Removing .local directory"},
            {"pattern": r"rm\s+-rf\s+\.cache", "severity": Severity.MEDIUM, "reason": "Removing .cache directory"},
            {"pattern": r"rm\s+-rf\s+\.bash_history", "severity": Severity.MEDIUM, "reason": "Removing .bash_history"},

            # Find-based deletions (critical)
            {"pattern": r"find\s+.*\s+-exec\s+rm\s+", "severity": Severity.CRITICAL, "reason": "Find -exec rm can delete many files"},
            {"pattern": r"find\s+.*-delete", "severity": Severity.CRITICAL, "reason": "Find -delete removes files directly"},

            # Xargs with rm
            {"pattern": r"xargs\s+rm\s+", "severity": Severity.HIGH, "reason": "Xargs with rm can delete many files"},
            {"pattern": r"xargs\s+-0\s+rm\s+", "severity": Severity.HIGH, "reason": "Xargs -0 with rm"},

            # Disk destruction
            {"pattern": r"dd\s+if=/dev/zero\s+of=/dev/sd", "severity": Severity.CRITICAL, "reason": "Overwriting disk"},
            {"pattern": r"mkfs\..+", "severity": Severity.CRITICAL, "reason": "Formatting disk"},
            {"pattern": r"dd\s+if=/dev/urandom\s+of=/dev/sd", "severity": Severity.CRITICAL, "reason": "Overwriting disk with random data"},

            # ---- NEW: Echo/printf of dangerous commands piped to shell ----
            {"pattern": r"echo\s+[\"'].*rm\s+-rf.*[\"']\s*\|\s*(?:sh|bash)", "severity": Severity.HIGH, "reason": "Echoed dangerous command piped to shell"},
            {"pattern": r"printf\s+[\"'].*rm\s+-rf.*[\"']\s*\|\s*(?:sh|bash)", "severity": Severity.HIGH, "reason": "Printf dangerous command piped to shell"},
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
            {"pattern": r"git\s+reset\s+--hard", "severity": Severity.HIGH, "reason": "Hard reset discarding changes"},
            {"pattern": r"git\s+clean\s+-f", "severity": Severity.MEDIUM, "reason": "Force clean of untracked files"},
            {"pattern": r"git\s+push\s+--force", "severity": Severity.HIGH, "reason": "Force push overwriting remote history"},
            {"pattern": r"git\s+rebase\s+--(continue|abort|skip)", "severity": Severity.MEDIUM, "reason": "Destructive rebase operation"},
        ]
    },
    {
        "id": "core.system",
        "destructive_patterns": [
            {"pattern": r"systemctl\s+stop\s+", "severity": Severity.MEDIUM, "reason": "Stopping a system service"},
            {"pattern": r"systemctl\s+disable\s+", "severity": Severity.MEDIUM, "reason": "Disabling a system service"},
            {"pattern": r"kill\s+-9\s+", "severity": Severity.HIGH, "reason": "Force kill a process"},
            {"pattern": r"pkill\s+-f\s+", "severity": Severity.MEDIUM, "reason": "Kill processes by pattern"},
        ]
    },
    {
        "id": "core.database",
        "destructive_patterns": [
            {"pattern": r"DROP\s+DATABASE", "severity": Severity.CRITICAL, "reason": "Dropping a database"},
            {"pattern": r"TRUNCATE\s+TABLE", "severity": Severity.HIGH, "reason": "Truncating a table"},
            {"pattern": r"DELETE\s+FROM\s+\S+\s+WHERE\s+", "severity": Severity.MEDIUM, "reason": "Bulk delete from table"},
        ]
    },
    {
        "id": "core.obfuscation",
        "safe_patterns": [],
        "destructive_patterns": [
            # General obfuscation patterns
            {"pattern": r"printf.*\\x[0-9a-fA-F]+.*\$\w+\s+\$\w+", "severity": Severity.HIGH, "reason": "Obfuscated command: printf builds command name and arguments"},
            {"pattern": r"printf.*\\[0-7]{3}.*\$\w+\s+\$\w+", "severity": Severity.HIGH, "reason": "Obfuscated command: printf with octal builds command"},
            {"pattern": r"base64\s+-d.*\|.*sh", "severity": Severity.HIGH, "reason": "Obfuscated command: base64 decode pipe to shell"},
            {"pattern": r"echo\s+.*\|.*base64\s+-d.*\|.*sh", "severity": Severity.HIGH, "reason": "Obfuscated command: echo+base64+sh"},
            {"pattern": r"\$\(.*printf.*\)", "severity": Severity.HIGH, "reason": "Obfuscated command: command substitution with printf"},
            {"pattern": r"sh\s+-c\s+.*printf", "severity": Severity.HIGH, "reason": "Obfuscated command: sh -c with printf"},
            # Perl pack
            {"pattern": r"perl\s+-e\s+.*pack\s*\(\s*['\"]H\*['\"]", "severity": Severity.HIGH, "reason": "Perl pack obfuscation"},
            # Echo/printf with escapes (these are also caught by decoders, but this is a fallback)
            {"pattern": r"echo\s+-e\s+.*\\[0-7]{3}.*\|\s*(?:sh|bash)", "severity": Severity.HIGH, "reason": "Echo with octal escapes"},
            {"pattern": r"printf\s+.*\\[0-7]{3}.*\|\s*(?:sh|bash)", "severity": Severity.HIGH, "reason": "Printf with octal escapes"},
            {"pattern": r"printf\s+.*\\x[0-9a-fA-F]{2}.*\|\s*(?:sh|bash)", "severity": Severity.HIGH, "reason": "Printf with hex escapes"},
            # Eval with command substitution
            {"pattern": r"eval\s+\"\s*\$\(.*(?:base64|printf|xxd|perl).*\)\"", "severity": Severity.HIGH, "reason": "Eval with command substitution obfuscation"},
            {"pattern": r"bash\s+-c\s+\"\s*\$\(.*(?:base64|printf|xxd|perl).*\)\"", "severity": Severity.HIGH, "reason": "Bash -c with command substitution obfuscation"},
        ]
    },
]