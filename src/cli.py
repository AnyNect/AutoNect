"""AnyNect CLI — global entry point for AutoNect.

Installed via `pip install -e .` which registers the `AnyNect` command
through setup.py's entry_points.
"""
import argparse
import sys
import subprocess
import webbrowser
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent


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
    cmd = [
        sys.executable, "-m", "uvicorn", "src.web.server:app",
        "--host", args.host, "--port", str(args.port),
    ]
    if args.reload:
        cmd.append("--reload")
    return _run(cmd)


def cmd_setup(args):
    script = PROJECT_ROOT / "setup.sh"
    if not script.exists():
        print(f"setup.sh not found at {script}", file=sys.stderr)
        return 1
    return _run(["bash", str(script)])


def cmd_login(args):
    webbrowser.open("https://chat.deepseek.com/")
    return 0


def cmd_test(args):
    mapping = {
        "config": "tests.test_config",
        "browser": "tests.test_browser",
        "parser": "tests.test_parser",
        "security": "tests.test_security",
    }
    target = args.target or "all"
    if target == "all":
        return _run([sys.executable, "-m", "pytest", "tests/"])
    module = mapping.get(target)
    if not module:
        print(f"Unknown test target: {target}", file=sys.stderr)
        print(f"Available: {', '.join(mapping)}", file=sys.stderr)
        return 2
    return _run([sys.executable, "-m", module])


def cmd_guard(args):
    mode = args.mode or "standard"
    if mode == "strict":
        return _run([sys.executable, "-m", "src.security.test_guard_strict"])
    return _run([sys.executable, "-m", "src.security.test_guard"])


def cmd_version(args):
    print("AutoNect v1.0.0")
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="AnyNect",
        description="AutoNect — AI-driven desktop automation via DeepSeek.",
    )
    sub = parser.add_subparsers(dest="command", metavar="<command>")

    p_start = sub.add_parser("start", help="Start the AutoNect web server (default)")
    p_start.add_argument("--host", default="127.0.0.1", help="Bind host (default: 127.0.0.1)")
    p_start.add_argument("--port", type=int, default=8000, help="Bind port (default: 8000)")
    p_start.add_argument("--no-reload", dest="reload", action="store_false", default=True,
                         help="Disable uvicorn auto-reload")
    p_start.set_defaults(func=cmd_start)

    p_setup = sub.add_parser("setup", help="Run setup.sh to install dependencies and browsers")
    p_setup.set_defaults(func=cmd_setup)

    p_login = sub.add_parser("login", help="Open DeepSeek in your browser for login")
    p_login.set_defaults(func=cmd_login)

    p_test = sub.add_parser("test", help="Run tests")
    p_test.add_argument("target", nargs="?", help="config | browser | parser | security | all (default)")
    p_test.set_defaults(func=cmd_test)

    p_guard = sub.add_parser("guard", help="Run security guard tests")
    p_guard.add_argument("mode", nargs="?", choices=["standard", "strict"], help="Test mode")
    p_guard.set_defaults(func=cmd_guard)

    p_ver = sub.add_parser("version", help="Print version")
    p_ver.set_defaults(func=cmd_version)

    args = parser.parse_args(argv)

    if not args.command:
        # Default action: start the server
        args.host = "127.0.0.1"
        args.port = 8000
        args.reload = True
        return cmd_start(args)

    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())