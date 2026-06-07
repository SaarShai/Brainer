#!/usr/bin/env python3
"""CLASSIFIER eval for prompt-triage routing accuracy.

Reads triage_labeled.jsonl, runs each prompt through classify.py's classify()
(and is_bypass() for the bypass cases), and reports:

  - routing accuracy (model-family grade: cheap-OK vs escalate, with the
    project's grading rules: not_haiku, haiku<->local equivalence)
  - tier accuracy on cases that carry an expected_tier
  - per-tier confusion matrix (expected tier x predicted tier)
  - the regex-fast-path vs LLM-fallback split (classify() returns "source":
    regex / regex-low-conf / ollama / default)
  - bypass detection accuracy (NO TRIAGE / /opus + anti-bypass decoys)
  - the cost-floor guard: count of complex cases misrouted to haiku (must be 0)

Default run is DETERMINISTIC: ollama fallback OFF (regex fast-path only),
matching the project's test convention. Pass --ollama to additionally measure
the fallback path against a live daemon.

Usage:
  python3 eval/exp3_classifiers/run_triage_eval.py
  python3 eval/exp3_classifiers/run_triage_eval.py --ollama --json
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(REPO / "skills/prompt-triage/tools"))
import classify as triage  # noqa: E402

DATA = HERE / "triage_labeled.jsonl"


def load_cases() -> list[dict]:
    rows = []
    for line in DATA.read_text().splitlines():
        line = line.strip()
        if line:
            rows.append(json.loads(line))
    return rows


def grade_model(expected: str, actual: str) -> bool:
    """Project grading rule (mirrors prompt_triage_corpus.grade)."""
    if expected is None:
        return True  # not graded on model
    if expected == "not_haiku":
        return actual != "haiku"
    if expected == actual:
        return True
    if expected == "haiku" and actual.startswith("local:"):
        return True
    if expected.startswith("local:") and actual == "haiku":
        return True
    return False


def run(cases: list[dict], use_ollama: bool) -> dict:
    rows = []
    # routing (model) grade
    routed_total = routed_correct = 0
    # tier grade (only where expected_tier given)
    tier_total = tier_correct = 0
    tier_conf = defaultdict(lambda: defaultdict(int))  # expected -> predicted -> n
    # regex vs fallback split
    source_counts = defaultdict(int)
    # bypass
    bypass_total = bypass_correct = 0
    # cost-floor guard
    complex_cases = complex_misrouted_haiku = 0

    for c in cases:
        prompt = c["prompt"]
        if c["expect_bypass"] is True or (
            c["expected_model"] is None and c["expected_tier"] is None
            and c["expect_bypass"] is not None
        ):
            # Pure bypass / anti-bypass case: only check is_bypass().
            pass

        # Always evaluate bypass detection where a bypass expectation is meaningful.
        # (Every case carries expect_bypass; decoys expect False.)
        actual_bypass = triage.is_bypass(prompt)
        bypass_ok = actual_bypass == c["expect_bypass"]
        bypass_total += 1
        bypass_correct += int(bypass_ok)

        row = {
            "prompt": prompt[:70],
            "source": c["source"],
            "expect_bypass": c["expect_bypass"],
            "actual_bypass": actual_bypass,
            "bypass_correct": bypass_ok,
        }

        if c["expect_bypass"]:
            # A bypass prompt would skip the classifier entirely in production.
            # We don't grade tier/model on it. Record and continue.
            row["graded"] = "bypass-only"
            rows.append(row)
            continue

        result = triage.classify(prompt, use_ollama_fallback=use_ollama)
        actual_model = result.get("model", "opus")
        actual_tier = result.get("tier", "unknown")
        src = result.get("source", "?")
        source_counts[src] += 1

        # routing (model) grade
        m_ok = grade_model(c["expected_model"], actual_model)
        if c["expected_model"] is not None:
            routed_total += 1
            routed_correct += int(m_ok)

        # tier grade
        t_ok = None
        if c["expected_tier"] is not None:
            tier_total += 1
            t_ok = actual_tier == c["expected_tier"]
            tier_correct += int(t_ok)
            tier_conf[c["expected_tier"]][actual_tier] += 1

        # cost-floor guard: cases that must NOT be cheap-routed
        if c["expected_model"] in ("not_haiku", "opus", "sonnet"):
            complex_cases += 1
            if actual_model == "haiku":
                complex_misrouted_haiku += 1

        row.update({
            "expected_tier": c["expected_tier"],
            "actual_tier": actual_tier,
            "tier_correct": t_ok,
            "expected_model": c["expected_model"],
            "actual_model": actual_model,
            "model_correct": m_ok if c["expected_model"] is not None else None,
            "classify_source": src,
            "confidence": result.get("confidence"),
            "graded": "routing",
        })
        rows.append(row)

    # tier confusion -> plain dict
    conf = {exp: dict(preds) for exp, preds in tier_conf.items()}

    return {
        "use_ollama": use_ollama,
        "routing_accuracy": round(routed_correct / max(1, routed_total), 4),
        "routing_total": routed_total,
        "routing_correct": routed_correct,
        "tier_accuracy": round(tier_correct / max(1, tier_total), 4),
        "tier_total": tier_total,
        "tier_correct": tier_correct,
        "tier_confusion": conf,
        "bypass_accuracy": round(bypass_correct / max(1, bypass_total), 4),
        "bypass_total": bypass_total,
        "bypass_correct": bypass_correct,
        "fastpath_split": dict(source_counts),
        "complex_cases": complex_cases,
        "complex_misrouted_to_haiku": complex_misrouted_haiku,
        "rows": rows,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ollama", action="store_true",
                    help="enable LLM fallback against a live daemon (non-deterministic)")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--out", default=str(HERE / "results" / "triage_eval.json"))
    args = ap.parse_args()

    cases = load_cases()
    det = run(cases, use_ollama=False)
    result = {
        "eval": "prompt_triage_routing",
        "data": str(DATA.relative_to(REPO)),
        "n_cases": len(cases),
        "from_corpora": sum(1 for c in cases if c["source"] != "authored"),
        "authored": sum(1 for c in cases if c["source"] == "authored"),
        "deterministic_regex_only": {k: v for k, v in det.items() if k != "rows"},
        "misclassified_routing": [
            r for r in det["rows"]
            if r.get("graded") == "routing" and r.get("model_correct") is False
        ],
        "misclassified_tier": [
            r for r in det["rows"]
            if r.get("graded") == "routing" and r.get("tier_correct") is False
        ],
        "bypass_errors": [r for r in det["rows"] if not r["bypass_correct"]],
    }
    if args.ollama:
        oll = run(cases, use_ollama=True)
        result["with_ollama_fallback"] = {k: v for k, v in oll.items() if k != "rows"}

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(result, indent=2))

    if args.json:
        print(json.dumps(result, indent=2))
        return 0

    d = det
    print(f"=== prompt-triage routing ({len(cases)} cases, regex-only deterministic) ===")
    print(f"  routing accuracy : {d['routing_accuracy']:.1%}  ({d['routing_correct']}/{d['routing_total']})")
    print(f"  tier accuracy    : {d['tier_accuracy']:.1%}  ({d['tier_correct']}/{d['tier_total']})")
    print(f"  bypass accuracy  : {d['bypass_accuracy']:.1%}  ({d['bypass_correct']}/{d['bypass_total']})")
    print(f"  fast-path split  : {d['fastpath_split']}")
    print(f"  complex cases    : {d['complex_cases']}  misrouted->haiku: {d['complex_misrouted_to_haiku']}")
    print(f"\n  TIER CONFUSION (expected -> predicted):")
    for exp, preds in sorted(d["tier_confusion"].items(), key=lambda kv: str(kv[0])):
        print(f"    {str(exp):>8}: {preds}")
    if result["misclassified_routing"]:
        print(f"\n  ROUTING MISCLASSIFIED ({len(result['misclassified_routing'])}):")
        for r in result["misclassified_routing"]:
            print(f"    exp_model={r['expected_model']:<12} got={r['actual_model']:<14} "
                  f"src={r['classify_source']:<14} {r['prompt']}")
    if result["misclassified_tier"]:
        print(f"\n  TIER MISCLASSIFIED ({len(result['misclassified_tier'])}):")
        for r in result["misclassified_tier"]:
            print(f"    exp_tier={r['expected_tier']:<8} got={r['actual_tier']:<8} "
                  f"src={r['classify_source']:<14} {r['prompt']}")
    if result["bypass_errors"]:
        print(f"\n  BYPASS ERRORS ({len(result['bypass_errors'])}):")
        for r in result["bypass_errors"]:
            print(f"    exp_bypass={r['expect_bypass']} got={r['actual_bypass']}  {r['prompt']}")
    if args.ollama:
        o = result["with_ollama_fallback"]
        print(f"\n  [with ollama fallback] routing={o['routing_accuracy']:.1%} "
              f"tier={o['tier_accuracy']:.1%} split={o['fastpath_split']}")
    print(f"\n  full JSON: {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
