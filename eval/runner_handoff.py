#!/usr/bin/env python3
"""Integration test for the handoff skill.

Invokes skills/handoff/tools/handoff.py with a focus argument, verifies:
  - The script returns a path on stdout
  - The path exists and contains markdown
  - The doc carries the expected sections (current task, what done, what
    in-progress, what next)
  - The focus argument is reflected in the doc

Outputs eval/results/handoff.json with the measurement.

Usage:
  python3 eval/runner_handoff.py
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path


REQUIRED_SECTIONS = [
    # patterns (case-insensitive) — the doc must include each
    r"current task",
    r"(?:what )?done",
    r"in[- ]progress|blockers?",
    r"(?:what )?next",
]

TEST_FOCUS_LINES = [
    "fixing the auth race condition",
    "continue the eval and populate remaining EVAL.md files",
    "wip — nothing specific",
]


def run_once(focus: str, root: Path) -> dict:
    """Invoke handoff.py with a focus argument; collect timing + content."""
    script = root / "skills/handoff/tools/handoff.py"
    t0 = time.time()
    proc = subprocess.run(
        [sys.executable, str(script), "--goal", focus],
        capture_output=True,
        text=True,
        timeout=30,
        env={**os.environ, "TOKEN_ECONOMY_ROOT": str(root)},
    )
    latency_ms = int((time.time() - t0) * 1000)
    out = proc.stdout.strip()
    err = proc.stderr.strip()

    if proc.returncode != 0:
        return {
            "focus": focus,
            "ok": False,
            "rc": proc.returncode,
            "stderr": err[:500],
            "latency_ms": latency_ms,
        }

    # Stdout should be the path to the written file
    path = Path(out.splitlines()[-1] if out else "")
    if not path.exists():
        return {
            "focus": focus,
            "ok": False,
            "reason": f"stdout path not found: {out!r}",
            "stderr": err[:500],
            "latency_ms": latency_ms,
        }

    body = path.read_text()
    body_lc = body.lower()
    sections_present = {pat: bool(re.search(pat, body_lc)) for pat in REQUIRED_SECTIONS}
    focus_reflected = focus.lower() in body_lc

    # Path should be in $TMPDIR (per skill body), not workspace.
    # Resolve both sides so /var/folders/... vs /private/var/folders/... matches on macOS.
    tmp_resolved = Path(tempfile.gettempdir()).resolve()
    in_tmp = path.resolve().is_relative_to(tmp_resolved) if hasattr(Path, "is_relative_to") else str(path.resolve()).startswith(str(tmp_resolved))

    return {
        "focus": focus,
        "ok": all(sections_present.values()) and focus_reflected and in_tmp,
        "path": str(path),
        "bytes": len(body.encode()),
        "lines": body.count("\n"),
        "sections_present": sections_present,
        "focus_reflected": focus_reflected,
        "in_tmpdir": in_tmp,
        "latency_ms": latency_ms,
        "preview": body[:400],
    }


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    results = []
    for f in TEST_FOCUS_LINES:
        results.append(run_once(f, root))
        time.sleep(1.1)  # ensure per-second timestamps don't collide

    n_ok = sum(1 for r in results if r.get("ok"))
    mean_bytes = sum(r.get("bytes", 0) for r in results) / max(len(results), 1)
    mean_latency = sum(r.get("latency_ms", 0) for r in results) / max(len(results), 1)

    summary = {
        "harness": "runner_handoff.py",
        "n": len(results),
        "passed": n_ok,
        "pass_rate": round(n_ok / max(len(results), 1), 3),
        "mean_bytes": round(mean_bytes, 0),
        "mean_latency_ms": round(mean_latency, 0),
        "results": results,
    }
    out_path = root / "eval/results/handoff.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(summary, indent=2))

    print(f"\n=== handoff integration ({len(results)} focus arguments) ===")
    for r in results:
        sec = sum(1 for v in r.get("sections_present", {}).values() if v)
        print(
            f"  focus={r['focus'][:50]:50s} "
            f"ok={r.get('ok')} bytes={r.get('bytes',0):4} "
            f"sections={sec}/{len(REQUIRED_SECTIONS)} "
            f"focus_in_doc={r.get('focus_reflected')} "
            f"in_tmp={r.get('in_tmpdir')}"
        )
    print(f"  pass rate: {n_ok}/{len(results)} ({summary['pass_rate']:.0%})")
    print(f"  mean bytes: {summary['mean_bytes']:.0f}")
    print(f"  mean latency: {summary['mean_latency_ms']:.0f} ms")
    print(f"  results: {out_path}")
    return 0 if n_ok == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
