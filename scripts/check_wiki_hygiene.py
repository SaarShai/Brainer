#!/usr/bin/env python3
"""Lightweight wiki source-of-truth hygiene check.

This intentionally does not enforce full v2 metadata or L1 links on every wiki
page. It guards the repo-level memory model: markdown is canonical, the sqlite
index is derived, and the compact top-level pointer files exist.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WIKI = ROOT / "wiki"
MEMORY_DOC = ROOT / "docs" / "MEMORY_MODEL.md"
REQUIRED = [
    WIKI,
    WIKI / "L1_index.md",
    WIKI / "schema.md",
    WIKI / "index.md",
    WIKI / "log.md",
    MEMORY_DOC,
]


def main() -> int:
    errors: list[str] = []
    for path in REQUIRED:
        if not path.exists():
            errors.append(f"missing required wiki path: {path.relative_to(ROOT)}")

    if MEMORY_DOC.exists():
        text = MEMORY_DOC.read_text(encoding="utf-8", errors="replace")
        for phrase in ("wiki/*.md", ".brainer/wiki.sqlite3", "make check", "write-gate", "compact pointer"):
            if phrase not in text:
                errors.append(f"docs/MEMORY_MODEL.md does not mention {phrase}")

    if (WIKI / "L1_index.md").exists():
        index_text = (WIKI / "L1_index.md").read_text(encoding="utf-8", errors="replace")
        for rel in ("L0_rules.md", "schema.md", "index.md", "log.md", "raw/", "projects/"):
            if rel not in index_text:
                errors.append(f"wiki/L1_index.md does not mention {rel}")

    if errors:
        return fail(errors)

    print("Wiki hygiene check passed.")
    return 0


def fail(errors: list[str]) -> int:
    print("Wiki hygiene check failed:")
    for error in errors:
        print(f"- {error}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
