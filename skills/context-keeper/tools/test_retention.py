#!/usr/bin/env python3
"""Regression tests for context-keeper retention.py. No pytest, no network.

Covers: aging/expiry math with synthetic mtimes, dry-run vs delete behavior
(dry-run never removes a file; delete requires the explicit flag), scrub on a
synthetic transcript with planted secrets (every planted class caught,
non-secret content byte-identical, original untouched without --replace,
original replaced only with --replace), and a real-file smoke test against
the smallest file in .brainer/sessions/raw/ (existence-only — real content
varies, so this asserts the tool runs clean and writes the sibling, not
specific counts).
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

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


# --- retention window math -------------------------------------------------

def test_get_retention_days_default_and_override():
    saved = os.environ.pop("BRAINER_RAW_RETENTION_DAYS", None)
    try:
        assert retention.get_retention_days() == 60
        os.environ["BRAINER_RAW_RETENTION_DAYS"] = "10"
        assert retention.get_retention_days() == 10
        os.environ["BRAINER_RAW_RETENTION_DAYS"] = "not-a-number"
        assert retention.get_retention_days() == 60
        os.environ["BRAINER_RAW_RETENTION_DAYS"] = "-5"
        assert retention.get_retention_days() == 60
    finally:
        if saved is None:
            os.environ.pop("BRAINER_RAW_RETENTION_DAYS", None)
        else:
            os.environ["BRAINER_RAW_RETENTION_DAYS"] = saved


def test_expired_files_ages_boundary():
    d = Path(tempfile.mkdtemp())
    try:
        _touch_with_age(d / "old.jsonl", 90)
        _touch_with_age(d / "fresh.jsonl", 5)
        _touch_with_age(d / "boundary.jsonl", 60.5)
        expired = retention._expired_files(d, 60)
        names = {f.name for f, _, _ in expired}
        assert names == {"old.jsonl", "boundary.jsonl"}, names
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


# --- scrub: synthetic planted secrets ---------------------------------------

_PLANTED = {
    "openai_key": "sk-proj-ABCDEFGH1234567890abcdEFGHijkl",
    "github_pat": "ghp_ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789",
    "aws_akid": "AKIAABCDEFGHIJKLMNOP",
    "bearer": "Authorization: Bearer abcdefghijklmnopqrstuvwxyz012345",
    "password_assign": 'password = "hunter2superlongsecretvalue123"',
    "high_entropy_hex": "a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4",
    "non_owner_email": "someone.else@example.com",
}

_NON_SECRET_LINE = 'the quick brown fox jumps over the lazy dog, count=42, path=/tmp/ok'


def _make_synthetic_transcript(d: Path) -> Path:
    lines = [
        '{"type":"user","message":{"role":"user","content":"my key is %s"}}' % _PLANTED["openai_key"],
        '{"type":"user","message":{"role":"user","content":"token %s"}}' % _PLANTED["github_pat"],
        '{"type":"user","message":{"role":"user","content":"aws id %s"}}' % _PLANTED["aws_akid"],
        '{"type":"user","message":{"role":"user","content":"%s"}}' % _PLANTED["bearer"],
        '{"type":"user","message":{"role":"user","content":"%s"}}' % _PLANTED["password_assign"],
        # Unescaped top-level key:value pair — the realistic shape (a real
        # JSON field on the line), not a string-within-a-string.
        '{"type":"user","session_id":"%s","message":{"role":"user","content":"ok"}}' % _PLANTED["high_entropy_hex"],
        '{"type":"user","message":{"role":"user","content":"reach me at %s"}}' % _PLANTED["non_owner_email"],
        '{"type":"user","message":{"role":"user","content":"%s"}}' % _NON_SECRET_LINE,
    ]
    p = d / "synthetic.jsonl"
    p.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return p


def test_scrub_catches_all_planted_classes_and_preserves_non_secret_content():
    d = Path(tempfile.mkdtemp())
    try:
        src = _make_synthetic_transcript(d)
        original_bytes = src.read_bytes()
        r = _run(["scrub", str(src)], env={"BRAINER_OWNER_EMAIL": "owner@example.com"})
        assert r.returncode == 0, r.stderr

        sibling = d / "synthetic.redacted.jsonl"
        assert sibling.exists(), "scrub must write a .redacted.jsonl sibling"
        scrubbed = sibling.read_text(encoding="utf-8")

        for label, secret in _PLANTED.items():
            assert secret not in scrubbed, f"{label} leaked: {secret!r} still present"

        # Non-secret content survives byte-identical.
        assert _NON_SECRET_LINE in scrubbed
        assert "the quick brown fox" in scrubbed

        # Original untouched without --replace.
        assert src.read_bytes() == original_bytes, "original must be untouched without --replace"
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_scrub_keeps_owner_email_redacts_others():
    d = Path(tempfile.mkdtemp())
    try:
        src = d / "emails.jsonl"
        src.write_text(
            '{"content":"cc owner@example.com and someone.else@example.com"}\n',
            encoding="utf-8",
        )
        r = _run(["scrub", str(src)], env={"BRAINER_OWNER_EMAIL": "owner@example.com"})
        assert r.returncode == 0, r.stderr
        scrubbed = (d / "emails.redacted.jsonl").read_text(encoding="utf-8")
        assert "owner@example.com" in scrubbed, "owner's own email must survive"
        assert "someone.else@example.com" not in scrubbed
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_scrub_replace_flag_overwrites_original():
    d = Path(tempfile.mkdtemp())
    try:
        src = d / "replace_me.jsonl"
        src.write_text('{"content":"key sk-proj-ABCDEFGH1234567890abcdEFGHijkl"}\n', encoding="utf-8")
        r = _run(["scrub", str(src), "--replace"])
        assert r.returncode == 0, r.stderr
        assert "sk-proj-ABCDEFGH1234567890abcdEFGHijkl" not in src.read_text(encoding="utf-8")
        assert not (d / "replace_me.redacted.jsonl").exists(), "--replace merges sibling into original"
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_scrub_without_replace_never_touches_original_even_when_secrets_found():
    d = Path(tempfile.mkdtemp())
    try:
        src = d / "no_replace.jsonl"
        content = '{"content":"key sk-proj-ABCDEFGH1234567890abcdEFGHijkl"}\n'
        src.write_text(content, encoding="utf-8")
        before_mtime = src.stat().st_mtime
        r = _run(["scrub", str(src)])
        assert r.returncode == 0, r.stderr
        assert src.read_text(encoding="utf-8") == content
        assert src.stat().st_mtime == before_mtime
    finally:
        shutil.rmtree(d, ignore_errors=True)


# --- real-archive smoke test -------------------------------------------------

def test_scrub_real_archive_smoke():
    real_dir = Path(__file__).resolve().parents[3] / ".brainer" / "sessions" / "raw"
    if not real_dir.is_dir():
        print("skip: no real archive dir present")
        return
    candidates = [p for p in real_dir.glob("*.jsonl") if p.is_file()]
    if not candidates:
        print("skip: no real archive files present")
        return
    smallest = min(candidates, key=lambda p: p.stat().st_size)

    tmp_copy_dir = Path(tempfile.mkdtemp())
    try:
        # Work on a copy so the real archive is never touched (no --replace
        # anyway, but the sibling would otherwise land next to the original).
        copy_path = tmp_copy_dir / smallest.name
        shutil.copy2(smallest, copy_path)
        original_bytes = smallest.read_bytes()

        r = _run(["scrub", str(copy_path)])
        assert r.returncode == 0, r.stderr
        print(f"real-file smoke ({smallest.name}, {smallest.stat().st_size} bytes): {r.stdout.strip()}")

        sibling = copy_path.with_name(copy_path.name[: -len(".jsonl")] + ".redacted.jsonl")
        assert sibling.exists()

        # Real archive itself must be provably untouched.
        assert smallest.read_bytes() == original_bytes, "real archived file must never be modified"
    finally:
        shutil.rmtree(tmp_copy_dir, ignore_errors=True)


def main():
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"pass {fn.__name__}")
    print(f"OK ({len(fns)} tests)")


if __name__ == "__main__":
    main()
