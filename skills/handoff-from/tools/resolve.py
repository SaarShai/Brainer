#!/usr/bin/env python3
"""Resolve a session id (or 'latest' / 'stuck') to a structured sidecar.

Composes with context-keeper: invokes its extract.py against the target
transcript to produce a compact, grep-able sidecar that the new session can
read without exploding its context. Prints a JSON envelope to stdout.

Usage:
  python3 resolve.py <session-id-or-prefix>
  python3 resolve.py latest
  python3 resolve.py stuck
  python3 resolve.py <sid> --out /tmp/my-sidecar.md
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[2]
EXTRACT_PY = REPO_ROOT / "skills" / "context-keeper" / "tools" / "extract.py"


def project_slug(cwd: Path) -> str:
    """Claude Code encodes /Users/za/Documents/foo → -Users-za-Documents-foo."""
    return "-" + str(cwd).strip("/").replace("/", "-")


def transcripts_dir(cwd: Path) -> Path:
    return Path.home() / ".claude" / "projects" / project_slug(cwd)


def find_transcript(query: str, tdir: Path) -> Path | None:
    if not tdir.is_dir():
        return None
    transcripts = sorted(tdir.glob("*.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not transcripts:
        return None
    if query == "latest":
        return transcripts[0]
    if query == "stuck":
        now = time.time()
        recent = [p for p in transcripts if now - p.stat().st_mtime < 86400]
        if not recent:
            return None
        # least recently modified among files active in last 24h — proxy for "stuck"
        return max(recent, key=lambda p: now - p.stat().st_mtime)
    for p in transcripts:
        if p.stem == query or p.stem.startswith(query):
            return p
    return None


def count_events(path: Path) -> int:
    n = 0
    try:
        with open(path) as f:
            for _ in f:
                n += 1
    except OSError:
        pass
    return n


def fail(reason: str) -> int:
    json.dump({"ok": False, "reason": reason}, sys.stdout)
    sys.stdout.write("\n")
    return 1


def main() -> int:
    ap = argparse.ArgumentParser(prog="handoff-from-resolve")
    ap.add_argument("query", help="session-id (full or prefix), 'latest', or 'stuck'")
    ap.add_argument("--cwd", default=os.getcwd(), help="project working dir (default: cwd)")
    ap.add_argument("--out", default=None, help="sidecar output path (default: $TMPDIR/handoff-from-<sid8>.md)")
    args = ap.parse_args()

    cwd = Path(args.cwd).resolve()
    tdir = transcripts_dir(cwd)
    if not tdir.is_dir():
        return fail(f"no transcripts dir at {tdir}")

    tpath = find_transcript(args.query, tdir)
    if not tpath:
        return fail(f"no transcript matching {args.query!r} under {tdir}")

    if not EXTRACT_PY.is_file():
        return fail(f"extract.py missing at {EXTRACT_PY}")

    sid = tpath.stem
    out = Path(args.out) if args.out else Path(tempfile.gettempdir()) / f"handoff-from-{sid[:8]}.md"
    out.parent.mkdir(parents=True, exist_ok=True)

    try:
        proc = subprocess.run(
            [sys.executable, str(EXTRACT_PY), str(tpath), "--out", str(out), "--session-id", sid],
            capture_output=True, text=True, timeout=60,
        )
    except subprocess.TimeoutExpired:
        return fail("extract.py timed out after 60s")

    if not out.is_file():
        return fail(
            f"extract.py did not produce sidecar at {out} "
            f"(rc={proc.returncode}, stderr={proc.stderr[:200]!r})"
        )

    age = time.time() - tpath.stat().st_mtime
    json.dump({
        "ok": True,
        "transcript_path": str(tpath),
        "sidecar_path": str(out),
        "session_id": sid,
        "events": count_events(tpath),
        "last_event_age_seconds": round(age, 1),
        "sidecar_bytes": out.stat().st_size,
    }, sys.stdout, indent=2)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
