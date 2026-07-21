#!/usr/bin/env python3
"""Staleness sweep: archives session transcripts that SessionEnd never fired for.

On hosts where SessionEnd never fires (e.g. the Claude desktop app — sessions are
never "exited"), archive.py's SessionEnd -> raw-copy path is silently dead
(live-test finding, 2026-07-20). This sweep piggybacks on hooks that DO fire
(SessionStart, PreCompact): scan the host's per-project transcript directory
(~/.claude/projects/<encoded-cwd>/*.jsonl) for transcripts that are (a) not the
current session, (b) mtime-stale beyond a threshold, and (c) not yet archived
under .brainer/sessions/raw/ — then archive them.

Idempotent: skips a transcript whose raw copy already exists with a matching size.
Fail-soft: every error is logged and swallowed; this must never raise or block
the caller. Cheap: a directory glob + stat per file, no transcript parsing.
"""
from __future__ import annotations

import shutil
import sys
import time
from pathlib import Path

STALE_SECONDS_DEFAULT = 24 * 60 * 60


def log_err(msg: str) -> None:
    ts = time.strftime("%FT%TZ", time.gmtime())
    sys.stderr.write(f"{ts} context-keeper/sweep: {msg}\n")


def encode_project_dir(cwd: Path) -> str:
    # Mirrors Claude Code's own ~/.claude/projects/<encoded-cwd> naming: every
    # path separator becomes '-' (verified against live ~/.claude/projects/ entries).
    return str(cwd).replace("/", "-")


def transcript_dir_for(cwd: Path) -> Path:
    return Path.home() / ".claude" / "projects" / encode_project_dir(cwd)


def already_archived(src: Path, dest: Path) -> bool:
    if not dest.exists():
        return False
    try:
        return dest.stat().st_size == src.stat().st_size
    except OSError:
        return False


def sweep(cwd: Path, current_session_id: str | None = None,
          stale_seconds: int = STALE_SECONDS_DEFAULT) -> int:
    """Archive stale, unarchived transcripts for `cwd`. Returns count archived.

    Never raises — every error is logged to stderr and swallowed so a sweep
    failure can never disrupt the hook that triggered it.
    """
    archived = 0
    try:
        src_dir = transcript_dir_for(cwd)
        if not src_dir.is_dir():
            return 0
        dest_dir = cwd / ".brainer" / "sessions" / "raw"
        now = time.time()
        for f in sorted(src_dir.glob("*.jsonl")):
            try:
                if current_session_id and f.stem == current_session_id:
                    continue
                mtime = f.stat().st_mtime
                if now - mtime < stale_seconds:
                    continue
                dest = dest_dir / f.name
                if already_archived(f, dest):
                    continue
                dest_dir.mkdir(parents=True, exist_ok=True)
                # Self-contained ignore, same as archive.py: stays out of version
                # control even in a repo that doesn't already ignore .brainer/.
                gi = dest_dir / ".gitignore"
                if not gi.exists():
                    gi.write_text("*\n", encoding="utf-8")
                shutil.copy2(f, dest)
                archived += 1
            except Exception as e:  # per-file fail-soft: one bad file must not stop the sweep
                log_err(f"file-error path={f} error={e!r}")
    except Exception as e:  # never crash the caller
        log_err(f"sweep-error: {e!r}")
    return archived


def main() -> int:
    if len(sys.argv) < 2:
        log_err("usage: sweep.py <project_root> [session_id] [stale_seconds]")
        return 0
    try:
        cwd = Path(sys.argv[1])
        session_id = sys.argv[2] if len(sys.argv) > 2 and sys.argv[2] else None
        stale_seconds = int(sys.argv[3]) if len(sys.argv) > 3 and sys.argv[3] else STALE_SECONDS_DEFAULT
        n = sweep(cwd, session_id, stale_seconds)
        if n:
            log_err(f"archived {n} stale transcript(s) for {cwd}")
    except Exception as e:
        log_err(f"main-error: {e!r}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
