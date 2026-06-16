#!/usr/bin/env python3
"""audit_lessons.py — the Measure phase of task-retrospective.

A learning loop that records lessons but never checks whether a fix HELD is open.
This closes it: scan the append-only timeline (`wiki/log.md`) for any promoted
lesson pattern that RECURS in a dated entry *after* the date it was promoted. A
post-promotion hit means the documented fix did not hold -> the lesson must be
escalated from prose to a mechanical gate (a compliance-canary drift probe).

Registry: lesson_patterns.json — a JSON array of:
    {
      "id":          "edit-without-read",
      "description": "Edit/Write before Read",
      "regex":       "File has not been read yet|edit-without-read",
      "promoted":    "2026-06-12",      # ISO date the covering fix landed
      "fix":         "compliance-canary repeated_tool_error probe 'edit-without-read'"
    }

Timeline format (wiki/log.md), append-only dated entries:
    ## [2026-06-14b] verb | summary
    body lines ...

Exit codes:
    0  clean — every promoted pattern is holding (no post-promotion recurrence)
    1  recurrence — at least one promoted lesson recurred; escalate it to a gate
    2  usage / input error

Pure stdlib. No project-specific paths are hardcoded; the wiki/log.md location is
derived from the repo root (skills/task-retrospective/tools/ -> repo root) and is
overridable with --log. Report-only: it never edits anything.
"""
from __future__ import annotations

import argparse
import datetime as _dt
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve()
# tools/ -> task-retrospective/ -> skills/ -> <repo root>
REPO_ROOT = HERE.parents[3]
DEFAULT_REGISTRY = HERE.parent.parent / "lesson_patterns.json"
DEFAULT_LOG = REPO_ROOT / "wiki" / "log.md"

# `## [2026-06-14]` or `## [2026-06-14b]` (suffix letter for same-day entries)
ENTRY_RE = re.compile(r"^##\s*\[(\d{4}-\d{2}-\d{2})([a-z]?)\]\s*(.*)$")

# `pattern:<signature>` — the recurrence classifier the skill mandates on every
# banked lesson / log line (Part C step 6). Matching this tag — NOT a free-text
# regex over prose — is what distinguishes an entry that IS a recurrence of a
# signature from an entry that merely MENTIONS it (e.g. a meta note about the
# fix). `[A-Za-z0-9._-]+` matches signature slugs like `edit-without-read`.
PATTERN_TAG_RE = re.compile(r"pattern:\s*([A-Za-z0-9._-]+)")


def entry_pattern_tags(entry: dict) -> set[str]:
    tags: set[str] = set()
    for line in (entry["header"], *entry["lines"]):
        for m in PATTERN_TAG_RE.finditer(line):
            tags.add(m.group(1))
    return tags


def parse_date(s: str) -> _dt.date:
    return _dt.date.fromisoformat(s)


def load_registry(path: Path) -> list[dict]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        sys.stderr.write(f"audit_lessons: registry not found: {path}\n")
        raise SystemExit(2)
    except json.JSONDecodeError as e:
        sys.stderr.write(f"audit_lessons: registry is not valid JSON ({e})\n")
        raise SystemExit(2)
    if not isinstance(data, list):
        sys.stderr.write("audit_lessons: registry must be a JSON array\n")
        raise SystemExit(2)
    patterns = []
    for i, p in enumerate(data):
        if not isinstance(p, dict):
            sys.stderr.write(f"audit_lessons: registry[{i}] is not an object — skipped\n")
            continue
        missing = [k for k in ("id", "regex", "promoted") if k not in p]
        if missing:
            sys.stderr.write(f"audit_lessons: registry[{i}] missing {missing} — skipped\n")
            continue
        try:
            compiled = re.compile(p["regex"])
        except re.error as e:
            sys.stderr.write(f"audit_lessons: registry[{p['id']}] bad regex ({e}) — skipped\n")
            continue
        try:
            promoted = parse_date(p["promoted"])
        except ValueError:
            sys.stderr.write(f"audit_lessons: registry[{p['id']}] bad promoted date '{p['promoted']}' — skipped\n")
            continue
        patterns.append({**p, "_re": compiled, "_promoted": promoted})
    return patterns


