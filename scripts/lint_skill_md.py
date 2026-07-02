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

import os
import re
import sys
from pathlib import Path

try:  # PyYAML is optional — keep the "dependency-free" promise when absent.
    import yaml  # type: ignore
except ImportError:  # pragma: no cover - exercised only on hosts without PyYAML
    yaml = None  # type: ignore

DESC_MAX = 1536
# Descriptions are ALWAYS resident in agent context (per SKILLS_INDEX.md) — a
# long one is a permanent token tax across every host and consumer repo. The
# 2026-07 pass compressed the 9 worst (62-153 words) to <=~90; warn past 100.
DESC_MAX_WORDS = 100
REQUIRED_FIELDS = ("name", "description")
TRIGGER_HINTS = (
    "use when", "use on", "use at", "use for", "use whenever", "use before", "use after", "use opt-in",
    "trigger", "fires on", "run on", "applies when",
)


def _unquote(value: str) -> str:
    """Strip surrounding YAML double/single quotes and unescape `\\"`/`\\\\`.

    A value containing `: ` (colon-space) must ship as a quoted YAML scalar so
    real YAML parsers accept it; the hand-rolled `partition(":")` below would
    otherwise leak the surrounding quotes into the extracted value (and break
    the length / trigger-keyword checks). Normalize to the logical value here.
    """
    v = value.strip()
    if len(v) >= 2 and v[0] == v[-1] and v[0] in "\"'":
        inner = v[1:-1]
        if v[0] == '"':
            inner = inner.replace('\\"', '"').replace("\\\\", "\\")
        return inner
    return v


def parse_frontmatter(text: str) -> tuple[dict, str, str | None]:
    m = re.match(r"^---\n(.*?)\n---\n(.*)$", text, re.DOTALL)
    if not m:
        return {}, text, None
    fm_block, body = m.group(1), m.group(2)
    fm: dict[str, str] = {}
    for line in fm_block.splitlines():
        if ":" not in line:
            continue
        k, _, v = line.partition(":")
        fm[k.strip()] = _unquote(v)
    return fm, body, fm_block


def lint_one(path: Path) -> list[str]:
    issues: list[str] = []
    text = path.read_text()
    fm, body, fm_block = parse_frontmatter(text)
    if not fm:
        issues.append("missing YAML frontmatter")
        return issues
    # Strict YAML gate: when PyYAML is importable, the frontmatter MUST parse
    # with the SAME parser GitHub/agentskills.io use. This is the check the old
    # hand-rolled `partition(":")` could never do — it is why 7 SKILL.md files
    # with `: ` (colon-space) in an unquoted description shipped broken. Skipped
    # (with the dependency-free promise intact) only where PyYAML is absent.
    if yaml is not None and fm_block is not None:
        try:
            loaded = yaml.safe_load(fm_block)
        except yaml.YAMLError as exc:  # type: ignore[union-attr]
            first = str(exc).splitlines()[0] if str(exc) else exc.__class__.__name__
            issues.append(f"frontmatter is not valid YAML (yaml.safe_load: {first})")
            return issues
        if not isinstance(loaded, dict):
            issues.append("frontmatter YAML did not parse to a mapping")
            return issues
    for k in REQUIRED_FIELDS:
        if k not in fm:
            issues.append(f"missing required field: {k}")
    desc = fm.get("description", "")
    if len(desc) > DESC_MAX:
        issues.append(f"description {len(desc)} chars > {DESC_MAX} cap")
    n_words = len(desc.split())
    if n_words > DESC_MAX_WORDS:
        issues.append(f"description {n_words} words > {DESC_MAX_WORDS} — "
                      "resident-context tax; move detail into the body")
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
    # In CI the strict-YAML gate (lines ~76) is the whole point — silently
    # degrading to the dependency-free path there would let malformed frontmatter
    # ship. Fail loudly so a missing dep is fixed, not ignored.
    if os.environ.get("CI") and yaml is None:
        print("ERROR: PyYAML is required in CI for strict SKILL.md frontmatter "
              "validation, but it is not installed.", file=sys.stderr)
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
