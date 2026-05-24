#!/usr/bin/env python3
"""prompt-triage classification calibration.

Labeled corpus of (prompt, expected tier) pairs. Tests:
  - simple tasks route to haiku
  - complex tasks DO NOT route to haiku (regression for the broad-regex bug)
  - long stack-trace prompts ending with an imperative classify on the imperative
    (regression for the 800-char truncation bug)
  - ollama fallback is bypassed in tests (deterministic, no daemon needed)

Bug regression blocks (M2/M5/L3/H1) live in `_extra_regression_checks`.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _lib import LabeledCase, Report, Timer, calibration_metrics, print_report, write_report, REPO  # noqa: E402

sys.path.insert(0, str(REPO / "skills/prompt-triage/tools"))
import classify as triage_mod  # noqa: E402


# Each case: prompt → expected MODEL family.
# "haiku" or "local:*" means cheap-OK; "sonnet" or "opus" means escalate.
CASES: list[LabeledCase] = [
    # --- Simple → haiku/local (cheap-OK) ---
    LabeledCase("simple_typo", inputs=("fix this typo in the readme",), expected="haiku"),
    LabeledCase("simple_commit", inputs=("commit and push",), expected="haiku"),
    LabeledCase("simple_factual", inputs=("what is the gini coefficient",), expected="haiku"),
    LabeledCase("simple_wiki_add", inputs=("add a note to wiki that we use pgvector",), expected="haiku"),
    LabeledCase("simple_install", inputs=("install ruff",), expected="haiku"),
    LabeledCase("simple_summarize_local", inputs=("summarize this paragraph for me",), expected="local:qwen3:8b"),
    LabeledCase("simple_git_stash", inputs=("git stash",), expected="haiku"),
    LabeledCase("simple_explicit_local", inputs=("use ollama to translate this string",), expected="local:qwen3:8b"),

    # --- Complex → must NOT route to haiku (REGRESSION FOR C3) ---
    LabeledCase("complex_audit_markdown",
                inputs=("write me a comprehensive markdown audit of my codebase",),
                expected="not_haiku"),
    LabeledCase("complex_refactor",
                inputs=("refactor the auth module across all services",),
                expected="opus"),
    LabeledCase("complex_architect",
                inputs=("design the new event-bus architecture for our backend",),
                expected="opus"),
    LabeledCase("complex_review",
                inputs=("review and critique the PR I just opened",),
                expected="not_haiku"),
    LabeledCase("complex_debug",
                inputs=("debug why the production queue is hanging",),
                expected="not_haiku"),
    LabeledCase("complex_long_request",
                inputs=("Help me think through this. " * 80,),  # ~2000 chars
                expected="not_haiku"),
    LabeledCase("complex_thorough",
                inputs=("do a thorough analysis of the failure modes in our auth flow",),
                expected="not_haiku"),
    LabeledCase("complex_investigation",
                inputs=("investigate the root cause of the data inconsistency",),
                expected="not_haiku"),

    # --- Long-context with imperative at end (REGRESSION FOR C4) ---
    # If we truncate to 800 chars, we miss the "fix this" at the end.
    LabeledCase("long_stack_trace_with_imperative",
                inputs=(("Traceback (most recent call last):\n" +
                         "  File \"foo.py\", line 1, in <module>\n" * 200 +
                         "ValueError: bad\n" +
                         "fix this please"),),
                expected="not_haiku"),

    # --- Edge cases ---
    LabeledCase("empty_prompt", inputs=("",), expected="opus"),  # falls through to default
    LabeledCase("research_task",
                inputs=("research the best vector DB options for our scale",),
                expected="sonnet"),

    # --- M2 regression: summarize rule must point at a real Ollama model.
    # gemma4:26b is not a published tag; we now route to qwen3:8b.
    LabeledCase("simple_summarize_tldr", inputs=("tldr this log please",), expected="local:qwen3:8b"),
    LabeledCase("simple_summarize_condense", inputs=("condense this article",), expected="local:qwen3:8b"),
]


def classify_one(case: LabeledCase) -> str:
    """Run classifier without ollama fallback (deterministic, no daemon needed)."""
    result = triage_mod.classify(case.inputs[0], use_ollama_fallback=False)
    return result.get("model", "opus")


def grade(expected: str, actual: str) -> bool:
    if expected == "not_haiku":
        return actual != "haiku"
    if expected == actual:
        return True
    # Allow "haiku" expectation to be satisfied by "local:*" (both cheap-OK)
    if expected == "haiku" and actual.startswith("local:"):
        return True
    if expected.startswith("local:") and actual == "haiku":
        return True
    return False


def _extra_regression_checks() -> list[dict]:
    """Targeted checks for non-corpus-shaped bugs (M5 JSON extraction, L3 bypass
    anchoring, H1 single-process hook end-to-end). Each row mirrors the corpus
    row shape: {label, prompt_preview, expected, actual, correct}.
    """
    rows: list[dict] = []

    # --- L3: bypass regex anchoring ---
    bypass_cases = [
        ("L3_bypass_no_triage_anywhere",      "fix this NO TRIAGE",                True),
        ("L3_bypass_no_dash_triage",          "NO-TRIAGE just run",                True),
        ("L3_bypass_no_underscore_triage",    "please NO_TRIAGE here",             True),
        ("L3_bypass_slash_opus_at_start",     "/opus help me think",               True),
        ("L3_bypass_slash_opus_leading_ws",   "   /opus do thing",                 True),
        # Anti-bypass: /opus inside paths must NOT trigger
        ("L3_no_bypass_path_segment",         "git log /opus/file.md",             False),
        ("L3_no_bypass_url",                  "see https://x.com/opus/page",       False),
        ("L3_no_bypass_substring",            "the word slashopus is not bypass",  False),
        ("L3_no_bypass_filename",             "open ./opus.txt",                   False),
    ]
    for label, prompt, expected_bypass in bypass_cases:
        actual = triage_mod.is_bypass(prompt)
        rows.append({
            "label": label,
            "prompt_preview": prompt[:60],
            "expected": f"bypass={expected_bypass}",
            "actual": f"bypass={actual}",
            "correct": actual == expected_bypass,
        })

    # --- M5: robust JSON extraction from noisy LLM output ---
    extract = triage_mod._extract_json_obj
    json_cases = [
        # (label, llm_response_text, expected_dict_keys_subset_or_None)
        ("M5_pure_json",
         '{"tier":"simple","agent":"quick-fix","model":"haiku","confidence":0.8}',
         {"tier": "simple"}),
        ("M5_prose_with_real_json",
         'Sure, here is your answer:\n{"tier":"simple","model":"haiku"}\nThat is it.',
         {"tier": "simple"}),
        ("M5_stray_brace_decoy",
         'the result is {tier:simple} but real JSON is {"tier":"medium","model":"sonnet"}',
         {"tier": "medium"}),
        ("M5_braces_inside_string",
         '{"tier":"simple","reason":"contains } stray brace { in text","model":"haiku"}',
         {"tier": "simple", "reason": "contains } stray brace { in text"}),
        ("M5_nested",
         '{"tier":"hard","extra":{"a":1,"b":[1,2]},"model":"opus"}',
         {"tier": "hard"}),
        ("M5_no_json",
         "I cannot classify this — sorry.",
         None),
        ("M5_empty",
         "",
         None),
        ("M5_unbalanced",
         "{ not closed",
         None),
    ]
    for label, text, expected in json_cases:
        got = extract(text)
        if expected is None:
            ok = got is None
            actual_s = "None" if got is None else f"got={got}"
        else:
            ok = isinstance(got, dict) and all(got.get(k) == v for k, v in expected.items())
            actual_s = f"got={got}"
        rows.append({
            "label": label,
            "prompt_preview": text[:60].replace("\n", " "),
            "expected": "None" if expected is None else f"keys⊇{expected}",
            "actual": actual_s,
            "correct": ok,
        })

    # --- H1: hook.sh end-to-end via single python process ---
    # Verifies the hook produces the expected directive block AND obeys bypass.
    hook_path = REPO / "skills/prompt-triage/tools/hook.sh"
    env = dict(os.environ, AGENTS_TRIAGE_NO_OLLAMA="1")

    def run_hook(payload: dict) -> str:
        proc = subprocess.run(
            ["bash", str(hook_path)],
            input=json.dumps(payload),
            capture_output=True, text=True, env=env, timeout=10,
        )
        return proc.stdout

    h1_cases = [
        # (label, payload, expected_substring_or_None, must_be_empty)
        ("H1_hook_simple_classifies",
         {"prompt": "fix this typo in the readme"},
         "agents-triage", False),
        ("H1_hook_simple_emits_json_tier",
         {"prompt": "fix this typo in the readme"},
         '"tier": "simple"', False),
        ("H1_hook_bypass_no_triage",
         {"prompt": "NO TRIAGE just run it"},
         None, True),
        ("H1_hook_bypass_slash_opus",
         {"prompt": "/opus think hard"},
         None, True),
        ("H1_hook_no_bypass_path_segment",
         # git log /opus/file.md → classifier returns agent=none which suppresses
         # directive; the important thing is bypass did NOT fire (stdout is empty
         # via the agent=none path, not via the bypass early exit).
         {"prompt": "git log /opus/file.md"},
         None, True),
        ("H1_hook_complex_audit_not_haiku",
         {"prompt": "write me a comprehensive markdown audit of my codebase"},
         '"model": "haiku"', None),  # special: must NOT contain
        ("H1_hook_malformed_stdin_no_crash",
         {},  # missing prompt
         None, True),
    ]
    for label, payload, needle, must_empty in h1_cases:
        try:
            out = run_hook(payload)
        except Exception as e:
            rows.append({
                "label": label, "prompt_preview": str(payload)[:60],
                "expected": "no crash", "actual": f"exception: {e}", "correct": False,
            })
            continue
        if must_empty is True:
            ok = out.strip() == ""
            actual_s = f"stdout-empty={ok}"
            exp_s = "empty stdout"
        elif must_empty is None:  # "must NOT contain needle"
            ok = needle not in out
            actual_s = f"contains_needle={needle in out}"
            exp_s = f"stdout NOT containing {needle!r}"
        else:
            ok = needle in out
            actual_s = f"contains_needle={needle in out}"
            exp_s = f"stdout contains {needle!r}"
        rows.append({
            "label": label, "prompt_preview": str(payload)[:60],
            "expected": exp_s, "actual": actual_s, "correct": ok,
        })

    return rows


def main() -> int:
    t = Timer()
    rows = []
    for c in CASES:
        actual = classify_one(c)
        correct = grade(c.expected, actual)
        rows.append({
            "label": c.label,
            "prompt_preview": c.inputs[0][:60] + ("…" if len(c.inputs[0]) > 60 else ""),
            "expected": c.expected,
            "actual": actual,
            "correct": correct,
        })

    # Append targeted regression checks (M5, L3, H1).
    rows.extend(_extra_regression_checks())

    # Build binary-style metrics: correct or not
    n = len(rows)
    correct = sum(1 for r in rows if r["correct"])
    metrics = {"n": n, "correct": correct, "accuracy": round(correct / n, 3)}

    # Critical-class assertions: zero false-cheap-route on complex tasks
    complex_cases = [r for r in rows if r["expected"] in ("not_haiku", "opus", "sonnet")]
    cheap_routed_complex = [r for r in complex_cases if r["actual"] == "haiku"]
    metrics["complex_cases"] = len(complex_cases)
    metrics["complex_misrouted_to_haiku"] = len(cheap_routed_complex)

    report = Report(skill="prompt_triage", shape="corpus",
                    elapsed_s=t.elapsed(), summary=metrics)
    report.findings = [r for r in rows if not r["correct"]]
    report.passed = (
        metrics["accuracy"] >= 0.90 and
        metrics["complex_misrouted_to_haiku"] == 0  # hard constraint
    )
    print_report(report)
    if report.findings:
        print("\nmisclassifications:")
        for r in report.findings:
            print(f"  [{r['label']:<30}]  expected={r['expected']:<12} actual={r['actual']:<20} "
                  f"prompt={r['prompt_preview']}")
    path = write_report(report)
    print(f"\nfull JSON: {path}")
    if metrics["complex_misrouted_to_haiku"] > 0:
        print(f"\nFAIL: {metrics['complex_misrouted_to_haiku']} complex task(s) routed to haiku — regression on C3.")
    return 0 if report.passed else 1


if __name__ == "__main__":
    sys.exit(main())
