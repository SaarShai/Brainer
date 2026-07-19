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


def source_order_errors(events: list[tuple[str, str]]) -> list[str]:
    """Require source-grounded final selection before task-specific work."""
    sources_read: set[str] = set()
    for kind, value in events:
        if kind == "source_read":
            sources_read.add(value)
            continue
        if kind == "task_work":
            return ["task work preceded final selection"]
        if kind != "selection":
            continue
        identifiers = [item.strip() for item in value.split(",")]
        selected_skills = {
            item.split(":", 1)[0] for item in identifiers if item != "none"
        }
        missing = sorted(selected_skills - sources_read)
        return [f"selection preceded source read: {name}" for name in missing]
    return ["final selection missing"]


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

    def test_selection_follows_every_shortlisted_source_read(self) -> None:
        events = [
            ("source_read", "think"),
            ("selection", "think:borrow-before-building, think:falsify"),
            ("task_work", "inspect routing machinery"),
        ]
        self.assertEqual([], source_order_errors(events))

    def test_selection_before_source_read_is_rejected(self) -> None:
        events = [
            ("selection", "think:borrow-before-building, think:falsify"),
            ("source_read", "think"),
        ]
        errors = source_order_errors(events)
        self.assertEqual(["selection preceded source read: think"], errors)

    def test_no_skill_selection_needs_no_source_read(self) -> None:
        self.assertEqual([], source_order_errors([("selection", "none")]))

    def test_task_work_before_selection_is_rejected(self) -> None:
        events = [
            ("source_read", "think"),
            ("task_work", "inspect routing machinery"),
            ("selection", "think:borrow-before-building"),
        ]
        self.assertEqual(
            ["task work preceded final selection"], source_order_errors(events)
        )

    def test_consumer_verification_marks_missing_checks_unavailable(self) -> None:
        text = SKILL.read_text(encoding="utf-8")
        self.assertIn('echo "NOT AVAILABLE: $check"', text)
        self.assertIn("`NOT AVAILABLE` is not a pass", text)


if __name__ == "__main__":
    unittest.main(verbosity=2)
