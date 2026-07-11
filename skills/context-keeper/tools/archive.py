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
