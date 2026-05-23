#!/usr/bin/env python3
"""Assert every auto-compaction has a matching context-keeper checkpoint.

Scans every transcript JSONL under ~/.claude/projects/<project-slug>/ for
`compact_boundary` events. For each event with `compactMetadata.trigger == "auto"`
that fired after the hook-fix timestamp, asserts a checkpoint file exists in
.token-economy/sessions/ whose name encodes the same session-id prefix and a
timestamp within ±tolerance of the event timestamp.

Exit 0: all auto-compactions have checkpoints.
Exit 1: one or more auto-compactions have no matching checkpoint.

Usage:
  python3 eval/runner_keeper_auto_check.py
  python3 eval/runner_keeper_auto_check.py --since 2026-05-23T07:02
  python3 eval/runner_keeper_auto_check.py --tolerance-sec 120 --verbose
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
DEFAULT_HOOK_FIX = "2026-05-23T07:02:00+00:00"


def project_slug(cwd: Path) -> str:
    return "-" + str(cwd).strip("/").replace("/", "-")


def parse_iso(s: str) -> datetime:
    # Accept "Z" suffix and naive forms
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    dt = datetime.fromisoformat(s)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def iter_compact_events(jsonl: Path):
    try:
        with open(jsonl) as f:
            for line in f:
                try:
                    ev = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if ev.get("type") == "system" and ev.get("subtype") == "compact_boundary":
                    yield ev
    except OSError:
        return


def find_matching_checkpoint(
    sessions_dir: Path, session_id: str, event_dt: datetime, tolerance_sec: int
) -> Path | None:
    """A checkpoint filename looks like '2026-05-23-0739-ac5625bd.md'.
    Match by session-id 8-char prefix AND timestamp within tolerance.

    Newer checkpoints use UTC; older ones used local time. Try both.
    The checkpoint always precedes the compact_boundary event (hook runs
    first, summarizer runs second, boundary written last), so we only
    accept candidates where cp_dt <= event_dt + small slack.
    """
    sid8 = session_id[:8]
    candidates = list(sessions_dir.glob(f"*-{sid8}.md"))
    if not candidates:
        return None
    # Local UTC offset, for interpreting legacy local-time filenames
    local_offset_sec = -(datetime.now().astimezone().utcoffset() or 0).total_seconds()
    for cp in candidates:
        stem = cp.stem
        parts = stem.rsplit("-", 1)
        if len(parts) != 2:
            continue
        ts_part = parts[0]
        try:
            naive = datetime.strptime(ts_part, "%Y-%m-%d-%H%M")
        except ValueError:
            continue
        # Try UTC interpretation, then local-time interpretation
        for tz_shift in (0, local_offset_sec):
            cp_dt = naive.replace(tzinfo=timezone.utc)
            cp_dt_shifted = cp_dt.fromtimestamp(cp_dt.timestamp() + tz_shift, tz=timezone.utc)
            delta = (event_dt - cp_dt_shifted).total_seconds()
            # checkpoint must precede event; allow small negative slack for clock skew
            if -30 <= delta <= tolerance_sec:
                return cp
    return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cwd", default=str(REPO), help="project root (default: repo)")
    ap.add_argument("--since", default=DEFAULT_HOOK_FIX, help="ignore compacts before this ISO timestamp")
    ap.add_argument("--tolerance-sec", type=int, default=600, help="checkpoint-vs-event timestamp tolerance (summarizer can take minutes)")
    ap.add_argument("--include-manual", action="store_true", help="also assert manual /compact has a checkpoint")
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()

    since = parse_iso(args.since)
    cwd = Path(args.cwd).resolve()
    tdir = Path.home() / ".claude" / "projects" / project_slug(cwd)
    sessions_dir = cwd / ".token-economy" / "sessions"

    if not tdir.is_dir():
        print(f"no transcripts dir at {tdir}", file=sys.stderr)
        return 2
    if not sessions_dir.is_dir():
        print(f"no sessions dir at {sessions_dir}", file=sys.stderr)
        return 2

    triggers = {"auto"} if not args.include_manual else {"auto", "manual"}
    seen = 0
    missing: list[dict] = []
    matched: list[dict] = []

    for jsonl in sorted(tdir.glob("*.jsonl")):
        for ev in iter_compact_events(jsonl):
            meta = ev.get("compactMetadata") or {}
            trig = meta.get("trigger")
            if trig not in triggers:
                continue
            ts_raw = ev.get("timestamp")
            if not ts_raw:
                continue
            ev_dt = parse_iso(ts_raw)
            if ev_dt < since:
                continue
            seen += 1
            sid = ev.get("sessionId") or jsonl.stem
            cp = find_matching_checkpoint(sessions_dir, sid, ev_dt, args.tolerance_sec)
            rec = {
                "session_id": sid,
                "event_time": ts_raw,
                "trigger": trig,
                "pre_tokens": meta.get("preTokens"),
                "post_tokens": meta.get("postTokens"),
                "transcript": str(jsonl),
            }
            if cp is None:
                missing.append(rec)
            else:
                rec["checkpoint"] = str(cp)
                matched.append(rec)

    if args.verbose:
        for r in matched:
            print(f"OK  {r['trigger']:6s} {r['event_time']} sid={r['session_id'][:8]} → {Path(r['checkpoint']).name}")
        for r in missing:
            print(f"MISS {r['trigger']:6s} {r['event_time']} sid={r['session_id'][:8]} pre={r['pre_tokens']}→post={r['post_tokens']}")

    print(f"\n{len(matched)}/{seen} compactions (triggers={sorted(triggers)}) since {args.since} have matching checkpoints")
    if missing:
        print(f"MISSING checkpoint for {len(missing)} compaction(s):", file=sys.stderr)
        for r in missing:
            print(f"  - {r['event_time']} sid={r['session_id']} trigger={r['trigger']} preTokens={r['pre_tokens']}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
