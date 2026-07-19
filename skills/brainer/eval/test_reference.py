#!/usr/bin/env python3
from __future__ import annotations

import re
import unittest
from pathlib import Path


HERE = Path(__file__).resolve().parent
SKILL_DIR = HERE.parent
REPO = SKILL_DIR.parents[1]
REFERENCE = SKILL_DIR / "REFERENCE.md"
SKILL = SKILL_DIR / "SKILL.md"
VALID_MODES = {"method", "whole", "authority-gated"}
THINK_EXPORTS = {
    "truth-before-fluency", "truth-before-agreement", "goal-before-solution",
    "smallest-safe-intervention", "first-principles", "borrow-before-building",
    "actual-constraint", "ranges-and-thresholds", "diverge-before-converging",
    "causal-tree", "pre-mortem", "falsify", "structural-analogy", "research",
    "package-repetition",
}
SELECTION_LINE = re.compile(
    r"^Brainer selection: (?:none|[a-z0-9-]+:(?:whole|[a-z0-9-]+)"
    r"(?:, [a-z0-9-]+:(?:whole|[a-z0-9-]+))*)$"
)


def slugify_heading(value: str) -> str:
    value = value.strip().lower()
    value = re.sub(r"[^\w\- ]", "", value)
    return re.sub(r"[ ]+", "-", value)


def headings(path: Path) -> set[str]:
    found: set[str] = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        match = re.match(r"^#{1,6}\s+(.+?)\s*$", line)
        if match:
            found.add(slugify_heading(match.group(1)))
    return found


def reference_errors(text: str) -> list[str]:
    errors: list[str] = []
    links = re.findall(r"\]\((\.\./[^)#]+/SKILL\.md)#([^)]+)\)", text)
    if not links:
        errors.append("no indexed skill anchors")
    for relative, anchor in links:
        target = (SKILL_DIR / relative).resolve()
        if not target.is_file():
            errors.append(f"missing source: {relative}")
            continue
        if anchor not in headings(target):
            errors.append(f"missing heading: {relative}#{anchor}")

    modes = re.findall(r"\]\([^)]+\) \| `([^`]+)` \|", text)
    unknown = sorted(set(modes) - VALID_MODES)
    if unknown:
        errors.append(f"unknown modes: {unknown}")
    if not VALID_MODES.issubset(set(modes)):
        errors.append("all three selection modes must be represented")
    return errors


def selection_trace_errors(events: list[tuple[str, str]]) -> list[str]:
    """Grade the initial /brainer gate; routing reads are the only prelude."""
    errors: list[str] = []
    declaration_seen = False
    for kind, payload in events:
        if kind == "selection":
            if not SELECTION_LINE.fullmatch(payload):
                errors.append("selection declaration has invalid identifier grammar")
            declaration_seen = True
            break
        if kind != "routing_read":
            errors.append(f"task work preceded selection: {kind}")
            break
    if not declaration_seen:
        errors.append("selection declaration missing before task work")
    return errors


class BrainerReferenceTests(unittest.TestCase):
    def test_all_sources_and_headings_are_live(self) -> None:
        self.assertEqual(reference_errors(REFERENCE.read_text(encoding="utf-8")), [])

    def test_broken_anchor_negative_fixture_is_rejected(self) -> None:
        text = REFERENCE.read_text(encoding="utf-8")
        broken = text.replace("#exported-methods-for-brainer", "#not-a-real-heading", 1)
        errors = reference_errors(broken)
        self.assertTrue(any("not-a-real-heading" in item for item in errors), errors)

    def test_both_explicit_triggers_and_authority_boundary_exist(self) -> None:
        text = SKILL.read_text(encoding="utf-8")
        self.assertIn("/brainer", text)
        self.assertIn("use any relevant/helpful Brainer skill", text)
        self.assertIn("does **not** independently authorize", text)
        self.assertIn("An empty shortlist is valid", text)

    def test_method_export_and_exclusion_classes_are_explicit(self) -> None:
        text = REFERENCE.read_text(encoding="utf-8")
        think = (REPO / "skills" / "think" / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("../think/SKILL.md#exported-methods-for-brainer", text)
        for export_id in THINK_EXPORTS:
            self.assertIn(f"`{export_id}`", think)
            self.assertIn(f"`{export_id}`", text)
        for name in (
            "caveman-ultra", "fable-mode", "prompt-triage",
            "requirements-ledger", "standing-orders", "compliance-canary",
            "context-keeper", "semantic-diff", "wiki-memory", "write-gate",
        ):
            self.assertIn(f"`{name}`", text)

    def test_final_selection_identifiers_are_unambiguous(self) -> None:
        text = SKILL.read_text(encoding="utf-8")
        reference = REFERENCE.read_text(encoding="utf-8")
        self.assertIn("`<skill>:<export-id>`", text)
        self.assertIn("`<skill>:whole`", text)
        self.assertIn("bare skill name is not", text)
        self.assertIn("task text following `/brainer` is still user authority", text)
        self.assertIn("selects `propagate:whole`", reference)

    def test_selection_declaration_precedes_task_work(self) -> None:
        good = [
            ("routing_read", "skills/brainer/REFERENCE.md"),
            ("routing_read", "skills/think/SKILL.md"),
            ("selection", "Brainer selection: think:borrow-before-building, think:falsify"),
            ("task_tool", "rg routing"),
        ]
        self.assertEqual([], selection_trace_errors(good))

    def test_task_investigation_before_selection_is_rejected(self) -> None:
        bad = [
            ("task_tool", "pwd && sed -n 1,240p start.md"),
            ("selection", "Brainer selection: think:borrow-before-building"),
        ]
        errors = selection_trace_errors(bad)
        self.assertTrue(any("task work preceded selection" in item for item in errors))

    def test_bare_skill_selection_is_rejected(self) -> None:
        errors = selection_trace_errors([
            ("selection", "Brainer selection: think"),
        ])
        self.assertTrue(any("invalid identifier grammar" in item for item in errors))


if __name__ == "__main__":
    unittest.main(verbosity=2)
