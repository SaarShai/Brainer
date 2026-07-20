#!/usr/bin/env python3
"""Regression tests for context-keeper retention.py. No pytest, no network.

Covers: retention-window parsing (default/valid/invalid override, and that
`expire` refuses instead of silently falling back while `status` reports the
default with an explicit "ignored" note), aging/expiry math with synthetic
mtimes, dry-run vs delete behavior (dry-run never removes a file; delete
requires the explicit flag), per-file delete-failure reporting (nonzero
exit, failed file survives, other expired files still removed), and symlink
safety (a symlinked archive directory is refused outright; a symlink sitting
where an archive file would be is skipped, reported, and never unlinked).

There is no `scrub` subcommand and no test for one — see `../POLICY.md` for
why it was removed rather than patched.
"""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).parent))
import retention  # noqa: E402

_RETENTION_PY = Path(__file__).parent / "retention.py"


def _run(args: list, cwd: str | None = None, env: dict | None = None):
    full_env = dict(os.environ)
    if env:
        full_env.update(env)
    return subprocess.run(
        [sys.executable, str(_RETENTION_PY)] + args,
        cwd=cwd, env=full_env, capture_output=True, text=True, timeout=30,
    )


def _touch_with_age(path: Path, days_old: float, content: str = "{}\n") -> None:
    path.write_text(content, encoding="utf-8")
    ts = time.time() - days_old * 86400
    os.utime(path, (ts, ts))


# --- retention window parsing -----------------------------------------------

def test_parse_retention_days_unset_and_empty():
    assert retention.parse_retention_days(None) == (60, False)
    assert retention.parse_retention_days("") == (60, False)


def test_parse_retention_days_valid_override():
    assert retention.parse_retention_days("10") == (10, False)


def test_parse_retention_days_invalid_shapes():
    assert retention.parse_retention_days("not-a-number") == (None, True)
    assert retention.parse_retention_days("0") == (None, True)
    assert retention.parse_retention_days("-5") == (None, True)


def test_expire_rejects_invalid_override_nonzero_exit():
    d = Path(tempfile.mkdtemp())
    try:
        _touch_with_age(d / "old.jsonl", 100)
        for bad in ("not-a-number", "0", "-5"):
            r = _run(["expire", "--dir", str(d), "--dry-run"], env={"BRAINER_RAW_RETENTION_DAYS": bad})
            assert r.returncode != 0, f"expire must refuse override={bad!r}"
            assert bad in r.stderr, r.stderr
            assert (d / "old.jsonl").exists(), "refusal must not touch files"
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_status_reports_default_and_notes_invalid_override_ignored():
    d = Path(tempfile.mkdtemp())
    try:
        _touch_with_age(d / "old.jsonl", 1)
        for bad in ("not-a-number", "0", "-5"):
            r = _run(["status", "--dir", str(d)], env={"BRAINER_RAW_RETENTION_DAYS": bad})
            assert r.returncode == 0, r.stderr
            assert "retention window: 60 days (default)" in r.stdout, r.stdout
            assert f"invalid override ignored: {bad}" in r.stdout, r.stdout
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_status_valid_override_no_ignored_note():
    d = Path(tempfile.mkdtemp())
    try:
        _touch_with_age(d / "old.jsonl", 1)
        r = _run(["status", "--dir", str(d)], env={"BRAINER_RAW_RETENTION_DAYS": "10"})
        assert r.returncode == 0, r.stderr
        assert "retention window: 10 days (from BRAINER_RAW_RETENTION_DAYS)" in r.stdout, r.stdout
        assert "ignored" not in r.stdout, r.stdout
    finally:
        shutil.rmtree(d, ignore_errors=True)


# --- aging / expiry math ------------------------------------------------

def test_expired_files_ages_boundary():
    d = Path(tempfile.mkdtemp())
    try:
        _touch_with_age(d / "old.jsonl", 90)
        _touch_with_age(d / "fresh.jsonl", 5)
        _touch_with_age(d / "boundary.jsonl", 60.5)
        expired, skipped = retention._expired_files(d, 60)
        names = {f.name for f, _, _ in expired}
        assert names == {"old.jsonl", "boundary.jsonl"}, names
        assert skipped == []
    finally:
        shutil.rmtree(d, ignore_errors=True)


# --- status / expire CLI ----------------------------------------------------

def test_status_reports_counts_and_past_window():
    d = Path(tempfile.mkdtemp())
    try:
        _touch_with_age(d / "old.jsonl", 100)
        _touch_with_age(d / "new.jsonl", 1)
        r = _run(["status", "--dir", str(d)], env={"BRAINER_RAW_RETENTION_DAYS": "60"})
        assert r.returncode == 0, r.stderr
        assert "2 files" in r.stdout, r.stdout
        assert "past retention window (60d): 1 file(s)" in r.stdout, r.stdout
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_status_missing_dir_is_clean():
    d = Path(tempfile.mkdtemp()) / "does-not-exist"
    r = _run(["status", "--dir", str(d)])
    assert r.returncode == 0, r.stderr
    assert "no archive directory found" in r.stdout, r.stdout


