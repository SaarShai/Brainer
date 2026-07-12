#!/usr/bin/env python3
"""Deterministic schema and coverage tests for exp8_trigger."""
from __future__ import annotations

import subprocess
import sys
import unittest
from pathlib import Path

import run_trigger as trigger

HERE = Path(__file__).resolve().parent


class TriggerCasesTest(unittest.TestCase):
    def test_primary_targets_exactly_cover_live_skills_once(self) -> None:
        targets = [target for _, target in trigger.TARGET_CASES]
        self.assertEqual(len(targets), len(set(targets)))
        self.assertEqual(set(targets), trigger.live_skill_names())
        self.assertEqual(trigger.live_skill_names(), {name for name, _ in trigger.load_catalog()})
        self.assertEqual(28, len(targets))

    def test_old_14_case_fixture_fails_current_coverage_assertion(self) -> None:
        errors = trigger.validate_cases(target_cases=trigger.TARGET_CASES[:14])
        self.assertTrue(any("target coverage mismatch" in error for error in errors))

    def test_primary_cases_are_target_specific(self) -> None:
        live = trigger.live_skill_names()
        for _, target in trigger.TARGET_CASES:
            companion = next(name for name in live if name != target)
            self.assertTrue(trigger.case_matches(target, (target,)))
            self.assertFalse(trigger.case_matches(companion, (target,)))

    def test_manual_only_targets_retain_literal_slash_boundary(self) -> None:
        prompts = {target: prompt for prompt, target in trigger.TARGET_CASES}
        for target in ("think", "baton"):
            with self.subTest(target=target):
                self.assertRegex(prompts[target], rf"^/{target}(?:\s|$)")

    def test_composition_schema_and_names(self) -> None:
        live = trigger.live_skill_names()
        self.assertGreater(len(trigger.COMPOSITION_CASES), 0)
        for prompt, accepted in trigger.COMPOSITION_CASES:
            self.assertTrue(prompt.strip())
            self.assertIsInstance(accepted, tuple)
            self.assertGreaterEqual(len(accepted), 2)
            self.assertEqual(len(accepted), len(set(accepted)))
            self.assertLessEqual(set(accepted), live)
        self.assertEqual([], trigger.validate_cases())

    def test_validator_reports_malformed_case_shapes(self) -> None:
        errors = trigger.validate_cases(
            target_cases=[("only-a-prompt",)],
            composition_cases=[("only-a-prompt",)],
        )
        self.assertTrue(any("target 0 must be" in error for error in errors))
        self.assertTrue(any("composition 0 must be" in error for error in errors))

    def test_validator_rejects_unhashable_composition_entries(self) -> None:
        for bad_entry in (["write-gate"], {"skill": "wiki-memory"}):
            with self.subTest(bad_entry=bad_entry):
                errors = trigger.validate_cases(
                    composition_cases=[("remember this", ("write-gate", bad_entry))],
                )
                self.assertIn(
                    "composition 0 accepted skills must be non-empty strings", errors,
                )

    def test_validator_rejects_mixed_or_empty_composition_entries(self) -> None:
        for bad_entry in (7, None, "", "   "):
            with self.subTest(bad_entry=bad_entry):
                errors = trigger.validate_cases(
                    composition_cases=[("remember this", ("write-gate", bad_entry))],
                )
                self.assertIn(
                    "composition 0 accepted skills must be non-empty strings", errors,
                )

    def test_validate_only_cli_never_needs_a_model(self) -> None:
        result = subprocess.run(
            [sys.executable, str(HERE / "run_trigger.py"), "--validate-only"],
            cwd=HERE, capture_output=True, text=True, timeout=10,
        )
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn("PASS targets=28 compositions=3 live=28", result.stdout)


if __name__ == "__main__":
    unittest.main()
