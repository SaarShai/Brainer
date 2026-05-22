#!/usr/bin/env python3
"""Mechanical measurement for output-filter.

Feeds a corpus of noisy command outputs (ANSI escapes, progress bars,
duplicate lines) through filter.sh and measures:
  - bytes-in vs bytes-out
  - lines-in vs lines-out
  - error-line preservation (any line matching common error patterns
    must survive verbatim)

Usage:
  python3 eval/runner_filter.py
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


ERROR_PAT = re.compile(r"(error|exception|traceback|failed|fatal|segfault|killed|exit code [1-9])", re.I)


NOISY_SAMPLES: list[tuple[str, str]] = [
    (
        "ansi_progress",
        # Mimics a progress bar with carriage returns + ANSI escapes
        "\x1b[1;32mBuilding...\x1b[0m\n"
        + "\n".join(f"\r[{'='*i}{' '*(20-i)}] {i*5}%" for i in range(0, 21))
        + "\n\x1b[1;32mDone.\x1b[0m\n"
        + "Compiled 42 files\n",
    ),
    (
        "ci_log",
        # Repeated identical lines + warnings + one real error
        ("npm WARN deprecated foo@1.0\n" * 30)
        + "Running tests...\n"
        + "PASS test/a.test.js\n" * 12
        + "FAIL test/b.test.js\n"
        + "  Error: Expected 'foo' to equal 'bar'\n"
        + "  at Object.<anonymous> (test/b.test.js:5:14)\n"
        + ("npm WARN package.json has no description\n" * 20)
        + "exit code 1\n",
    ),
    (
        "dup_stdout",
        # Same line repeated many times — collapse target
        ("processing item...\n" * 100) + "all done\n",
    ),
    (
        "mixed_signal",
        # Mix of signal + noise; should preserve the signal
        "\x1b[KStarting deploy\n"
        + "step 1: build\n"
        + ("[debug] heartbeat\n" * 50)
        + "step 2: upload\n"
        + ("uploaded 1 KB\n" * 30)
        + "Traceback (most recent call last):\n"
        + "  File \"deploy.py\", line 42, in <module>\n"
        + "    main()\n"
        + "OSError: disk full\n"
        + "exit code 1\n",
    ),
]


def run_filter(text: str, root: Path) -> tuple[str, int]:
    """Pipe text through filter.sh, return (filtered_text, returncode)."""
    filter_sh = root / "skills/output-filter/tools/filter.sh"
    env = os.environ.copy()
    env["TOKEN_ECONOMY_ROOT"] = str(root)
    proc = subprocess.run(
        ["bash", str(filter_sh)],
        input=text,
        capture_output=True,
        text=True,
        timeout=30,
        env=env,
    )
    return proc.stdout, proc.returncode


def measure_sample(name: str, raw: str, root: Path) -> dict:
    filtered, rc = run_filter(raw, root)
    raw_bytes = len(raw.encode())
    out_bytes = len(filtered.encode())
    raw_lines = raw.count("\n")
    out_lines = filtered.count("\n")
    raw_errors = [ln for ln in raw.splitlines() if ERROR_PAT.search(ln)]
    preserved = sum(1 for ln in raw_errors if ln in filtered)
    return {
        "sample": name,
        "rc": rc,
        "raw_bytes": raw_bytes,
        "filtered_bytes": out_bytes,
        "bytes_delta_pct": round(100 * (out_bytes - raw_bytes) / max(raw_bytes, 1), 1),
        "raw_lines": raw_lines,
        "filtered_lines": out_lines,
        "lines_delta_pct": round(100 * (out_lines - raw_lines) / max(raw_lines, 1), 1),
        "errors_in_raw": len(raw_errors),
        "errors_preserved": preserved,
        "error_preservation_pct": round(100 * preserved / max(len(raw_errors), 1), 1) if raw_errors else None,
    }


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    rows = [measure_sample(name, raw, root) for name, raw in NOISY_SAMPLES]
    summary = {
        "harness": "runner_filter.py",
        "samples": rows,
        "totals": {
            "raw_bytes": sum(r["raw_bytes"] for r in rows),
            "filtered_bytes": sum(r["filtered_bytes"] for r in rows),
            "total_reduction_pct": round(
                100 * (sum(r["filtered_bytes"] for r in rows) - sum(r["raw_bytes"] for r in rows))
                / max(sum(r["raw_bytes"] for r in rows), 1), 1
            ),
            "errors_in_raw_total": sum(r["errors_in_raw"] for r in rows),
            "errors_preserved_total": sum(r["errors_preserved"] for r in rows),
        },
    }
    out_path = root / "eval/results/output-filter.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(summary, indent=2))

    print(f"\n=== output-filter (4 noisy samples) ===")
    for r in rows:
        ep = f"errors {r['errors_preserved']}/{r['errors_in_raw']} preserved" if r["errors_in_raw"] else "no error lines"
        print(f"  {r['sample']:15s}: {r['raw_bytes']:5} -> {r['filtered_bytes']:5} bytes ({r['bytes_delta_pct']:+.1f}%), {ep}")
    t = summary["totals"]
    print(f"  TOTAL          : {t['raw_bytes']} -> {t['filtered_bytes']} bytes ({t['total_reduction_pct']:+.1f}%)")
    print(f"  errors preserved: {t['errors_preserved_total']}/{t['errors_in_raw_total']}")
    print(f"  results: {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
