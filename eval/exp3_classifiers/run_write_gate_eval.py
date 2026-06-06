#!/usr/bin/env python3
"""CLASSIFIER eval for write-gate keep-vs-reject discrimination.

Reads write_gate_labeled.jsonl, runs each case through the real write-gate
scorer (score_text + decide, the same functions the CLI uses), and reports:

  - precision / recall / F1 (positive class = "keep")
  - confusion matrix (TP / FP / FN / TN)
  - per-kind accuracy
  - a THRESHOLD SWEEP: vary the score cutoff and report the P/R/F1 tradeoff,
    plus the best-F1 threshold. The why-clause gate for decisions/conventions
    is held fixed (it is independent of the numeric threshold).

Deterministic, no GPU, no network. Imports write_gate directly.

Usage:
  python3 eval/exp3_classifiers/run_write_gate_eval.py
  python3 eval/exp3_classifiers/run_write_gate_eval.py --threshold 3.0 --json
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(REPO / "skills/write-gate/tools"))
from write_gate import DEFAULT_THRESHOLD, decide, score_text  # noqa: E402

DATA = HERE / "write_gate_labeled.jsonl"


def load_cases() -> list[dict]:
    rows = []
    for line in DATA.read_text().splitlines():
        line = line.strip()
        if line:
            rows.append(json.loads(line))
    return rows


def confusion(cases: list[dict], threshold: float, require_why: bool = True) -> dict:
    """Run the gate at a given threshold. Positive class = keep/pass."""
    tp = tn = fp = fn = 0
    per_kind: dict[str, dict] = {}
    rows = []
    for c in cases:
        s = score_text(c["text"], c["kind"])
        passed, verdict = decide(s, c["kind"], threshold, require_why)
        gold_keep = c["label"] == "keep"
        if gold_keep and passed:
            tp += 1
        elif gold_keep and not passed:
            fn += 1
        elif not gold_keep and passed:
            fp += 1
        else:
            tn += 1
        k = per_kind.setdefault(c["kind"], {"n": 0, "correct": 0})
        k["n"] += 1
        k["correct"] += int(passed == gold_keep)
        rows.append({
            "label": c.get("label_id", c["why"][:30]),
            "kind": c["kind"],
            "gold": c["label"],
            "predicted": "keep" if passed else "reject",
            "score": round(s.total, 2),
            "has_why": s.has_why,
            "correct": passed == gold_keep,
            "verdict": verdict,
        })
    n = len(cases)
    precision = tp / max(1, tp + fp)
    recall = tp / max(1, tp + fn)
    f1 = 2 * precision * recall / max(1e-9, precision + recall)
    return {
        "threshold": threshold,
        "n": n,
        "accuracy": round((tp + tn) / n, 4),
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1": round(f1, 4),
        "confusion": {"tp": tp, "fp": fp, "fn": fn, "tn": tn},
        "per_kind_accuracy": {
            k: round(v["correct"] / v["n"], 4) for k, v in sorted(per_kind.items())
        },
        "rows": rows,
    }


def threshold_sweep(cases: list[dict], lo: float = -2.0, hi: float = 12.0, step: float = 0.5) -> list[dict]:
    """Vary the numeric score cutoff; report P/R/F1 at each. The why-clause
    requirement for decisions/conventions stays on (it gates independently of
    the numeric threshold, so even at threshold=-inf a reasonless decision is
    rejected). This isolates the score-cutoff tradeoff."""
    out = []
    t = lo
    while t <= hi + 1e-9:
        m = confusion(cases, round(t, 3))
        out.append({
            "threshold": round(t, 3),
            "precision": m["precision"],
            "recall": m["recall"],
            "f1": m["f1"],
            "accuracy": m["accuracy"],
            "tp": m["confusion"]["tp"],
            "fp": m["confusion"]["fp"],
            "fn": m["confusion"]["fn"],
            "tn": m["confusion"]["tn"],
        })
        t += step
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--threshold", type=float, default=DEFAULT_THRESHOLD)
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--out", default=str(HERE / "results" / "write_gate_eval.json"))
    args = ap.parse_args()

    cases = load_cases()
    main_m = confusion(cases, args.threshold)
    sweep = threshold_sweep(cases)
    best = max(sweep, key=lambda r: (r["f1"], r["accuracy"]))

    result = {
        "eval": "write_gate_keep_vs_reject",
        "data": str(DATA.relative_to(REPO)),
        "n_cases": len(cases),
        "n_keep": sum(1 for c in cases if c["label"] == "keep"),
        "n_reject": sum(1 for c in cases if c["label"] == "reject"),
        "from_corpus": sum(1 for c in cases if c["source"] == "write_gate_corpus.py"),
        "authored": sum(1 for c in cases if c["source"] == "authored"),
        "default_threshold_metrics": {k: v for k, v in main_m.items() if k != "rows"},
        "best_threshold": best,
        "threshold_sweep": sweep,
        "misclassified": [r for r in main_m["rows"] if not r["correct"]],
    }

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(result, indent=2))

    if args.json:
        print(json.dumps(result, indent=2))
        return 0

    m = main_m
    print(f"=== write-gate keep-vs-reject ({len(cases)} cases, threshold={args.threshold}) ===")
    print(f"  accuracy  : {m['accuracy']:.1%}")
    print(f"  precision : {m['precision']:.1%}   recall: {m['recall']:.1%}   F1: {m['f1']:.1%}")
    cm = m["confusion"]
    print(f"  confusion : TP={cm['tp']} FP={cm['fp']} FN={cm['fn']} TN={cm['tn']}")
    print(f"  per-kind  : {m['per_kind_accuracy']}")
    if m["rows"]:
        wrong = [r for r in m["rows"] if not r["correct"]]
        if wrong:
            print(f"\n  MISCLASSIFIED ({len(wrong)}):")
            for r in wrong:
                print(f"    [{r['gold']:>6}->{r['predicted']:<6}] kind={r['kind']:<11} "
                      f"score={r['score']:>5} why={r['has_why']}  {r['label']}")
    print(f"\n  THRESHOLD SWEEP (P/R/F1 tradeoff):")
    print(f"    {'thr':>5} {'P':>6} {'R':>6} {'F1':>6} {'acc':>6}  TP FP FN TN")
    for r in sweep:
        mark = "  <- best F1" if r["threshold"] == best["threshold"] else ""
        print(f"    {r['threshold']:>5} {r['precision']:>6.3f} {r['recall']:>6.3f} "
              f"{r['f1']:>6.3f} {r['accuracy']:>6.3f}  "
              f"{r['tp']:>2} {r['fp']:>2} {r['fn']:>2} {r['tn']:>2}{mark}")
    print(f"\n  best-F1 threshold = {best['threshold']} (F1={best['f1']:.3f}, acc={best['accuracy']:.3f})")
    print(f"\n  full JSON: {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
