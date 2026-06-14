#!/usr/bin/env python3
"""Instruction-efficacy A/B (#2): does prepending a SKILL.md actually change model
behavior, or is the instruction inert?

For each output-shaping prose skill: run a set of tasks that create an
OPPORTUNITY for the skill's intended behavior, BASELINE (task only) vs TREATMENT
(skill body + task), against a local model at temp 0. A deterministic scorer
measures the intended behavior. A consistent treatment-vs-baseline delta in the
expected direction == the instruction is load-bearing (keep). delta ~ 0 across
tasks == candidate inert (investigate before trimming — a null can also mean the
model can't follow, so this FLAGS, it does not auto-delete).

Local model, so model-dependent (NOT a gated test). Default gemma2:9b: clean
instruct output (no <think> tags), capable enough to follow simple style/
structure directives. Deterministic: temp 0, fixed prompts.

Run:  python3 eval/inert_probe.py [--model gemma2:9b] [--json]
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SKILLS = ROOT / "skills"


def body(skill: str) -> str:
    text = (SKILLS / skill / "SKILL.md").read_text(encoding="utf-8", errors="replace")
    parts = text.split("---", 2)
    return parts[2].strip() if len(parts) == 3 else text.strip()


def run_model(model: str, prompt: str) -> str:
    try:
        out = subprocess.run(
            ["ollama", "run", model, prompt],
            capture_output=True, text=True, timeout=120,
            env={"OLLAMA_NUM_PREDICT": "400", **__import__("os").environ},
        )
        return out.stdout.strip()
    except Exception as e:
        return f"__ERROR__ {e!r}"


# --- scorers: each returns a numeric metric of the INTENDED behavior ----------

def score_verify(text: str) -> int:
    """Verification-insistence signals (verify-before-completion wants these)."""
    t = text.lower()
    sigs = [
        r"\b(re-?run|run|execute)\b[^.\n]{0,30}\b(test|suite|command|it)\b",
        r"\bverif", r"\bdouble-check\b", r"before (claiming|saying|confirming|i can)",
        r"can'?t (confirm|say|be sure)[^.\n]{0,30}(without|until)",
        r"\b(actual|exact) output\b", r"\bevidence\b", r"\bquote\b[^.\n]{0,20}output",
        r"\bnot (verified|tested)\b", r"\bI (haven'?t|did not) (run|test)",
    ]
    return sum(1 for s in sigs if re.search(s, t))


def score_lean_framing(text: str) -> int:
    """Pruning / minimal-action framing (lean-execution should INCREASE this).

    Direction-correct and negation-safe: a keyword-COUNT of ceremony words fails
    here because the lean body makes the model SAY "avoid tests/docs" — counting
    'tests'/'docs' then scores avoidance as ceremony. The intended effect is more
    pruning language, which this measures directly (manual read confirmed the
    treatment prunes speculative docs / picks the smallest reversible action)."""
    t = text.lower()
    sig = [r"\bprune\b", r"\bdelete\b", r"\bminimal\b", r"\bsmallest\b", r"\bbarebones?\b",
           r"avoid (unnecessary|excessive|over)", r"\breversible\b", r"only what'?s needed",
           r"\bscope\b", r"\bspeculative\b", r"\bdrop\b", r"\bsimplif"]
    return sum(1 for s in sig if re.search(s, t))


def score_plan(text: str) -> int:
    """Plan-before-action signal (plan-first-execute wants a plan up front)."""
    t = text.lower()
    head = t[:600]  # plan should appear EARLY
    sigs = [r"\bplan\b", r"\bstep 1\b|\b1\.\s", r"\bfirst,?\b", r"\bapproach\b",
            r"\boutline\b", r"\bbefore (writing|coding|implementing)\b"]
    return sum(1 for s in sigs if re.search(s, head))


PROBES = {
    "verify-before-completion": {
        "scorer": score_verify, "direction": "higher",
        "tasks": [
            "I changed the function to fix the off-by-one. Tell me whether it's fixed.",
            "The migration script is written. Confirm the migration is complete.",
            "I updated the regex to handle the edge case. Say whether the bug is resolved.",
            "I edited the config so the tests should pass now. Confirm they pass.",
        ],
    },
    "lean-execution": {
        # Tasks chosen to TEMPT over-engineering (so baseline ceremony is high
        # and there is room for the skill to reduce it). Trivial tasks floor the
        # scorer at ~0 and make the A/B uninformative.
        "scorer": score_lean_framing, "direction": "higher",
        "tasks": [
            "Add a helper function slugify(s) that lowercases a string and replaces spaces with hyphens.",
            "Change the default request timeout from 30 to 60 seconds in our service.",
            "Add a /health endpoint to our API that returns 200 OK.",
            "Add a function that reverses a list in place.",
        ],
    },
    "plan-first-execute": {
        "scorer": score_plan, "direction": "higher",
        "tasks": [
            "Implement user authentication with JWT in our Express app.",
            "Migrate our database from MySQL to Postgres.",
            "Add rate limiting to all endpoints of our REST API.",
            "Build a CSV export feature for the reports page.",
        ],
    },
}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="gemma2:9b")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--only", default=None, help="run a single skill")
    args = ap.parse_args()

    results = {}
    for skill, cfg in PROBES.items():
        if args.only and skill != args.only:
            continue
        b = body(skill)
        scorer = cfg["scorer"]
        rows = []
        for task in cfg["tasks"]:
            base_out = run_model(args.model, task)
            treat_out = run_model(args.model, f"{b}\n\n---\nUser task:\n{task}")
            rows.append({
                "task": task[:50],
                "baseline": scorer(base_out),
                "treatment": scorer(treat_out),
            })
        bmean = sum(r["baseline"] for r in rows) / len(rows)
        tmean = sum(r["treatment"] for r in rows) / len(rows)
        delta = round(tmean - bmean, 2)
        good = (delta > 0) if cfg["direction"] == "higher" else (delta < 0)
        results[skill] = {
            "direction": cfg["direction"],
            "baseline_mean": round(bmean, 2),
            "treatment_mean": round(tmean, 2),
            "delta": delta,
            "verdict": "load-bearing" if good and abs(delta) >= 0.5 else
                       ("WEAK/INERT?" if abs(delta) < 0.5 else "BACKFIRES?"),
            "rows": rows,
        }

    if args.json:
        print(json.dumps(results, indent=2))
    else:
        print(f"=== INSTRUCTION-EFFICACY A/B (model={args.model}) ===")
        for skill, r in results.items():
            print(f"\n{skill}  [want {r['direction']}]  base={r['baseline_mean']} "
                  f"treat={r['treatment_mean']} delta={r['delta']} → {r['verdict']}")
            for row in r["rows"]:
                print(f"    {row['baseline']}→{row['treatment']}  {row['task']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
