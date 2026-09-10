#!/usr/bin/env python3
"""AnyNect CLI — global entry point for AutoNect.

Installed via `pip install -e .`, which registers the `AnyNect` command
through setup.py's entry_points. `AutoNect` is kept as a backward-compat
alias pointing at the same `main` function.

Subcommands:
    start   (default)  start the AnyNect web server
    setup              run setup.sh to install/repair dependencies
    login              open DeepSeek in the default browser
    test [target]      run tests (all | config | browser)
    version            print the version
"""
import argparse
import os
import subprocess
import sys
import webbrowser
from pathlib import Path

VERSION = "1.0.0"

# When invoked through the console_scripts entry point, sys.path does not
# include the project root, so `import src.*` fails unless we add it here.
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def _run(cmd, **kwargs):
    """Run a subprocess from the project root, propagating Ctrl+C cleanly."""
    try:
        return subprocess.run(cmd, cwd=str(PROJECT_ROOT), check=True, **kwargs)
    except KeyboardInterrupt:
        print("\nInterrupted.", file=sys.stderr)
        return 130
    except subprocess.CalledProcessError as e:
        return e.returncode


def cmd_start(args):
    from src.core.config import config

    port = args.port if args.port is not None else config.get("server", "port", default=8000)
    host = args.host if args.host is not None else config.get("server", "host", default="127.0.0.1")
    reload = args.reload if args.reload is not None else config.get("server", "reload", default=False)

    # Propagate host/port to the server process so the startup banner
    # reflects the actual values instead of hardcoded defaults.
    os.environ["AUTONECT_HOST"] = str(host)
    os.environ["AUTONECT_PORT"] = str(port)

    import uvicorn
    print(f"🚀 Starting AnyNect on http://{host}:{port}")
    uvicorn.run(
        "src.web.server:app",
        host=host,
        port=port,
        reload=bool(reload),
        log_level="info",
    )
    return 0


def cmd_setup(args):
    script = PROJECT_ROOT / "setup.sh"
    if not script.exists():
        print(f"setup.sh not found at {script}", file=sys.stderr)
        return 1
    return _run(["bash", str(script)])


def cmd_login(args):
    webbrowser.open("https://chat.deepseek.com/")
    print("Opened DeepSeek in your default browser.")
    return 0


def cmd_test(args):
    mapping = {
        "config":  "tests.test_config",
        "browser": "tests.test_browser",
    }
    target = args.target or "all"
    if target == "all":
        return _run([sys.executable, "-m", "pytest", "tests/"])
    module = mapping.get(target)
    if not module:
        print(f"Unknown test target: {target}", file=sys.stderr)
        print(f"Available: all, {', '.join(mapping)}", file=sys.stderr)
        return 2
    return _run([sys.executable, "-m", module])


def cmd_version(args):
    print(f"AnyNect v{VERSION}")
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="AnyNect",
        description="AnyNect — AI-driven desktop automation via DeepSeek.",
    )
    sub = parser.add_subparsers(dest="command", metavar="<command>")

    p_start = sub.add_parser("start", help="Start the AnyNect web server (default)")
    p_start.add_argument("--host", default=None, help="Bind host (default: from config)")
    p_start.add_argument("--port", type=int, default=None, help="Bind port (default: from config)")
    p_start.add_argument("--reload", dest="reload", action="store_true", default=None,
                         help="Enable uvicorn auto-reload")
    p_start.add_argument("--no-reload", dest="reload", action="store_false",
                         help="Disable uvicorn auto-reload")
    p_start.set_defaults(func=cmd_start)

    p_setup = sub.add_parser("setup", help="Run setup.sh to install dependencies and browsers")
    p_setup.set_defaults(func=cmd_setup)

    p_login = sub.add_parser("login", help="Open DeepSeek in your default browser")
    p_login.set_defaults(func=cmd_login)

    p_test = sub.add_parser("test", help="Run tests")
    p_test.add_argument("target", nargs="?", help="all (default) | config | browser")
    p_test.set_defaults(func=cmd_test)

    p_ver = sub.add_parser("version", help="Print version")
    p_ver.set_defaults(func=cmd_version)

    args = parser.parse_args(argv)

    # No subcommand → default to `start`
    if not args.command:
        args.host = None
        args.port = None
        args.reload = None
        return cmd_start(args)

    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
