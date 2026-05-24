#!/usr/bin/env python3
"""Run every sim in eval/sims/ and report pass/fail.

Usage:
  python3 eval/sims/run_all.py              # run all
  python3 eval/sims/run_all.py --only fuzz  # filter by shape (calibration/fuzz/scale/integration/pipeline)
  python3 eval/sims/run_all.py --skill prompt-triage  # filter by skill name
  python3 eval/sims/run_all.py --json       # JSON output for CI

Exit codes:
  0 — every sim returned 0
  1 — at least one sim returned non-zero
  2 — usage / discovery error

Convention: a sim is any eval/sims/*.py that is NOT _lib.py, NOT TEMPLATE_*.py,
and NOT run_all.py itself.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

SIMS_DIR = Path(__file__).resolve().parent
EXCLUDED = {"_lib.py", "run_all.py"}


def discover() -> list[Path]:
    sims = []
    for p in sorted(SIMS_DIR.glob("*.py")):
        if p.name in EXCLUDED:
            continue
        if p.name.startswith("TEMPLATE_"):
            continue
        if p.name.startswith("_"):
            continue
        sims.append(p)
    return sims


def main() -> int:
    ap = argparse.ArgumentParser(prog="run_all", description=__doc__)
    ap.add_argument("--only", choices=["calibration", "corpus", "fuzz", "scale",
                                         "integration", "pipeline"])
    ap.add_argument("--skill", help="filter sims whose filename starts with this skill name")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--quiet", action="store_true", help="suppress per-sim stdout")
    args = ap.parse_args()

    sims = discover()
    if args.only:
        sims = [s for s in sims if args.only in s.stem]
    if args.skill:
        sims = [s for s in sims if s.stem.startswith(args.skill.replace("-", "_"))]

    if not sims:
        print("no sims matched", file=sys.stderr)
        return 2

    results = []
    t0 = time.time()
    for sim in sims:
        if not args.quiet and not args.json:
            print(f"--- {sim.name} ---")
        ts = time.time()
        try:
            r = subprocess.run(
                [sys.executable, str(sim)],
                capture_output=args.quiet or args.json,
                text=True,
                timeout=180,
            )
            elapsed = time.time() - ts
            results.append({
                "sim": sim.name,
                "exit": r.returncode,
                "elapsed_s": round(elapsed, 2),
                "stdout_tail": (r.stdout or "").splitlines()[-5:] if (args.quiet or args.json) else None,
            })
            if not args.quiet and not args.json and r.stdout:
                print(r.stdout)
        except subprocess.TimeoutExpired:
            results.append({"sim": sim.name, "exit": 124, "elapsed_s": 180, "error": "timeout"})
        except Exception as e:
            results.append({"sim": sim.name, "exit": -1, "error": f"{type(e).__name__}: {e}"})

    total_elapsed = round(time.time() - t0, 2)
    passed = sum(1 for r in results if r["exit"] == 0)
    failed = [r for r in results if r["exit"] != 0]

    if args.json:
        print(json.dumps({
            "n": len(results), "passed": passed, "failed": len(failed),
            "total_elapsed_s": total_elapsed, "results": results,
        }, indent=2))
    else:
        print(f"\n=== sim run summary: {passed}/{len(results)} passed  ({total_elapsed}s) ===")
        for r in results:
            mark = "ok" if r["exit"] == 0 else f"FAIL ({r['exit']})"
            print(f"  [{mark}] {r['sim']:<40} {r['elapsed_s']}s")
        if failed:
            print(f"\n{len(failed)} sim(s) failed")
            for r in failed:
                if r.get("stdout_tail"):
                    print(f"\n--- {r['sim']} stdout tail ---")
                    for line in r["stdout_tail"]:
                        print(f"  {line}")

    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())
