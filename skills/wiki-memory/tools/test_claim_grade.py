from __future__ import annotations

"""Accuracy harness + gold corpus for claim_grade.py.

Gold labels drawn from real PROMPTER + Brainer claim shapes plus synthetic edge
cases and the false-positive traps surfaced in research (causal-but-empirical,
hedged-soft-decision, first-person-taste-vs-prefer-rule). Thresholds are the
falsification bar: a change to claim_grade.py that drops below them is a
regression and must not ship.

Run: python3 skills/wiki-memory/tools/test_claim_grade.py
"""

import sys
import unittest
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from claim_grade import grade_claim, KLASS  # noqa: E402

# (text, expected_fine_type)
GOLD: list[tuple[str, str]] = [
    # --- observation (empirical / measured / dated / factual locator) ---
    ("prompt-triage hook latency measured ~113ms on the regex path", "observation"),
    ("Installed gog CLI v0.16.0 and verified the Darwin arm64 checksum", "observation"),
    ("12 deterministic tests passed with no network calls", "observation"),
    ("The build took 4.2s on the first cold run", "observation"),
    ("On 2026-06-12 the classifier returned None for every LLM fallback", "observation"),
    ("overlap() lives at wiki.py:1536 and only detects duplication", "observation"),
    ("The export produced 163 concepts and validated with 0 invalid blocks", "observation"),
    ("Qwen3.6 35B is marked experimental in the upstream README", "observation"),
    ("the test failed because the path was wrong", "observation"),          # causal != decision (trap)
    ("looking-forward-to-it is a sub-principle of enjoy, not a fifth principle", "observation"),
    ("overall cache hit ratio across the 8 sessions was 0.9477", "observation"),
    ("the M1 disk is 100% full with 119MB free", "observation"),
    # --- decision (a choice was committed) ---
    ("We decided to fail closed when complex hints appear and no LLM is available", "decision"),
    ("Chose qwen2.5:7b as the fallback after the corpus run", "decision"),
    ("Switched the hook to keep_alive=2h", "decision"),
    ("Deprecated the old tokens.py clones in favor of the wiki-memory copy", "decision"),
    ("We are going with rsync for sibling sync", "decision"),
    ("Adopted the why-clause requirement from codenamev claude_memory", "decision"),
    ("Standardized on the closed type enum plus write-gate", "decision"),
    ("Settled on a one-way export-okf serializer, no import", "decision"),
    # --- rule (normative / conditional / directive) ---
    ("Always retrieve before reasoning about stored facts", "rule"),
    ("Do not praise questions or validate premises before answering", "rule"),
    ("Never promote a page to verified via reuse alone", "rule"),
    ("If the prompt has complex hints and no LLM, then defer to the main model", "rule"),
    ("Prefer updating an existing page over creating a new one", "rule"),     # prefer-over directive (trap vs opinion)
    ("raw/ must never be rewritten after creation", "rule"),
    ("The assistant recommends; the user decides", "rule"),
    ("Run decay weekly, never per-prompt", "rule"),
    ("Verification subagents should default to a sonnet-class model", "rule"),
    ("Resolve conflicts in this order: current request first, then durable preferences", "rule"),
    ("Use this checklist before any tool use with side effects", "rule"),
    ("Cite page IDs or paths in answers and durable notes", "rule"),
    ("Prompt generation: retrieve the relevant pages before composing", "rule"),
    ("In coach mode, hold it and ask first before proceeding", "rule"),
    # --- hypothesis (tentative / uncertain) ---
    ("This might be flaky under high concurrency", "hypothesis"),
    ("The latency spike is probably caused by cold model load", "hypothesis"),
    ("It seems the BOM prefix breaks the frontmatter parser", "hypothesis"),
    ("We may need a separate maturity axis distinct from trust", "hypothesis"),
    ("I suspect the regex backtracks on long slash-runs", "hypothesis"),
    ("Could be that PyYAML normalizes the list differently than our parser", "hypothesis"),
    ("We might adopt OKF as an export format", "hypothesis"),                  # hedged soft-decision (trap)
    ("Perhaps the canary should fire on shorter windows", "hypothesis"),
    # --- opinion (subjective evaluation, no evidence) ---
    ("The caveman style reads cleaner", "opinion"),
    ("This API is ugly", "opinion"),
    ("I prefer tabs over spaces", "opinion"),                                  # first-person taste (trap vs rule)
    ("The output feels too verbose", "opinion"),
    ("Spaces are nicer than tabs", "opinion"),
    ("This is the best approach", "opinion"),
    ("The new layout is more readable", "opinion"),
]

