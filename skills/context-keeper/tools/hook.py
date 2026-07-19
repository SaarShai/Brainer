#!/usr/bin/env python3
"""PreCompact hook entry. Reads Claude Code JSON payload from stdin, runs extract.py,
forwards the terse pointer to stdout (which Claude Code prepends to the compaction prompt).

Contract: always exit 0. Compaction must not be blocked by a hook failure.
"""
import json
import os
import subprocess
import sys
import time
from pathlib import Path


def log_err(msg: str) -> None:
    ts = time.strftime("%FT%TZ", time.gmtime())
    sys.stderr.write(f"{ts} context-keeper: {msg}\n")


def resolve_project_root(payload: dict) -> Path | None:
    payload_cwd = payload.get("cwd")
    if payload_cwd is not None and not isinstance(payload_cwd, str):
        log_err(f"invalid-cwd type={type(payload_cwd).__name__}")
    candidates = (
        ("payload", payload_cwd),
        ("CLAUDE_PROJECT_DIR", os.environ.get("CLAUDE_PROJECT_DIR")),
        ("process", os.getcwd()),
    )
    for source, candidate in candidates:
        if not isinstance(candidate, str) or not candidate:
            continue
        try:
            path = Path(candidate)
            if path.is_dir():
                return path
        except (ValueError, OSError) as e:
            log_err(f"invalid-cwd source={source} error={type(e).__name__}")
    return None


def main() -> int:
    raw = sys.stdin.read()
    if not raw.strip():
        log_err("empty-payload")
        return 0
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as e:
        log_err(f"json-decode-error: {e}")
        return 0
    if not isinstance(payload, dict):
        log_err(f"non-object-payload type={type(payload).__name__}")
        return 0

    tp = payload.get("transcript_path", "")
    sid = payload.get("session_id", "")
    trigger = payload.get("trigger", "auto")

    if not isinstance(tp, str):
        log_err(f"invalid-transcript-path type={type(tp).__name__}")
        return 0
    if not tp:
        log_err(f"missing-transcript path={tp!r}")
        return 0
    try:
        transcript_exists = Path(tp).is_file()
    except (ValueError, OSError) as e:
        log_err(f"invalid-transcript-path error={type(e).__name__}")
        return 0
    if not transcript_exists:
        log_err(f"missing-transcript path={tp!r}")
        return 0
    if not isinstance(sid, str):
        log_err(f"invalid-session-id type={type(sid).__name__} fallback='unknown'")
        sid = "unknown"
    elif not sid:
        sid = "unknown"
    if not isinstance(trigger, str):
        log_err(f"invalid-trigger type={type(trigger).__name__} fallback='auto'")
        trigger = "auto"
    elif not trigger:
        trigger = "auto"

    extract_py = Path(__file__).parent / "extract.py"
    if not extract_py.is_file():
        log_err(f"extract.py-missing at={extract_py}")
        return 0

    project_root = resolve_project_root(payload)
    if project_root is None:
        log_err("no-resolvable-cwd")
        return 0

    env = os.environ.copy()
    env["TOKEN_ECONOMY_ROOT"] = str(project_root)

    try:
        subprocess.run(
            [sys.executable, str(extract_py), tp, "--pointer-only",
             "--session-id", sid, "--trigger", trigger],
            timeout=30,
            check=False,
            env=env,
        )
    except subprocess.TimeoutExpired:
        log_err(f"extract-timeout sid={sid} trigger={trigger}")
    except Exception as e:  # never crash the host
        log_err(f"extract-error: {e!r}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
