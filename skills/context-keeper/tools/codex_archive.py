#!/usr/bin/env python3
"""Codex Stop-hook worker. Saves a raw copy of the active Codex session into the
project, in addition to Codex's default global store (~/.codex/sessions/).

Codex Stop hooks don't hand us a transcript path, but every rollout records its
`cwd` in the opening `session_meta` line. So we resolve the current project dir,
find the newest rollout whose recorded cwd matches it, and copy it verbatim into
<cwd>/.brainer/sessions/raw/. Idempotent: overwrites by rollout filename, so the
per-turn Stop fires just refresh the copy until the session is complete.

Contract: always exit 0. A Stop-hook failure must never disrupt the host.
"""
from __future__ import annotations

import json
import os
import shutil
import sys
import time
from pathlib import Path

SESSIONS_ROOT = Path.home() / ".codex" / "sessions"
SCAN_LIMIT = 50  # newest-by-mtime rollouts to inspect; bounds per-Stop cost


def log_err(msg: str) -> None:
    ts = time.strftime("%FT%TZ", time.gmtime())
    sys.stderr.write(f"{ts} context-keeper/codex_archive: {msg}\n")


def resolve_cwd() -> Path | None:
    for cand in (os.environ.get("PWD"), os.getcwd()):
        if cand and Path(cand).is_dir():
            return Path(cand).resolve()
    return None


def rollout_cwd(path: Path) -> str | None:
    try:
        with path.open(encoding="utf-8") as fh:
            first = fh.readline()
        meta = json.loads(first)
        payload = meta.get("payload", meta)
        return payload.get("cwd")
    except Exception:
        return None


def find_active_rollout(cwd: Path) -> Path | None:
    if not SESSIONS_ROOT.is_dir():
        return None
    rollouts = sorted(
        SESSIONS_ROOT.glob("*/*/*/rollout-*.jsonl"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )[:SCAN_LIMIT]
    target = str(cwd)
    for rp in rollouts:
        rc = rollout_cwd(rp)
        if rc and Path(rc).resolve() == cwd:
            return rp
    return None


def main() -> int:
    # Drain stdin (Codex passes a JSON payload) but we don't rely on it.
    try:
        sys.stdin.read()
    except Exception:
        pass

    cwd = resolve_cwd()
    if cwd is None:
        log_err("no-resolvable-cwd")
        return 0

    rollout = find_active_rollout(cwd)
    if rollout is None:
        log_err(f"no-matching-rollout cwd={cwd}")
        return 0

    dest_dir = cwd / ".brainer" / "sessions" / "raw"
    try:
        dest_dir.mkdir(parents=True, exist_ok=True)
        gi = dest_dir / ".gitignore"
        if not gi.exists():
            gi.write_text("*\n", encoding="utf-8")
        shutil.copy2(rollout, dest_dir / rollout.name)
    except Exception as e:  # never crash the host
        log_err(f"copy-error: {e!r}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
