#!/usr/bin/env python3
"""Regression tests for context-keeper sweep.py. No pytest, no network.

Motivating gap (found only by manual inspection, 2026-07-20): on the Claude
desktop app SessionEnd never fires, so archive.py's raw-transcript archive was
silently dead. sweep.py piggybacks on SessionStart/PreCompact instead. The
core contract this file proves:

- a stale, unarchived fake transcript IS picked up and archived;
- an already-archived transcript (matching size in .brainer/sessions/raw/) is
  skipped, not re-copied;
- a fresh (non-stale) transcript is left alone;
- the current session's own transcript is never swept, even if stale;
- sweep() never raises on a missing source directory.
"""
from __future__ import annotations

import os
import shutil
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
import sweep  # noqa: E402


def _touch_with_age(path: Path, hours_old: float, content: str = '{"line": 1}\n') -> None:
    path.write_text(content, encoding="utf-8")
    ts = time.time() - hours_old * 3600
    os.utime(path, (ts, ts))


def _fake_home_and_project(tmp_dir: Path):
    """Builds <tmp>/project (fake cwd) and the matching fake
    ~/.claude/projects/<encoded-cwd>/ transcript dir sweep.py resolves to."""
    home = tmp_dir / "home"
    project = tmp_dir / "cwd" / "project"
    project.mkdir(parents=True)
    home.mkdir(parents=True)
    src_dir = home / ".claude" / "projects" / sweep.encode_project_dir(project)
    src_dir.mkdir(parents=True)
    return home, project, src_dir


def test_stale_unarchived_transcript_is_swept():
    with tempfile.TemporaryDirectory() as td:
        home, project, src_dir = _fake_home_and_project(Path(td))
        stale = src_dir / "stale-session.jsonl"
        _touch_with_age(stale, hours_old=48)

        real_home = Path.home
        Path.home = staticmethod(lambda: home)
        try:
            n = sweep.sweep(project, current_session_id=None, stale_seconds=24 * 3600)
        finally:
            Path.home = real_home

        dest = project / ".brainer" / "sessions" / "raw" / "stale-session.jsonl"
        assert n == 1, f"expected 1 archived, got {n}"
        assert dest.is_file(), "stale unarchived transcript was not archived"
        assert dest.read_text(encoding="utf-8") == stale.read_text(encoding="utf-8")
        assert (project / ".brainer" / "sessions" / "raw" / ".gitignore").is_file()


def test_already_archived_transcript_is_skipped():
    with tempfile.TemporaryDirectory() as td:
        home, project, src_dir = _fake_home_and_project(Path(td))
        stale = src_dir / "already-done.jsonl"
        _touch_with_age(stale, hours_old=48, content='{"line": 1}\n')

        dest_dir = project / ".brainer" / "sessions" / "raw"
        dest_dir.mkdir(parents=True)
        dest = dest_dir / "already-done.jsonl"
        dest.write_text(stale.read_text(encoding="utf-8"), encoding="utf-8")
        sentinel_mtime = dest.stat().st_mtime

        real_home = Path.home
        Path.home = staticmethod(lambda: home)
        try:
            n = sweep.sweep(project, current_session_id=None, stale_seconds=24 * 3600)
        finally:
            Path.home = real_home

        assert n == 0, f"expected 0 archived (already present), got {n}"
        assert dest.stat().st_mtime == sentinel_mtime, "already-archived file was needlessly re-copied"


def test_fresh_transcript_is_not_swept():
    with tempfile.TemporaryDirectory() as td:
        home, project, src_dir = _fake_home_and_project(Path(td))
        fresh = src_dir / "fresh-session.jsonl"
        _touch_with_age(fresh, hours_old=1)

        real_home = Path.home
        Path.home = staticmethod(lambda: home)
        try:
            n = sweep.sweep(project, current_session_id=None, stale_seconds=24 * 3600)
        finally:
            Path.home = real_home

        dest = project / ".brainer" / "sessions" / "raw" / "fresh-session.jsonl"
        assert n == 0, f"expected 0 archived (not stale yet), got {n}"
        assert not dest.exists(), "fresh transcript should not be archived"


def test_current_session_never_swept_even_if_stale():
    with tempfile.TemporaryDirectory() as td:
        home, project, src_dir = _fake_home_and_project(Path(td))
        current = src_dir / "current-sid.jsonl"
        _touch_with_age(current, hours_old=48)

        real_home = Path.home
        Path.home = staticmethod(lambda: home)
        try:
            n = sweep.sweep(project, current_session_id="current-sid", stale_seconds=24 * 3600)
        finally:
            Path.home = real_home

        dest = project / ".brainer" / "sessions" / "raw" / "current-sid.jsonl"
        assert n == 0, f"expected 0 archived (current session excluded), got {n}"
        assert not dest.exists()


def test_missing_source_dir_returns_zero_never_raises():
    with tempfile.TemporaryDirectory() as td:
        tmp_dir = Path(td)
        home = tmp_dir / "home"
        project = tmp_dir / "cwd" / "project"
        project.mkdir(parents=True)
        home.mkdir(parents=True)
        # No ~/.claude/projects/<encoded>/ dir created at all.
        real_home = Path.home
        Path.home = staticmethod(lambda: home)
        try:
            n = sweep.sweep(project)
        finally:
            Path.home = real_home
        assert n == 0


def main():
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"pass {fn.__name__}")
    print(f"OK ({len(fns)} tests)")


if __name__ == "__main__":
    main()
