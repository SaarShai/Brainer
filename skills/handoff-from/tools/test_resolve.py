#!/usr/bin/env python3
"""Integration smoke test for handoff-from/tools/resolve.py.

Run from anywhere:
  python3 skills/handoff-from/tools/test_resolve.py
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
RESOLVE = HERE / "resolve.py"
REPO = HERE.parents[2]


def run(*args: str) -> tuple[int, dict, str]:
    proc = subprocess.run(
        [sys.executable, str(RESOLVE), *args],
        capture_output=True, text=True, cwd=str(REPO),
    )
    try:
        return proc.returncode, json.loads(proc.stdout), proc.stderr
    except json.JSONDecodeError:
        return proc.returncode, {"_raw": proc.stdout}, proc.stderr


def main() -> int:
    fails: list[tuple[str, dict, str]] = []

    # 1. "latest" resolves to a real session with a non-empty sidecar
    rc, out, err = run("latest")
    if rc != 0 or not out.get("ok"):
        fails.append(("latest-resolve", out, err))
    else:
        sidecar = Path(out["sidecar_path"])
        if not sidecar.is_file() or sidecar.stat().st_size == 0:
            fails.append(("latest-sidecar-empty", out, ""))
        latest_sid = out.get("session_id", "")

        # 2. prefix of latest sid resolves to the same session
        if latest_sid:
            rc2, out2, err2 = run(latest_sid[:8])
            if rc2 != 0 or out2.get("session_id") != latest_sid:
                fails.append(("prefix-match", out2, err2))

    # 3. nonexistent fails cleanly with structured error (not crash)
    rc, out, err = run("zzzz-definitely-not-a-session")
    if rc == 0 or out.get("ok") is True or "reason" not in out:
        fails.append(("nonexistent-should-fail-clean", out, err))

    if fails:
        for name, out, err in fails:
            print(f"FAIL {name}: out={out} stderr={err[:200]}", file=sys.stderr)
        return 1
    print("OK 3/3")
    return 0


if __name__ == "__main__":
    sys.exit(main())
