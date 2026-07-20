#!/usr/bin/env python3
"""Retention / deletion / redaction CLI for the raw session archive.

`archive.py` (SessionEnd hook) writes lossless, unredacted copies of every
session transcript to `<cwd>/.brainer/sessions/raw/*.jsonl`, forever, with no
scrub. This tool closes the retention/redaction/deletion gap named in the
2026-07 skills-overhaul memory-research report. Full policy: `../POLICY.md`.

Three subcommands, all explicit-invocation only (never run from a hook):

  status                 count files, ages, total bytes, how many are past
                          the retention window.
  expire --dry-run|--delete
                          list (or actually delete) archive files older than
                          the retention window. Deletion is NEVER automatic —
                          `--delete` must be typed by a human (no-drop
                          doctrine: nothing disappears silently).
  scrub <file> [--replace]
                          redact secrets from one archived transcript into a
                          `.redacted.jsonl` sibling. The original is left
                          untouched unless `--replace` is given.

Retention window defaults to 60 days; override with
`BRAINER_RAW_RETENTION_DAYS`.

Redaction lessons this file honors (see wiki `queries/external-validation`
and `skills/_shared/audit_redact.py`, both consulted before writing any
regex here):

  - Redact BEFORE any re-serialization. `scrub` reads/writes raw text lines
    (`splitlines(keepends=True)` + regex substitution) and NEVER parses the
    JSONL into objects and re-dumps it — a parse/re-dump round-trip can
    reorder keys, change escaping, or duplicate content, all of which would
    make the "non-secret content is byte-identical" guarantee false.
  - No `\\b` word-boundary anchors. `\\b` silently fails to match at a
    boundary between two "word" characters (e.g. `_` next to a token) or at
    a non-ASCII neighbor, which under-redacts — the one failure mode that is
    never acceptable in a security sink. Every pattern below uses explicit
    character-class lookarounds instead.

The heavy lifting for named-secret families (API keys, bearer/OAuth tokens,
password-like assignments, PEM blocks, ...) is delegated to the shared,
previously-hardened `skills/_shared/audit_redact.redact_secrets()` — borrowed,
not reimplemented. This file adds two classes that module doesn't cover:
high-entropy hex/base64 runs sitting next to a key, and non-owner emails.
"""
from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
_SHARED_DIR = Path(__file__).resolve().parents[2] / "_shared"  # skills/_shared
if str(_SHARED_DIR) not in sys.path:
    sys.path.insert(0, str(_SHARED_DIR))

DEFAULT_RETENTION_DAYS = 60
REDACTED_MARKER = "[REDACTED]"  # matches skills/_shared/audit_redact.REDACTED
REDACTED_EMAIL_MARKER = "[REDACTED-EMAIL]"

# High-entropy hex/base64 run (>=32 chars) sitting immediately after a JSON
# key/colon or a bareword key/`=`/`:` — "key-adjacent", not just any long
# string in prose. Standard base64 alphabet (no `-`/`_`) deliberately excludes
# hyphenated slugs/UUIDs-with-dashes so ordinary prose and identifiers don't
# false-positive. No `\b` used; the key/delimiter prefix and optional-quote
# suffix are the only anchors, both explicit character classes.
_HIGH_ENTROPY_RE = re.compile(
    r'((?:"[A-Za-z0-9_.\-]+"|[A-Za-z_][A-Za-z0-9_]*)\s*[:=]\s*"?)'
    r'([0-9a-fA-F]{32,}|[A-Za-z0-9+/]{32,}={0,2})'
    r'("?)'
)

# Email address. Lookaround uses explicit character classes (NOT \b) so a
# leading/trailing char that is itself part of the local-part/domain charset
# correctly blocks the match instead of \b's word-char ambiguity.
_EMAIL_RE = re.compile(
    r'(?<![A-Za-z0-9._%+-])'
    r'[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}'
    r'(?![A-Za-z0-9._%+-])'
)


def _human_bytes(n: int) -> str:
    size = float(n)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if size < 1024 or unit == "TB":
            return f"{size:.1f}{unit}" if unit != "B" else f"{int(size)}B"
        size /= 1024
    return f"{size:.1f}TB"


def get_retention_days() -> int:
    raw = os.environ.get("BRAINER_RAW_RETENTION_DAYS")
    if raw:
        try:
            val = int(raw)
            if val > 0:
                return val
        except ValueError:
            pass
    return DEFAULT_RETENTION_DAYS


def resolve_archive_dir(explicit: str | None) -> Path:
    if explicit:
        return Path(explicit)
    base = os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()
    return Path(base) / ".brainer" / "sessions" / "raw"


