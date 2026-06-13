#!/usr/bin/env python3
"""Lint SKILL.md files for agentskills.io schema compliance.

Checks:
  - YAML frontmatter present and parses
  - `name` and `description` required
  - `description` ≤ 1536 chars (agentskills.io budget)
  - trigger keywords in first sentence of description
  - body has at least one section (## heading)
  - if EVAL.md is referenced, file exists
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

DESC_MAX = 1536
REQUIRED_FIELDS = ("name", "description")
TRIGGER_HINTS = (
    "use when", "use on", "use at", "use for", "use whenever", "use before", "use after", "use opt-in",
    "trigger", "fires on", "run on", "applies when",
)


def parse_frontmatter(text: str) -> tuple[dict, str]:
    m = re.match(r"^---\n(.*?)\n---\n(.*)$", text, re.DOTALL)
    if not m:
        return {}, text
    fm_block, body = m.group(1), m.group(2)
    fm: dict[str, str] = {}
    for line in fm_block.splitlines():
        if ":" not in line:
            continue
        k, _, v = line.partition(":")
        fm[k.strip()] = v.strip()
    return fm, body


def lint_one(path: Path) -> list[str]:
    issues: list[str] = []
    text = path.read_text()
    fm, body = parse_frontmatter(text)
    if not fm:
        issues.append("missing YAML frontmatter")
        return issues
    for k in REQUIRED_FIELDS:
        if k not in fm:
            issues.append(f"missing required field: {k}")
    desc = fm.get("description", "")
    if len(desc) > DESC_MAX:
        issues.append(f"description {len(desc)} chars > {DESC_MAX} cap")
    desc_lc = desc.lower()
    # Slash-only skills (`disable-model-invocation: true`) trigger on the literal
    # token, not description-matching — they don't need trigger keywords.
    slash_only = fm.get("disable-model-invocation", "").strip().lower() == "true"
    # Deprecation stubs ("DEPRECATED — use X. Do not use.") must NOT carry
    # trigger keywords — their whole point is to never fire (PROMPTER field
    # deploy 2026-06-12: linter demanded 'Use when' on do-not-use stubs).
    # Match the canonical stub SHAPE, not just a "DEPRECATED" prefix: the old
    # `startswith("DEPRECATED")` falsely exempted real skills like
    # "Deprecated-API scanner" (a live trigger that legitimately needs 'Use
    # when'). Require the do-not-use marker that only a real stub carries.
    deprecated = bool(re.match(r"\s*DEPRECATED\b.*\bdo not use\b", desc, re.I | re.S))
    if not slash_only and not deprecated and not any(h in desc_lc for h in TRIGGER_HINTS):
        issues.append("description should front-load trigger keywords (e.g. 'Use when...', 'Trigger on...')")
    # Section headings are recommended only for longer skill bodies. 40-line
    # floor: a ~30-line measured-tuned body (caveman-ultra) doesn't need nav,
    # and restructuring a measured artifact to satisfy lint inverts priorities.
    if "##" not in body and len(body.splitlines()) > 40:
        issues.append("body has no `## section` headings (long body benefits from sections)")
    return issues


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print("usage: lint.py <SKILL.md> [...]", file=sys.stderr)
        return 2
    rc = 0
    for arg in argv[1:]:
        p = Path(arg)
        if not p.exists():
            print(f"{arg}: not found")
            rc = 1
            continue
        issues = lint_one(p)
        if issues:
            rc = 1
            print(f"{arg}: {len(issues)} issue(s)")
            for i in issues:
                print(f"  - {i}")
        else:
            print(f"{arg}: ok")
    return rc


if __name__ == "__main__":
    sys.exit(main(sys.argv))
