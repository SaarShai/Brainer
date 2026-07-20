#!/usr/bin/env python3
"""Retention / deletion CLI for the raw session archive.

`archive.py` (SessionEnd hook) writes lossless, unredacted copies of every
session transcript to `<cwd>/.brainer/sessions/raw/*.jsonl`, forever, with no
scrub. This tool closes the retention/deletion gap named in the 2026-07
skills-overhaul memory-research report. Full policy: `../POLICY.md`.

Two subcommands, both explicit-invocation only (never run from a hook):

  status                 count files, ages, total bytes, how many are past
                          the retention window.
  expire --dry-run|--delete
                          list (or actually delete) archive files older than
                          the retention window. Deletion is NEVER automatic —
                          `--delete` must be typed by a human (no-drop
                          doctrine: nothing disappears silently).

Retention window defaults to 60 days; override with
`BRAINER_RAW_RETENTION_DAYS`. An invalid override (not a positive integer)
is NEVER silently treated as "use the default" for a destructive command —
`expire` refuses and exits nonzero; `status` uses the default but says so
explicitly so a broken override doesn't look like it's in effect.

There is no `scrub`/redaction subcommand here. A prior version shipped one
that reported success while still leaking secrets (JSON-escaped quotes,
URL-safe token alphabets) — a redactor that lies about having redacted is
worse than no redactor, so it was removed rather than patched. See
`../POLICY.md` for what a future scrub would need to pass before it ships.

Symlink safety: this tool refuses to operate at all if the archive directory
itself is a symlink (an lstat-based check, so a symlinked directory pointing
at unrelated files can't be silently walked or deleted-into), and skips —
rather than deletes — any symlink found in place of an archived file during
`expire`, reporting what was skipped.
"""
from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent

DEFAULT_RETENTION_DAYS = 60


def _human_bytes(n: int) -> str:
    size = float(n)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if size < 1024 or unit == "TB":
            return f"{size:.1f}{unit}" if unit != "B" else f"{int(size)}B"
        size /= 1024
    return f"{size:.1f}TB"


def parse_retention_days(raw: str | None) -> tuple[int | None, bool]:
    """Parse the `BRAINER_RAW_RETENTION_DAYS` override.

    Returns `(days, invalid)`. `invalid=True` means `raw` was set to
    something unusable (not an integer, or <= 0) — callers must NOT silently
    fall back to the default in that case; they must surface it explicitly
    (nonzero exit for `expire`, an explicit "ignored" note for `status`).
    An unset/empty `raw` is not an override at all: `(DEFAULT_RETENTION_DAYS,
    False)`.
    """
    if not raw:
        return DEFAULT_RETENTION_DAYS, False
    try:
        val = int(raw)
    except ValueError:
        return None, True
    if val <= 0:
        return None, True
    return val, False


def resolve_archive_dir(explicit: str | None) -> Path:
    if explicit:
        return Path(explicit)
    base = os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()
    return Path(base) / ".brainer" / "sessions" / "raw"


def refuse_if_symlink_dir(archive_dir: Path) -> str | None:
    """Return an error message if `archive_dir` itself is a symlink, else None.

    `Path.is_symlink()` is lstat-based (does not follow the link), so this
    catches a symlinked archive directory even though `Path.is_dir()` would
    happily follow it and treat the link's target as trustworthy.
    """
    try:
        if archive_dir.is_symlink():
            return f"refusing to operate on {archive_dir}: it is a symlink, not a real directory"
    except OSError:
        pass
    return None


def cmd_status(args: argparse.Namespace) -> int:
    archive_dir = resolve_archive_dir(args.dir)
    print(f"archive dir: {archive_dir}")

    err = refuse_if_symlink_dir(archive_dir)
    if err:
        print(err, file=sys.stderr)
        return 1

    raw_override = os.environ.get("BRAINER_RAW_RETENTION_DAYS")
    window_days, invalid = parse_retention_days(raw_override)
    if invalid:
        window_days = DEFAULT_RETENTION_DAYS
        print(f"retention window: {window_days} days (default) — invalid override ignored: {raw_override}")
    else:
        override = " (from BRAINER_RAW_RETENTION_DAYS)" if raw_override else " (default)"
        print(f"retention window: {window_days} days{override}")

    if not archive_dir.is_dir():
        print("no archive directory found — nothing archived yet")
        return 0
    files = sorted(p for p in archive_dir.glob("*.jsonl") if p.is_file())
    if not files:
        print("0 files, 0 bytes")
        return 0
    now = time.time()
    total_bytes = 0
    past_window = 0
    oldest_age = 0.0
    newest_age = float("inf")
    for f in files:
        st = f.stat()
        age_days = (now - st.st_mtime) / 86400
        total_bytes += st.st_size
        oldest_age = max(oldest_age, age_days)
        newest_age = min(newest_age, age_days)
        if age_days > window_days:
            past_window += 1
    print(f"{len(files)} files, {total_bytes} bytes ({_human_bytes(total_bytes)})")
    print(f"oldest: {oldest_age:.1f}d, newest: {newest_age:.1f}d")
    print(f"past retention window ({window_days}d): {past_window} file(s)")
    return 0


