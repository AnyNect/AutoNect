"""Pytest wrapper for the strict command-guard harness.

The real harness lives at src/security/test_guard_strict.py: 65
adversarial cases covering injection, obfuscation, and destructive
commands. It was written as a standalone script with a __main__ guard,
so pytest never collected it and it ran only when someone remembered
to invoke it by hand (2026-10-05 finding).

This wrapper runs every suite in it under pytest, so a regression in
the command guard fails the suite. The harness itself is untouched.

Safety: the harness only calls guard.evaluate() -- it never executes
any of the command strings. Verified 2026-10-05.
"""
from src.security import CommandGuard
from src.security.test_guard_strict import (
    DESTRUCTIVE_COMMANDS, HARDEST_UNSAFE, REAL_WORLD_DESTRUCTIVE,
    SAFE_COMMANDS, HARDEST_SAFE,
    ADVANCED_UNSAFE_CATEGORIES, ADVANCED_SAFE_CATEGORIES,
    run, run_categories,
)

def test_strict_guard_harness_passes():
    guard = CommandGuard()
    failures = []
    failures += run(guard, DESTRUCTIVE_COMMANDS,
                    "ORIGINAL DESTRUCTIVE (must never ALLOW)", "allow")
    failures += run(guard, HARDEST_UNSAFE,
                    "HARDEST UNSAFE (must never ALLOW)", "allow")
    failures += run(guard, REAL_WORLD_DESTRUCTIVE,
                    "REAL-WORLD DESTRUCTIVE (must never ALLOW)", "allow")
    failures += run(guard, SAFE_COMMANDS,
                    "ORIGINAL SAFE (must never DENY)", "deny")
    failures += run(guard, HARDEST_SAFE,
                    "HARDEST SAFE (must never DENY)", "deny")
    failures += run_categories(guard, ADVANCED_UNSAFE_CATEGORIES,
                               "ADVANCED UNSAFE CATEGORIES (must never ALLOW)",
                               "allow")
    failures += run_categories(guard, ADVANCED_SAFE_CATEGORIES,
                               "ADVANCED SAFE CATEGORIES (must never DENY)",
                               "deny")
    assert not failures, (
        f"{len(failures)} strict failure(s); first: {failures[:1]}")
