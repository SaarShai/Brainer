#!/usr/bin/env python3
"""Validate semantic-diff's prior 95.5% savings claim.

Test sequence per source file:
  1. First read (full) — establishes baseline.
  2. Unmodified re-read — should return ~nothing.
  3. Small modification (add a function) — should return only the changed node.
  4. Larger modification (edit 2 method bodies) — should return only those nodes.

Reports per-step byte/character savings vs the full file size.

Usage:
  python3 eval/runner_semdiff.py
"""
from __future__ import annotations

import json
import shutil
import sys
import tempfile
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "skills" / "semantic-diff" / "tools"))

from semdiff import read_smart  # noqa: E402


SAMPLE_FILES = [
    REPO_ROOT / "skills/semantic-diff/tools/semdiff/core.py",
    REPO_ROOT / "skills/prompt-triage/tools/classify.py",
]


def measure_file(src: Path) -> dict:
    """Run the 4-step sequence on one source file."""
    full = src.read_text()
    baseline = len(full)

    # 1. Copy file to a temp dir so we can mutate without touching the repo
    workdir = Path(tempfile.mkdtemp(prefix="semdiff-eval-"))
    work = workdir / src.name
    work.write_text(full)

    session = f"eval-{src.stem}-{int(time.time())}"

    # Step 1: first read (full)
    r1, m1 = read_smart(str(work), session_id=session)
    s1 = len(r1)

    # Step 2: unmodified re-read
    r2, m2 = read_smart(str(work), session_id=session)
    s2 = len(r2)

    # Step 3: small modification — append a new function
    addition = "\n\ndef _eval_added_function():\n    return 'eval'\n"
    work.write_text(full + addition)
    r3, m3 = read_smart(str(work), session_id=session)
    s3 = len(r3)

    # Step 4: larger modification — change two function bodies (find first two `def` blocks and prepend a body line)
    text = work.read_text()
    lines = text.splitlines()
    edits = 0
    out_lines = []
    for ln in lines:
        if edits < 2 and ln.lstrip().startswith("def "):
            out_lines.append(ln)
            indent = " " * (len(ln) - len(ln.lstrip()) + 4)
            out_lines.append(f"{indent}# eval-modification {edits}")
            edits += 1
            continue
        out_lines.append(ln)
    work.write_text("\n".join(out_lines))
    r4, m4 = read_smart(str(work), session_id=session)
    s4 = len(r4)

    shutil.rmtree(workdir, ignore_errors=True)

    return {
        "file": str(src.relative_to(REPO_ROOT)),
        "baseline_chars": baseline,
        "step1_full_read_chars": s1,
        "step2_unchanged_chars": s2,
        "step2_savings_pct": round(100 * (1 - s2 / max(s1, 1)), 1),
        "step3_added_function_chars": s3,
        "step3_savings_pct": round(100 * (1 - s3 / max(s1, 1)), 1),
        "step4_two_edits_chars": s4,
        "step4_savings_pct": round(100 * (1 - s4 / max(s1, 1)), 1),
        "modes": {
            "step1": m1.get("mode"),
            "step2": m2.get("mode"),
            "step3": m3.get("mode"),
            "step4": m4.get("mode"),
        },
    }


def main() -> int:
    results = [measure_file(f) for f in SAMPLE_FILES if f.exists()]
    if not results:
        print("no sample files found", file=sys.stderr)
        return 2

    mean_step2 = sum(r["step2_savings_pct"] for r in results) / len(results)
    mean_step3 = sum(r["step3_savings_pct"] for r in results) / len(results)
    mean_step4 = sum(r["step4_savings_pct"] for r in results) / len(results)

    summary = {
        "harness": "runner_semdiff.py",
        "n_files": len(results),
        "results": results,
        "summary": {
            "step2_unchanged_savings_pct_mean": round(mean_step2, 1),
            "step3_added_function_savings_pct_mean": round(mean_step3, 1),
            "step4_two_edits_savings_pct_mean": round(mean_step4, 1),
        },
    }
    out_path = REPO_ROOT / "eval/results/semantic-diff.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(summary, indent=2))

    print(f"\n=== semantic-diff ({len(results)} files) ===")
    print(f"{'file':50s}  baseline   step2(stable)  step3(+fn)   step4(2-edit)")
    for r in results:
        print(f"{r['file'][:50]:50s}  {r['baseline_chars']:6}  {r['step2_savings_pct']:5.1f}%       {r['step3_savings_pct']:5.1f}%       {r['step4_savings_pct']:5.1f}%")
    print()
    print(f"  mean unchanged re-read savings:        {summary['summary']['step2_unchanged_savings_pct_mean']:.1f}%")
    print(f"  mean added-function re-read savings:   {summary['summary']['step3_added_function_savings_pct_mean']:.1f}%")
    print(f"  mean two-method-edit re-read savings:  {summary['summary']['step4_two_edits_savings_pct_mean']:.1f}%")
    print(f"  results: {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