def _expired_files(archive_dir: Path, window_days: int) -> tuple[list[tuple[Path, float, int]], list[Path]]:
    """Return `(expired, skipped_symlinks)`.

    Symlinks are never treated as deletable archive files — `f.is_symlink()`
    (lstat-based) is checked before `f.is_file()` so a symlink pointing at a
    regular file is reported and skipped rather than silently unlinked.
    """
    now = time.time()
    out = []
    skipped_symlinks = []
    for f in sorted(archive_dir.glob("*.jsonl")):
        if f.is_symlink():
            skipped_symlinks.append(f)
            continue
        if not f.is_file():
            continue
        st = f.stat()
        age_days = (now - st.st_mtime) / 86400
        if age_days > window_days:
            out.append((f, age_days, st.st_size))
    return out, skipped_symlinks


def cmd_expire(args: argparse.Namespace) -> int:
    archive_dir = resolve_archive_dir(args.dir)

    err = refuse_if_symlink_dir(archive_dir)
    if err:
        print(err, file=sys.stderr)
        return 1

    raw_override = os.environ.get("BRAINER_RAW_RETENTION_DAYS")
    window_days, invalid = parse_retention_days(raw_override)
    if invalid:
        print(
            f"invalid BRAINER_RAW_RETENTION_DAYS={raw_override!r}: must be a positive "
            "integer number of days; refusing to guess a window for a deletion command",
            file=sys.stderr,
        )
        return 1

    if not archive_dir.is_dir():
        print(f"no archive directory at {archive_dir}")
        return 0
    expired, skipped_symlinks = _expired_files(archive_dir, window_days)
    for s in skipped_symlinks:
        print(f"skipped symlink (not a regular archive file): {s}")
    if not expired:
        print(f"no files older than {window_days} days")
        return 0
    total_bytes = sum(size for _, _, size in expired)
    if args.dry_run:
        print(f"DRY RUN — would delete {len(expired)} file(s), {total_bytes} bytes ({_human_bytes(total_bytes)}):")
        for f, age, size in expired:
            print(f"  {f}  age={age:.1f}d  size={size}")
        print("re-run with --delete to actually remove these files (deletion is never automatic)")
        return 0
    # --delete
    removed = []
    failed = []
    for f, age, size in expired:
        try:
            f.unlink()
            removed.append((f, age, size))
        except OSError as e:
            failed.append((f, e))
            print(f"FAILED to delete {f}: {e}", file=sys.stderr)
    removed_bytes = sum(size for _, _, size in removed)
    print(f"deleted {len(removed)} file(s), {removed_bytes} bytes ({_human_bytes(removed_bytes)}):")
    for f, age, size in removed:
        print(f"  removed {f}  age={age:.1f}d  size={size}")
    if failed:
        print(f"{len(failed)} file(s) FAILED to delete — see FAILED lines above", file=sys.stderr)
        return 1
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="retention.py",
        description="Retention / deletion for .brainer/sessions/raw/. See ../POLICY.md.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_status = sub.add_parser("status", help="count files, ages, total bytes, how many are past the window")
    p_status.add_argument("--dir", help="override archive directory (default: <project>/.brainer/sessions/raw)")

    p_expire = sub.add_parser("expire", help="list or delete archive files older than the retention window")
    p_expire.add_argument("--dir", help="override archive directory")
    grp = p_expire.add_mutually_exclusive_group(required=True)
    grp.add_argument("--dry-run", action="store_true", help="list what would be deleted; deletes nothing")
    grp.add_argument("--delete", action="store_true", help="actually delete; required for any removal")

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command == "status":
        return cmd_status(args)
    if args.command == "expire":
        return cmd_expire(args)
    parser.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