def get_owner_email(repo_dir: Path | None = None) -> str | None:
    """Repo owner's email, so `scrub` can keep it and redact everyone else's.

    Never hardcoded (this tool ships to sibling repos with different owners).
    `BRAINER_OWNER_EMAIL` wins if set; otherwise `git config user.email` in
    the target file's own directory tree. Returns None if undeterminable —
    callers then redact ALL emails found (fail toward more redaction, not
    less; a secret that can't be proven safe is not left in place).
    """
    env = os.environ.get("BRAINER_OWNER_EMAIL")
    if env and env.strip():
        return env.strip()
    try:
        result = subprocess.run(
            ["git", "config", "user.email"],
            cwd=str(repo_dir) if repo_dir else None,
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode == 0:
            email = result.stdout.strip()
            if email:
                return email
    except (OSError, subprocess.SubprocessError):
        pass
    return None


def _replace_high_entropy(m: "re.Match[str]") -> str:
    return m.group(1) + REDACTED_MARKER + m.group(3)


def _redact_high_entropy(text: str) -> tuple[str, int]:
    return _HIGH_ENTROPY_RE.subn(_replace_high_entropy, text)


def _redact_emails(text: str, owner_email: str | None) -> tuple[str, int]:
    count = 0

    def repl(m: "re.Match[str]") -> str:
        nonlocal count
        addr = m.group(0)
        if owner_email and addr.lower() == owner_email.lower():
            return addr
        count += 1
        return REDACTED_EMAIL_MARKER

    out = _EMAIL_RE.sub(repl, text)
    return out, count


def scrub_line(line: str, owner_email: str | None, ar_module) -> tuple[str, dict[str, int]]:
    """Redact one raw line. Never parses the line as JSON — pure text/regex."""
    before = line.count(ar_module.REDACTED)
    out = ar_module.redact_secrets(line)
    secret_families = out.count(ar_module.REDACTED) - before
    out, high_entropy = _redact_high_entropy(out)
    out, email = _redact_emails(out, owner_email)
    return out, {"secret_families": secret_families, "high_entropy": high_entropy, "email": email}


def cmd_status(args: argparse.Namespace) -> int:
    archive_dir = resolve_archive_dir(args.dir)
    window_days = get_retention_days()
    override = " (from BRAINER_RAW_RETENTION_DAYS)" if os.environ.get("BRAINER_RAW_RETENTION_DAYS") else " (default)"
    print(f"archive dir: {archive_dir}")
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


def _expired_files(archive_dir: Path, window_days: int) -> list[tuple[Path, float, int]]:
    now = time.time()
    out = []
    for f in sorted(archive_dir.glob("*.jsonl")):
        if not f.is_file():
            continue
        st = f.stat()
        age_days = (now - st.st_mtime) / 86400
        if age_days > window_days:
            out.append((f, age_days, st.st_size))
    return out


def cmd_expire(args: argparse.Namespace) -> int:
    archive_dir = resolve_archive_dir(args.dir)
    window_days = get_retention_days()
    if not archive_dir.is_dir():
        print(f"no archive directory at {archive_dir}")
        return 0
    expired = _expired_files(archive_dir, window_days)
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
    for f, age, size in expired:
        try:
            f.unlink()
            removed.append((f, age, size))
        except OSError as e:
            print(f"FAILED to delete {f}: {e}", file=sys.stderr)
    removed_bytes = sum(size for _, _, size in removed)
    print(f"deleted {len(removed)} file(s), {removed_bytes} bytes ({_human_bytes(removed_bytes)}):")
    for f, age, size in removed:
        print(f"  removed {f}  age={age:.1f}d  size={size}")
    return 0


def cmd_scrub(args: argparse.Namespace) -> int:
    src = Path(args.file)
    if not src.is_file():
        print(f"file not found: {src}", file=sys.stderr)
        return 1
    try:
        import audit_redact as ar
    except ImportError as e:
        print(f"cannot load skills/_shared/audit_redact.py: {e}", file=sys.stderr)
        return 1

    owner_email = get_owner_email(src.parent)

    if src.name.endswith(".jsonl"):
        sibling = src.with_name(src.name[: -len(".jsonl")] + ".redacted.jsonl")
    else:
        sibling = src.with_name(src.name + ".redacted.jsonl")

    try:
        text = src.read_text(encoding="utf-8", newline="")
    except UnicodeDecodeError as e:
        print(f"cannot decode {src} as utf-8: {e}", file=sys.stderr)
        return 1

    lines = text.splitlines(keepends=True)
    totals = {"secret_families": 0, "high_entropy": 0, "email": 0}
    out_lines = []
    for line in lines:
        new_line, counts = scrub_line(line, owner_email, ar)
        out_lines.append(new_line)
        for k, v in counts.items():
            totals[k] += v

    sibling.write_text("".join(out_lines), encoding="utf-8", newline="")

    print(f"scrubbed {src} -> {sibling}")
    print(
        "redactions: "
        f"secret-family={totals['secret_families']} "
        f"high-entropy={totals['high_entropy']} "
        f"email={totals['email']}"
    )
    if owner_email is None:
        print("owner email undeterminable (no BRAINER_OWNER_EMAIL, no git user.email) — all emails redacted")

    if args.replace:
        os.replace(str(sibling), str(src))
        print(f"--replace given: {src} now holds the scrubbed content")

    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="retention.py",
        description="Retention / deletion / redaction for .brainer/sessions/raw/. See ../POLICY.md.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_status = sub.add_parser("status", help="count files, ages, total bytes, how many are past the window")
    p_status.add_argument("--dir", help="override archive directory (default: <project>/.brainer/sessions/raw)")

    p_expire = sub.add_parser("expire", help="list or delete archive files older than the retention window")
    p_expire.add_argument("--dir", help="override archive directory")
    grp = p_expire.add_mutually_exclusive_group(required=True)
    grp.add_argument("--dry-run", action="store_true", help="list what would be deleted; deletes nothing")
    grp.add_argument("--delete", action="store_true", help="actually delete; required for any removal")

    p_scrub = sub.add_parser("scrub", help="redact secrets from one archived transcript into a sibling file")
    p_scrub.add_argument("file", help="path to the archived .jsonl transcript")
    p_scrub.add_argument("--replace", action="store_true", help="also overwrite the original with the scrubbed content")

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command == "status":
        return cmd_status(args)
    if args.command == "expire":
        return cmd_expire(args)
    if args.command == "scrub":
        return cmd_scrub(args)
    parser.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
