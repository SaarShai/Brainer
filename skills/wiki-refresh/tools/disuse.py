#!/usr/bin/env python3
"""Wiki disuse signal — consumes the retrieval-usage ledger (wiki/.brainer/
usage.json, written by wiki-memory's `wiki.py fetch`) as a prune/review
candidate signal for wiki-refresh.

Discovery this answers: most of the analytical wiki is written but never
read back out — a page with 0 fetches is cost without payoff. This module
does not delete or auto-act; it only REPORTS candidates (report-not-act,
same posture as every other wiki-refresh quality-scan verb — see SKILL.md's
"Quality-scan verbs" table). Keep/Update/Consolidate/Replace/Delete stays a
human/agent decision.

A page is a `candidate` only when BOTH hold:
  - reads <= READ_THRESHOLD (default 0 — "never fetched back out")
  - age_days >= GRACE_DAYS (default 30 — a brand-new page with 0 reads
    hasn't had a chance to be read yet; that's not disuse)

usage.json is read defensively: absent, empty, or malformed -> treated as
"no usage data" (every page reports reads=0, candidate computed on age
alone), never a crash.

CLI:
  report [--root R] [--grace-days N] [--read-threshold N]
      Print the JSON list of {page, reads, age_days, candidate} for every
      wiki/concepts|queries|patterns page, plus a summary line.
"""
from __future__ import annotations

import argparse
import datetime as _dt
import json
import re
import sys
from pathlib import Path

USAGE_REL = ".brainer/usage.json"  # relative to --root (the wiki/ dir itself,
                                    # same convention as wiki.py --root wiki)
CONTENT_DIRS = ("concepts", "queries", "patterns")
GRACE_DAYS_DEFAULT = 30
READ_THRESHOLD_DEFAULT = 0


def _frontmatter(text: str) -> dict:
    """Minimal frontmatter reader — enough to pull created:/updated: dates.
    Deliberately not importing wiki-memory's parser: this tool stays a
    self-contained wiki-refresh tool, same posture as staleness.py
    (no cross-skill coupling)."""
    m = re.match(r"^---\n(.*?)\n---\n", text, re.DOTALL)
    if not m:
        return {}
    fm: dict[str, str] = {}
    for line in m.group(1).splitlines():
        if ":" in line:
            k, _, v = line.partition(":")
            fm[k.strip()] = v.strip().strip('"').strip("'")
    return fm


def _parse_date(value: str | None) -> _dt.date | None:
    """Parse a frontmatter date string (date-only or ISO datetime). Tolerates
    missing/malformed values by returning None (age becomes unknown, not a
    crash)."""
    if not value:
        return None
    s = value.strip()
    if not s:
        return None
    try:
        return _dt.date.fromisoformat(s[:10])
    except ValueError:
        return None


def load_usage(root: Path) -> dict[str, int]:
    """Read wiki/.brainer/usage.json. Never raises: absent/empty/malformed
    all resolve to an empty dict (== "no usage data yet")."""
    usage_path = root / USAGE_REL
    if not usage_path.exists():
        return {}
    try:
        data = json.loads(usage_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    if not isinstance(data, dict):
        return {}
    out: dict[str, int] = {}
    for k, v in data.items():
        if isinstance(k, str) and isinstance(v, (int, float)):
            out[k] = int(v)
    return out


def _content_pages(root: Path) -> list[Path]:
    pages = []
    for d in CONTENT_DIRS:
        pages.extend(sorted((root / d).glob("*.md")))
    return pages


def report(
    root: Path,
    grace_days: int = GRACE_DAYS_DEFAULT,
    read_threshold: int = READ_THRESHOLD_DEFAULT,
    today: _dt.date | None = None,
) -> list[dict]:
    """Build the disuse signal: one row per wiki/concepts|queries|patterns
    page. `candidate` is True only when reads <= read_threshold AND
    age_days is known AND age_days >= grace_days (unknown age -> never
    flagged; a page we can't date isn't a safe prune candidate)."""
    usage = load_usage(root)
    today = today or _dt.date.today()
    rows = []
    for page_path in _content_pages(root):
        page_id = f"{page_path.parent.name}/{page_path.stem}"
        reads = usage.get(page_id, 0)
        try:
            text = page_path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            text = ""
        fm = _frontmatter(text)
        created = _parse_date(fm.get("created")) or _parse_date(fm.get("updated"))
        age_days = (today - created).days if created else None
        candidate = bool(
            reads <= read_threshold and age_days is not None and age_days >= grace_days
        )
        rows.append({
            "page": page_id,
            "reads": reads,
            "age_days": age_days,
            "candidate": candidate,
        })
    return rows


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="wiki disuse/read-value signal")
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("report", help="print the disuse signal as JSON")
    s.add_argument("--root", default=".")
    s.add_argument("--grace-days", type=int, default=GRACE_DAYS_DEFAULT,
                   help=f"min age before a 0-read page is flagged (default {GRACE_DAYS_DEFAULT})")
    s.add_argument("--read-threshold", type=int, default=READ_THRESHOLD_DEFAULT,
                   help=f"reads at/below this count are 'unread' (default {READ_THRESHOLD_DEFAULT})")
    a = ap.parse_args(argv)
    root = Path(a.root).resolve()

    rows = report(root, grace_days=a.grace_days, read_threshold=a.read_threshold)
    print(json.dumps(rows, indent=2))
    n_candidates = sum(1 for r in rows if r["candidate"])
    print(f"# {len(rows)} pages scanned, {n_candidates} disuse candidate(s) "
          f"(reads<={a.read_threshold}, age>={a.grace_days}d)", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