def parse_log(path: Path) -> list[dict]:
    """Return entries as {date, label, header, lines:[...]} in file order."""
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        sys.stderr.write(f"audit_lessons: log not found: {path}\n")
        raise SystemExit(2)
    entries: list[dict] = []
    cur: dict | None = None
    for raw in text.splitlines():
        m = ENTRY_RE.match(raw)
        if m:
            # ENTRY_RE validates the SHAPE of the date, not its calendar
            # validity ('2026-13-40' matches the regex). Guard the parse the
            # same way load_registry guards 'promoted' — a typo in the
            # append-only log must NOT crash the scan (a traceback exits 1,
            # which would be indistinguishable from a real recurrence).
            try:
                entry_date = parse_date(m.group(1))
            except ValueError:
                sys.stderr.write(f"audit_lessons: skipping malformed log header date '{raw.strip()}'\n")
                cur = None  # drop body lines until the next valid header
                continue
            cur = {
                "date": entry_date,
                "suffix": m.group(2),
                "header": raw.strip(),
                "lines": [],
            }
            entries.append(cur)
        elif cur is not None:
            cur["lines"].append(raw)
    return entries


def scan(patterns: list[dict], entries: list[dict], since: _dt.date | None) -> dict:
    """For each pattern, collect post-`promoted` (and post-`since`) recurrences.

    An entry dated strictly AFTER the floor counts as a recurrence of pattern P
    (id S, regex R) when:
      1. the entry is TAGGED `pattern:S` — a deliberate classification that this
         entry records a recurrence of S (definitive); OR
      2. the entry carries NO `pattern:` tag at all AND R matches a body/header
         line — the raw-untagged fallback (e.g. a pasted error string).
    An entry tagged with a DIFFERENT signature is treated as meta (it is *about*
    something else) and a regex hit in its prose is NOT a recurrence — this is
    what stops a note that merely MENTIONS S from tripping the scan.
    """
    results = {}
    for p in patterns:
        pid = p["id"]
        floor = p["_promoted"]
        if since and since > floor:
            floor = since
        hits = []
        for e in entries:
            if e["date"] <= floor:  # strictly AFTER the day it was promoted/fixed
                continue
            tags = entry_pattern_tags(e)
            regex_line = next((ln.strip() for ln in (e["header"], *e["lines"]) if p["_re"].search(ln)), None)
            if pid in tags:
                hits.append((e, regex_line or f"pattern:{pid} (tagged recurrence)"))
            elif not tags and regex_line is not None:
                hits.append((e, regex_line))
            # else: entry tagged with a different pattern -> meta-mention, skip
        results[pid] = {"pattern": p, "hits": hits}
    return results


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description="Measure phase: detect promoted lessons that recurred.")
    ap.add_argument("--registry", type=Path, default=DEFAULT_REGISTRY,
                    help=f"lesson_patterns.json (default: {DEFAULT_REGISTRY})")
    ap.add_argument("--log", type=Path, default=DEFAULT_LOG,
                    help=f"append-only timeline to scan (default: {DEFAULT_LOG})")
    ap.add_argument("--since", type=str, default=None,
                    help="only count recurrences on/after this ISO date (raises the floor)")
    args = ap.parse_args(argv)

    since = None
    if args.since:
        try:
            since = parse_date(args.since)
        except ValueError:
            sys.stderr.write(f"audit_lessons: bad --since date '{args.since}'\n")
            return 2

    patterns = load_registry(args.registry)
    if not patterns:
        print("audit_lessons: no usable patterns in registry — nothing to measure.")
        return 0

    entries = parse_log(args.log)
    results = scan(patterns, entries, since)

    recurred = {k: v for k, v in results.items() if v["hits"]}
    holding = [k for k, v in results.items() if not v["hits"]]

    print(f"# task-retrospective MEASURE — {len(patterns)} promoted lesson(s) vs {args.log}")
    if holding:
        print(f"\nHOLDING (no recurrence since promotion): {', '.join(sorted(holding))}")

    if not recurred:
        print("\nclean — every documented fix is holding.")
        return 0

    print(f"\nRECURRENCE — {len(recurred)} lesson(s) came back AFTER their fix; escalate to a mechanical gate:")
    for pid, v in recurred.items():
        p = v["pattern"]
        print(f"\n  [{pid}] {p.get('description','')}  (promoted {p['promoted']}; fix: {p.get('fix','—')})")
        for e, snippet in v["hits"]:
            print(f"    {e['header']}")
            print(f"      ↳ {snippet}")
    print("\nHARD RULE: a repeated failure earns a gate, not prose. Add a drift probe to the owning")
    print("skill's drift_probes.json (user_correction / repeated_tool_error / claim_without_evidence).")
    return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
