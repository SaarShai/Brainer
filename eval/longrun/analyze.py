#!/usr/bin/env python3
"""Aggregate longrun_<node>.jsonl into mean ± 95% CI across reps.

Turns the repeated trials into the three things the long run is for:
  efficiency  — drift adherence-uplift per 1k injected tokens
  reliability — variance (sd, CI) across reps + fraction of reps the effect held
  quality     — compounding dependent-acc lift (memory − cold); drift adherence

Usage:
  python3 eval/longrun/analyze.py eval/longrun/results/longrun_M2.jsonl [more.jsonl ...]
"""
from __future__ import annotations

import json
import statistics
import sys
from pathlib import Path


def ci95(xs: list[float]) -> tuple[float, float, float, int]:
    xs = [x for x in xs if x is not None]
    n = len(xs)
    if n == 0:
        return (float("nan"), 0.0, float("nan"), 0)
    m = statistics.mean(xs)
    sd = statistics.stdev(xs) if n > 1 else 0.0
    half = 1.96 * sd / (n ** 0.5) if n > 1 else 0.0
    return (round(m, 3), round(sd, 3), round(half, 3), n)


def col(recs: list[dict], path: list[str]) -> list[float]:
    out = []
    for r in recs:
        cur = r
        for k in path:
            cur = cur.get(k) if isinstance(cur, dict) else None
            if cur is None:
                break
        if isinstance(cur, (int, float)) and not isinstance(cur, bool):
            out.append(float(cur))
    return out


def frac_true(recs: list[dict], path: list[str]) -> tuple[float, int]:
    vals = []
    for r in recs:
        cur = r
        for k in path:
            cur = cur.get(k) if isinstance(cur, dict) else None
            if cur is None:
                break
        if isinstance(cur, bool):
            vals.append(cur)
    if not vals:
        return (float("nan"), 0)
    return (round(sum(vals) / len(vals), 3), len(vals))


def report(fp: Path):
    recs = [json.loads(l) for l in fp.read_text().splitlines() if l.strip()]
    node = recs[0]["node"] if recs else "?"
    model = recs[0]["model"] if recs else "?"
    print(f"\n===== {fp.name} — node={node} model={model} reps={len(recs)} =====")

    dok = sum(1 for r in recs if r.get("drift", {}).get("ok"))
    cok = sum(1 for r in recs if r.get("compound", {}).get("ok"))
    print(f"  completed: drift {dok}/{len(recs)}  compound {cok}/{len(recs)}")

    def line(label, xs):
        m, sd, half, n = ci95(xs)
        print(f"    {label:34s} mean={m}  ±{half} (95% CI)  sd={sd}  n={n}")

    print("  --- DRIFT (skill-pulse / compliance-canary), efficiency+quality ---")
    line("pulse uplift (adherence)", col(recs, ["drift_verdict", "pulse_uplift"]))
    line("canary uplift (adherence)", col(recs, ["drift_verdict", "canary_uplift"]))
    line("both uplift (adherence)", col(recs, ["drift_verdict", "both_uplift"]))
    line("pulse efficiency (/1k tok)", col(recs, ["drift_verdict", "pulse_efficiency"]))
    line("canary efficiency (/1k tok)", col(recs, ["drift_verdict", "canary_efficiency"]))
    fc, nfc = frac_true(recs, ["drift_verdict", "control_decays"])
    print(f"    control_decays held (gate)         {fc} of {nfc} reps")
    fb, nfb = frac_true(recs, ["drift_verdict", "both_beats_best_single"])
    print(f"    both_beats_best_single             {fb} of {nfb} reps")

    print("  --- COMPOUNDING (wiki-memory), quality+reliability ---")
    line("dependent_acc_lift (memory-cold)", col(recs, ["compound_verdict", "dependent_acc_lift"]))
    line("memory dependent acc", col(recs, ["compound_verdict", "memory_dependent_acc"]))
    line("cold dependent acc", col(recs, ["compound_verdict", "cold_dependent_acc"]))
    line("poisoned dependent acc", col(recs, ["compound_verdict", "poisoned_dependent_acc"]))
    lifts = col(recs, ["compound_verdict", "dependent_acc_lift"])
    if lifts:
        pos = sum(1 for x in lifts if x > 0)
        print(f"    memory>cold held                   {round(pos/len(lifts),3)} of {len(lifts)} reps")

    print("  --- wall time ---")
    line("drift secs/rep", col(recs, ["drift", "secs"]))
    line("compound secs/rep", col(recs, ["compound", "secs"]))


def main() -> int:
    files = [Path(a) for a in sys.argv[1:]]
    if not files:
        rd = Path(__file__).resolve().parent / "results"
        files = sorted(rd.glob("longrun_*.jsonl"))
    if not files:
        print("no longrun_*.jsonl found", file=sys.stderr)
        return 1
    for fp in files:
        if fp.exists():
            report(fp)
    return 0


if __name__ == "__main__":
    sys.exit(main())
