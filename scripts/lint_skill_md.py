#!/usr/bin/env python3
"""Lint SKILL.md files for agentskills.io schema compliance.

Checks:
  - YAML frontmatter present and parses
  - `name` and `description` required
  - `description` ≤ 1536 chars (agentskills.io budget)
  - trigger keywords in first sentence of description
  - body has at least one section (## heading)
  - if EVAL.md is referenced, file exists
  - premortem contract (LEARNING_CONTRACT.md §8): a skill shipping a machine
    gate (tools/*.py or drift_probes.json) declares its failure modes and
    ships a negative test. WARN by default; --strict promotes to hard issues.
"""
from __future__ import annotations

import argparse
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

# LEARNING_CONTRACT.md §8 — premortem is part of shipping: a skill that ships
# a machine gate (tools/*.py or drift_probes.json) must declare how it fails
# silently, and a gate that never tripped is unproven (§3, negative test
# first). NEGATIVE_TEST_HINTS is a content signal, not a filename convention —
# the file must actually assert a known-bad/reject/adversarial case, not just
# be named test*.
FAILURE_MODES_HEADING_RE = re.compile(r"^##\s*failure modes\s*$", re.I | re.M)
PREMORTEM_MENTION_RE = re.compile(r"premortem", re.I)
NEGATIVE_TEST_HINTS = (
    "reject", "adversarial", "known-bad", "known bad", "should_fail", "should fail",
    "must_fail", "must fail", "bad case", "bad_case", "negative test", "negative_test",
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


def _ships_machine_gate(skill_dir: Path) -> bool:
    """A skill ships a machine gate if it has tools/*.py or drift_probes.json."""
    if (skill_dir / "drift_probes.json").exists():
        return True
    tools_dir = skill_dir / "tools"
    if tools_dir.is_dir():
        return any(tools_dir.glob("*.py"))
    return False


def _has_failure_modes_note(skill_dir: Path) -> bool:
    """§8: a declared failure-modes note — '## Failure modes' heading or a
    'premortem' mention — in SKILL.md or EVAL.md."""
    for name in ("SKILL.md", "EVAL.md"):
        p = skill_dir / name
        if not p.exists():
            continue
        text = p.read_text()
        if FAILURE_MODES_HEADING_RE.search(text) or PREMORTEM_MENTION_RE.search(text):
            return True
    return False


def _has_negative_test(skill_dir: Path) -> bool:
    """§3: a negative-test artifact — tools/test*.py or test*.sh whose content
    signals a known-bad/reject/adversarial case."""
    tools_dir = skill_dir / "tools"
    if not tools_dir.is_dir():
        return False
    candidates = list(tools_dir.glob("test*.py")) + list(tools_dir.glob("test*.sh"))
    for f in candidates:
        text_lc = f.read_text().lower()
        if any(h in text_lc for h in NEGATIVE_TEST_HINTS):
            return True
    return False


def lint_one(path: Path, strict: bool = False) -> tuple[list[str], list[str]]:
    issues: list[str] = []
    warnings: list[str] = []
    text = path.read_text()
    fm, body, fm_block = parse_frontmatter(text)
    if not fm:
        issues.append("missing YAML frontmatter")
        return issues, warnings
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
            return issues, warnings
        if not isinstance(loaded, dict):
            issues.append("frontmatter YAML did not parse to a mapping")
            return issues, warnings
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
    # Premortem contract (LEARNING_CONTRACT.md §8): a skill shipping a machine
    # gate must declare its failure modes and ship a negative test. WARN by
    # default so the repo stays green; --strict promotes both to hard issues.
    skill_dir = path.parent
    if _ships_machine_gate(skill_dir):
        findings: list[str] = []
        if not _has_failure_modes_note(skill_dir):
            findings.append(
                "ships a machine gate (tools/*.py or drift_probes.json) but has no "
                "declared failure-modes note (a case-insensitive '## Failure modes' "
                "heading or a 'premortem' mention in SKILL.md or EVAL.md) — see "
                "LEARNING_CONTRACT.md §8"
            )
        if not _has_negative_test(skill_dir):
            findings.append(
                "ships a machine gate (tools/*.py or drift_probes.json) but has no "
                "negative-test artifact (a tools/test*.py or test*.sh whose content "
                "signals a known-bad/reject/adversarial case) — see "
                "LEARNING_CONTRACT.md §3"
            )
        if strict:
            issues.extend(findings)
        else:
            warnings.extend(findings)
    return issues, warnings


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="lint.py", add_help=False)
    parser.add_argument("files", nargs="*")
    parser.add_argument(
        "--strict", action="store_true",
        help="promote premortem-contract findings (LEARNING_CONTRACT.md §8) from "
             "warnings to hard issues",
    )
    args = parser.parse_args(argv[1:])
    if not args.files:
        print("usage: lint.py [--strict] <SKILL.md> [...]", file=sys.stderr)
        return 2
    # In CI the strict-YAML gate (lines ~76) is the whole point — silently
    # degrading to the dependency-free path there would let malformed frontmatter
    # ship. Fail loudly so a missing dep is fixed, not ignored.
    if os.environ.get("CI") and yaml is None:
        print("ERROR: PyYAML is required in CI for strict SKILL.md frontmatter "
              "validation, but it is not installed.", file=sys.stderr)
        return 2
    rc = 0
    for arg in args.files:
        p = Path(arg)
        if not p.exists():
            print(f"{arg}: not found")
            rc = 1
            continue
        issues, warnings = lint_one(p, strict=args.strict)
        if issues:
            rc = 1
            print(f"{arg}: {len(issues)} issue(s)")
            for i in issues:
                print(f"  - {i}")
        elif not warnings:
            print(f"{arg}: ok")
        if warnings:
            print(f"{arg}: {len(warnings)} warning(s)")
            for w in warnings:
                print(f"  - [warn] {w}")
    return rc


if __name__ == "__main__":
    sys.exit(main(sys.argv))