# named traps that MUST classify correctly (regression locks)
TRAPS = {
    "the test failed because the path was wrong": "observation",
    "We might adopt OKF as an export format": "hypothesis",
    "I prefer tabs over spaces": "opinion",
    "Prefer updating an existing page over creating a new one": "rule",
}

# Honest precision/coverage bars (abstention `unknown` counts against coverage,
# NOT against precision — high precision on emitted types is the goal; recall is
# secondary; see the blind-validation finding in claim_grade.py).
PRECISION_MIN = 0.88
COVERAGE_MIN = 0.75


class TestClaimGrade(unittest.TestCase):
    def _predict(self):
        return [(t, exp, grade_claim(t)["type"]) for t, exp in GOLD]

    def test_precision_when_confident(self):
        preds = self._predict()
        emitted = [(t, exp, got) for t, exp, got in preds if got != "unknown"]
        correct = sum(1 for _, exp, got in emitted if exp == got)
        prec = correct / len(emitted) if emitted else 0.0
        if prec < PRECISION_MIN:
            wrong = [f"\n  {exp:11s} != {got:11s} :: {t[:60]}" for t, exp, got in emitted if exp != got]
            self.fail(f"precision {prec:.3f} < {PRECISION_MIN} ({correct}/{len(emitted)} emitted)" + "".join(wrong))

    def test_coverage(self):
        preds = self._predict()
        emitted = sum(1 for _, _, got in preds if got != "unknown")
        cov = emitted / len(preds)
        if cov < COVERAGE_MIN:
            abst = [f"\n  abstained on {exp:11s} :: {t[:60]}" for t, exp, got in preds if got == "unknown"]
            self.fail(f"coverage {cov:.3f} < {COVERAGE_MIN} ({emitted}/{len(preds)})" + "".join(abst))

    def test_coarse_klass_precision(self):
        # data / directive / judgment roll-up on emitted — what contradiction
        # type-awareness needs.
        preds = self._predict()
        emitted = [(exp, got) for _, exp, got in preds if got != "unknown"]
        correct = sum(1 for exp, got in emitted if KLASS[exp] == KLASS[got])
        acc = correct / len(emitted) if emitted else 0.0
        self.assertGreaterEqual(acc, 0.88, f"coarse klass precision {acc:.3f} < 0.88")

    def test_named_traps(self):
        for text, exp in TRAPS.items():
            got = grade_claim(text)["type"]
            self.assertEqual(got, exp, f"trap misclassified: {text!r} -> {got} (want {exp})")

    def test_no_redos_on_long_unpunctuated_input(self):
        # bounded regexes + length cap: pathological input must not hang (was 42s)
        import time
        t = time.time()
        grade_claim("if " * 50000)
        grade_claim("when " * 40000)
        from claim_grade import grade_text
        grade_text("if when " * 30000)
        self.assertLess(time.time() - t, 1.0)

    def test_non_str_and_noise_inputs(self):
        # defensive coercion + non-alpha abstain (no crash on wrong types)
        self.assertEqual(grade_claim(123)["type"], "unknown")
        self.assertEqual(grade_claim("0 0 100% 9ms 42 ...")["type"], "unknown")
        self.assertEqual(grade_claim(None)["type"], "unknown")

    def test_orthogonal_to_truth(self):
        # a confident WRONG claim still grades by form, not truth
        self.assertEqual(grade_claim("The build took 999999ms")["type"], "observation")
        self.assertEqual(grade_claim("Always do the wrong thing")["type"], "rule")


if __name__ == "__main__":
    unittest.main(verbosity=2)
