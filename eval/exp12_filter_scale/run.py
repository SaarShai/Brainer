#!/usr/bin/env python3
"""exp12 — output-filter at scale (closes runner_filter's N=4 gap).

runner_filter.py proved the mechanics on 4 hand-built samples. The load-bearing
claim is "strips noise but preserves error lines VERBATIM." That claim only
earns trust at scale and against adversarial placement, so here we generate a
large, deterministic corpus where every embedded error line is KNOWN ground
truth, then assert:

  reliability  — 100% of embedded error lines survive byte-for-byte (the
                 contract; a single dropped error = fail)
  efficiency   — byte/line reduction distribution across the corpus
  adversarial  — errors placed INSIDE dup-collapsible blocks and progress
                 spam (where a naive dedup would eat them)

Deterministic (index-driven, no RNG). Local, no model.

Usage: python3 eval/exp12_filter_scale/run.py
"""
from __future__ import annotations

import json
import statistics
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(REPO / "eval"))
from runner_filter import ERROR_PAT, run_filter  # noqa: E402

# Distinct real-world error lines (different ecosystems) — each must survive verbatim.
ERROR_TEMPLATES = [
    "Error: Expected 'foo' to equal 'bar'",
    "Traceback (most recent call last):",
    "OSError: [Errno 28] No space left on device",
    "error[E0382]: borrow of moved value: `config`",
    "panic: runtime error: index out of range [3] with length 2",
    "FAIL src/auth.test.ts (2 failed)",
    "fatal: unable to access 'https://github.com/x/y': Could not resolve host",
    "Segmentation fault (core dumped)",
    "ERROR 1146 (42S02): Table 'db.users' doesn't exist",
    "AssertionError: 401 != 200",
    "npm ERR! code ELIFECYCLE",
    "exit code 1",
]

SIGNAL_LINES = [
    "Starting build", "step 1: compile", "step 2: link", "Deploy complete",
    "Compiled 42 files", "All checks passed", "Uploaded artifact",
]


def make_sample(i: int) -> tuple[str, list[str]]:
    """Deterministically build one noisy sample; return (text, embedded_error_lines)."""
    parts: list[str] = []
    errs: list[str] = []
    dup_n = 15 + (i * 7) % 90
    prog_pct = (i * 5) % 100

    # ANSI-coloured header
    parts.append("\x1b[1;34mRun #%d\x1b[0m" % i)
    # progress bar with carriage returns + ANSI
    bar = "".join("\r[%s%s] %d%%" % ("=" * k, " " * (20 - k), k * 5) for k in range(0, 21))
    parts.append("\x1b[32m" + bar + "\x1b[0m")
    # a block of duplicate noise
    parts.append(("processing item %d...\n" % i) * dup_n)
    parts.append(SIGNAL_LINES[i % len(SIGNAL_LINES)])

    # embed 1-2 errors at index-varied positions, some INSIDE the dup/progress spam
    e1 = ERROR_TEMPLATES[i % len(ERROR_TEMPLATES)]
    errs.append(e1)
    placement = i % 3
    if placement == 0:           # error buried inside duplicate spam (adversarial)
        parts.insert(2, ("warn: retrying...\n" * 10) + e1 + "\n" + ("warn: retrying...\n" * 10))
    elif placement == 1:         # error right after a progress bar
        parts.insert(2, e1)
    else:                        # error at the very end
        parts.append(e1)

    if i % 4 == 0:               # second error from a different ecosystem
        e2 = ERROR_TEMPLATES[(i * 3 + 5) % len(ERROR_TEMPLATES)]
        if e2 != e1:
            errs.append(e2)
            parts.append("more output\n" * 8 + e2)

    parts.append("npm WARN deprecated pkg@%d.0\n" % i * 1)
    text = "\n".join(parts) + "\n"
    return text, errs


def main() -> int:
    n = 40
    rows = []
    all_errors = 0
    all_preserved = 0
    misses = []
    for i in range(n):
        raw, embedded = make_sample(i)
        filtered, rc = run_filter(raw, REPO)
        raw_bytes, out_bytes = len(raw.encode()), len(filtered.encode())
        # ground-truth error preservation (verbatim substring)
        preserved = [e for e in embedded if e in filtered]
        all_errors += len(embedded)
        all_preserved += len(preserved)
        for e in embedded:
            if e not in filtered:
                misses.append({"sample": i, "error_line": e})
        rows.append({
            "i": i, "rc": rc,
            "raw_bytes": raw_bytes, "filtered_bytes": out_bytes,
            "reduction_pct": round(100 * (out_bytes - raw_bytes) / max(raw_bytes, 1), 1),
            "embedded_errors": len(embedded), "preserved": len(preserved),
        })

    reductions = [r["reduction_pct"] for r in rows]
    summary = {
        "experiment": "exp12_filter_scale",
        "n_samples": n,
        "error_preservation": {
            "total_errors": all_errors,
            "preserved": all_preserved,
            "rate": round(all_preserved / max(all_errors, 1), 4),
            "misses": misses,
        },
        "byte_reduction_pct": {
            "mean": round(statistics.mean(reductions), 1),
            "median": round(statistics.median(reductions), 1),
            "min": round(min(reductions), 1),
            "max": round(max(reductions), 1),
        },
        "rows": rows,
    }
    out = HERE / "results" / "summary.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(summary, indent=2))

    ep = summary["error_preservation"]
    br = summary["byte_reduction_pct"]
    print(f"\n=== exp12 output-filter @ scale (N={n}) ===")
    print(f"  error preservation: {ep['preserved']}/{ep['total_errors']} = {ep['rate']*100:.2f}%"
          f"  {'(PASS — all verbatim)' if ep['rate'] == 1.0 else '(FAIL — dropped errors!)'}")
    if misses:
        for m in misses[:10]:
            print(f"    MISS sample {m['sample']}: {m['error_line']!r}")
    print(f"  byte reduction: mean {br['mean']}%  median {br['median']}%  range [{br['min']}, {br['max']}]%")
    print(f"  results: {out}")
    return 0 if ep["rate"] == 1.0 else 1


if __name__ == "__main__":
    sys.exit(main())
