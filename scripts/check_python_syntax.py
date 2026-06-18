#!/usr/bin/env python3
"""Compile tracked Python files in memory without writing .pyc files."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def tracked_python_files() -> list[Path]:
    result = subprocess.run(
        ["git", "ls-files", "-z", "*.py"],
        cwd=ROOT,
        check=True,
        capture_output=True,
    )
    return [ROOT / raw.decode() for raw in result.stdout.split(b"\0") if raw]


def main() -> int:
    errors: list[str] = []
    for path in tracked_python_files():
        rel = path.relative_to(ROOT)
        try:
            source = path.read_text(encoding="utf-8")
            compile(source, str(rel), "exec")
        except Exception as exc:
            errors.append(f"{rel}: {type(exc).__name__}: {exc}")
    if errors:
        print("Python syntax check failed:")
        for error in errors:
            print(f"- {error}")
        return 1
    print(f"Python syntax check passed: {len(tracked_python_files())} files.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
