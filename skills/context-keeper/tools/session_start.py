#!/usr/bin/env python3
"""SessionStart hook entry. Fires the staleness sweep (sweep.py) in the background
so a never-exited desktop session still gets its predecessor transcripts archived.

SessionStart fires reliably even on hosts where SessionEnd never does (e.g. the
Claude desktop app, where sessions are never "exited") — see sweep.py docstring.
Launches sweep.py detached (fire-and-forget) so this hook returns immediately and
never blocks session start; the sweep's own contract keeps it cheap and fail-soft.

Contract: always exit 0. A SessionStart hook failure must never disrupt the host.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path


def log_err(msg: str) -> None:
    ts = time.strftime("%FT%TZ", time.gmtime())
    sys.stderr.write(f"{ts} context-keeper/session_start: {msg}\n")


def resolve_cwd(payload: dict) -> Path | None:
    payload_cwd = payload.get("cwd")
    if payload_cwd is not None and not isinstance(payload_cwd, str):
        log_err(f"invalid-cwd type={type(payload_cwd).__name__}")
    candidates = (
        ("payload", payload_cwd),
        ("CLAUDE_PROJECT_DIR", os.environ.get("CLAUDE_PROJECT_DIR")),
        ("process", os.getcwd()),
    )
    for source, cand in candidates:
        if not isinstance(cand, str) or not cand:
            continue
        try:
            path = Path(cand)
            if path.is_dir():
                return path
        except (ValueError, OSError) as e:
            log_err(f"invalid-cwd source={source} error={type(e).__name__}")
    return None


def main() -> int:
    raw = sys.stdin.read()
    payload: dict = {}
    if raw.strip():
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, dict):
                payload = parsed
            else:
                log_err(f"non-object-payload type={type(parsed).__name__}")
        except json.JSONDecodeError as e:
            log_err(f"json-decode-error: {e}")

    cwd = resolve_cwd(payload)
    if cwd is None:
        log_err("no-resolvable-cwd")
        return 0

    sid = payload.get("session_id", "")
    sid = sid if isinstance(sid, str) else ""

    sweep_py = Path(__file__).parent / "sweep.py"
    if not sweep_py.is_file():
        log_err(f"sweep.py-missing at={sweep_py}")
        return 0

    try:
        subprocess.Popen(
            [sys.executable, str(sweep_py), str(cwd), sid],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
    except Exception as e:  # never crash the host
        log_err(f"sweep-launch-error: {e!r}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