def test_expire_dry_run_deletes_nothing():
    d = Path(tempfile.mkdtemp())
    try:
        _touch_with_age(d / "old.jsonl", 100)
        r = _run(["expire", "--dir", str(d), "--dry-run"], env={"BRAINER_RAW_RETENTION_DAYS": "60"})
        assert r.returncode == 0, r.stderr
        assert "DRY RUN" in r.stdout, r.stdout
        assert (d / "old.jsonl").exists(), "dry-run must never delete"
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_expire_delete_requires_flag_and_removes_only_expired():
    d = Path(tempfile.mkdtemp())
    try:
        _touch_with_age(d / "old.jsonl", 100)
        _touch_with_age(d / "new.jsonl", 1)
        # No flag at all -> argparse rejects (mutually exclusive group required).
        r = _run(["expire", "--dir", str(d)], env={"BRAINER_RAW_RETENTION_DAYS": "60"})
        assert r.returncode != 0
        assert (d / "old.jsonl").exists()

        r = _run(["expire", "--dir", str(d), "--delete"], env={"BRAINER_RAW_RETENTION_DAYS": "60"})
        assert r.returncode == 0, r.stderr
        assert "deleted 1 file(s)" in r.stdout, r.stdout
        assert not (d / "old.jsonl").exists(), "expired file must be removed"
        assert (d / "new.jsonl").exists(), "non-expired file must survive"
    finally:
        shutil.rmtree(d, ignore_errors=True)


# --- delete-failure handling --------------------------------------------

def test_expire_delete_reports_failure_and_exits_nonzero():
    d = Path(tempfile.mkdtemp())
    try:
        _touch_with_age(d / "locked.jsonl", 100)
        _touch_with_age(d / "removable.jsonl", 100)
        orig_unlink = Path.unlink

        def flaky_unlink(self, *a, **kw):
            if self.name == "locked.jsonl":
                raise PermissionError(f"simulated permission denied: {self}")
            return orig_unlink(self, *a, **kw)

        args = argparse.Namespace(dir=str(d), dry_run=False)
        with mock.patch.object(Path, "unlink", flaky_unlink):
            rc = retention.cmd_expire(args)

        assert rc != 0, "any unlink failure must yield a nonzero exit"
        assert (d / "locked.jsonl").exists(), "failed unlink must leave the file in place"
        assert not (d / "removable.jsonl").exists(), "other expired files must still be removed"
    finally:
        shutil.rmtree(d, ignore_errors=True)


# --- symlink safety -------------------------------------------------------

def test_status_refuses_symlinked_archive_dir():
    parent = Path(tempfile.mkdtemp())
    try:
        real = parent / "real"
        real.mkdir()
        link = parent / "link"
        link.symlink_to(real, target_is_directory=True)
        r = _run(["status", "--dir", str(link)])
        assert r.returncode != 0
        assert "symlink" in r.stderr, r.stderr
    finally:
        shutil.rmtree(parent, ignore_errors=True)


def test_expire_refuses_symlinked_archive_dir():
    parent = Path(tempfile.mkdtemp())
    try:
        real = parent / "real"
        real.mkdir()
        _touch_with_age(real / "old.jsonl", 100)
        link = parent / "link"
        link.symlink_to(real, target_is_directory=True)
        r = _run(["expire", "--dir", str(link), "--delete"], env={"BRAINER_RAW_RETENTION_DAYS": "60"})
        assert r.returncode != 0
        assert "symlink" in r.stderr, r.stderr
        assert (real / "old.jsonl").exists(), "refusal must not touch files behind the symlinked dir"
    finally:
        shutil.rmtree(parent, ignore_errors=True)


def test_expire_skips_symlink_files_and_reports_them():
    d = Path(tempfile.mkdtemp())
    other = Path(tempfile.mkdtemp())
    try:
        target = other / "target.jsonl"
        _touch_with_age(target, 100)
        link = d / "linked.jsonl"
        link.symlink_to(target)
        _touch_with_age(d / "real_old.jsonl", 100)

        r = _run(["expire", "--dir", str(d), "--delete"], env={"BRAINER_RAW_RETENTION_DAYS": "60"})
        assert r.returncode == 0, r.stderr
        assert "skipped symlink" in r.stdout, r.stdout
        assert link.exists() and link.is_symlink(), "symlink must never be unlinked by expire"
        assert target.exists(), "symlink target must survive — only the link entry was ever a candidate"
        assert not (d / "real_old.jsonl").exists(), "real expired file must still be removed"
    finally:
        shutil.rmtree(d, ignore_errors=True)
        shutil.rmtree(other, ignore_errors=True)


def main():
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"pass {fn.__name__}")
    print(f"OK ({len(fns)} tests)")


if __name__ == "__main__":
    main()
