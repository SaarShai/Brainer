#!/usr/bin/env python3
"""SessionEnd hook worker. Saves a raw copy of the just-ended transcript into the
project, in addition to the host's default global store.

Lean by design: a verbatim copy of the JSONL (lossless — all generated info), no
enrichment, no secret-scrub. The copy lives under <cwd>/.brainer/sessions/raw/ and
is git-ignored (a self-contained .gitignore is dropped in that dir so it stays
ignored even in repos that don't already ignore .brainer/).

Contract: always exit 0. A SessionEnd hook failure must never disrupt the host.
"""
from __future__ import annotations

import json
import os
import shutil
import sys
import time
from pathlib import Path


def log_err(msg: str) -> None:
    ts = time.strftime("%FT%TZ", time.gmtime())
    sys.stderr.write(f"{ts} context-keeper/archive: {msg}\n")


def resolve_cwd(payload: dict) -> Path | None:
    for cand in (payload.get("cwd"), os.environ.get("CLAUDE_PROJECT_DIR"), os.getcwd()):
        if cand and Path(cand).is_dir():
            return Path(cand)
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

    tp = payload.get("transcript_path", "")
    if not tp or not Path(tp).is_file():
        log_err(f"missing-transcript path={tp!r}")
        return 0

    cwd = resolve_cwd(payload)
    if cwd is None:
        log_err("no-resolvable-cwd")
        return 0

    dest_dir = cwd / ".brainer" / "sessions" / "raw"
    try:
        dest_dir.mkdir(parents=True, exist_ok=True)
        # Self-contained ignore: '*' ignores everything here (git still reads an
        # ignored .gitignore), so the raw copies stay out of version control in
        # any host repo, not just ones that already ignore .brainer/.
        gi = dest_dir / ".gitignore"
        if not gi.exists():
            gi.write_text("*\n", encoding="utf-8")
        dest = dest_dir / Path(tp).name
        shutil.copy2(tp, dest)
    except Exception as e:  # never crash the host
        log_err(f"copy-error: {e!r}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
