#!/usr/bin/env python3
"""Drop-time lint: catch stale mutable values in a baton file.

Wiki lesson: wiki/patterns/handoffs-rot-at-mutable-values.md — batons carried
copied-at-drop-time volatile facts (git HEADs, shas, file counts, dirty-path
lists) that rotted between drop and grab; a successor cold-verify caught a
stale canon hash in 2 of 4 places.

Rule (SKILL.md "Drop-time mutable-value lint"): any mutable-value class field
(40-hex / 7-hex sha, "N files" counts, branch names paired with a HEAD claim)
must carry a `VERIFY-AT-GRAB` tag on the same line, or be a fenced shell
command (already a live re-derivation, not a copied value). Untagged bare
values fail the lint.

One function, no framework:
    lint_baton(text: str) -> list[str]   # list of violation messages, empty = pass

CLI: `python3 lint_baton.py <baton.md>` — exit 1 with violations printed if
any untagged mutable value is found, exit 0 (silent) if clean.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

TAG = "VERIFY-AT-GRAB"

# Mutable-value patterns this lint watches for.
_SHA40 = re.compile(r"\b[0-9a-f]{40}\b")
_SHA7 = re.compile(r"\b[0-9a-f]{7,12}\b")
_FILE_COUNT = re.compile(r"\b\d+\s+files?\b", re.IGNORECASE)
_HEAD_CLAIM = re.compile(r"\bHEAD\b|\bbranch:\s*\S+", re.IGNORECASE)

_FENCE = re.compile(r"^\s*```")


def _strip_fenced_code(lines: list[str]) -> list[bool]:
    """Return a per-line bool mask: True if the line is inside a fenced code block.

    Fenced commands (e.g. `` `git status` `` blocks) are live re-derivation
    instructions, not copied values, and are exempt from the lint.
    """
    mask = []
    in_fence = False
    for line in lines:
        if _FENCE.match(line):
            in_fence = not in_fence
            mask.append(True)  # the fence marker line itself is exempt
            continue
        mask.append(in_fence)
    return mask


def lint_baton(text: str) -> list[str]:
    """Scan baton text for untagged mutable-value patterns. Returns violation messages."""
    violations: list[str] = []
    lines = text.splitlines()
    fenced = _strip_fenced_code(lines)

    for i, (line, in_fence) in enumerate(zip(lines, fenced), start=1):
        if in_fence:
            continue
        if TAG in line:
            continue

        hits = []
        if _SHA40.search(line):
            hits.append("40-hex sha")
        elif _SHA7.search(line) and re.search(r"\bsha\b|\bcommit\b|\bhash\b|\bHEAD\b", line, re.IGNORECASE):
            hits.append("short sha")
        if _FILE_COUNT.search(line):
            hits.append("file count")
        if _HEAD_CLAIM.search(line) and (_SHA40.search(line) or _SHA7.search(line)):
            hits.append("HEAD/branch claim")

        for kind in hits:
            violations.append(
                f"line {i}: untagged {kind} — add `{TAG}` on this line or "
                f"replace the literal with a live re-derivation command: {line.strip()!r}"
            )

    return violations


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("usage: lint_baton.py <baton.md>", file=sys.stderr)
        return 2
    path = Path(argv[1])
    text = path.read_text()
    violations = lint_baton(text)
    if violations:
        print(f"lint_baton: {len(violations)} violation(s) in {path}:", file=sys.stderr)
        for v in violations:
            print(f"  - {v}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
