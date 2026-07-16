#!/usr/bin/env python3
"""learn-skill telemetry — close the `/skill` instrumentation hole.

A learned skill is born `proposed` and may not auto-fire until it has *earned*
trust. Earning needs evidence of real, successful use — which needs a usage log.
This is that log.

Two capture paths, both honest about confidence:
  * `record`  — an explicit, high-confidence hit/abort (the agent or user states it).
  * `scan`    — mine a transcript for `Skill` tool_use invocations and INFER the
                outcome: a user correction in the next user turn ⇒ abort, else hit.
                Inferred records are tagged `source: inferred` so a strict operator
                can count only `manual` ones.

Store: `.brainer/learn-skill/usage.sqlite3` (SQLite WAL), under CLAUDE_PROJECT_DIR
when set (stable across cwd changes), else ./ . Existing `usage.jsonl` records are
imported idempotently; JSONL is then treated as read-only legacy input.

Record shape (structured abort evidence is optional for backward compatibility):
  {"skill","ts","outcome":"hit|abort","source":"manual|inferred","session","note",
   "verifier_cause","causal_status","mechanism","evidence_ref"}

CLI:
  telemetry.py record --skill S --outcome {hit,abort} [--session ID] [--note T]
  telemetry.py scan --transcript PATH [--session ID]      # idempotent (dedup by skill+ts)
  telemetry.py stats [--skill S] [--manual-only] [--json]
  telemetry.py flag  [--min-aborts N] [--manual-only] [--json]   # deprecation candidates
"""
from __future__ import annotations

import argparse
import datetime as _dt
import hashlib
import json
import os
import re
import sqlite3
import sys
import time as _time
from pathlib import Path

# Legacy import path. Keep the name for callers/tests that seed old telemetry.
STORE_REL = ".brainer/learn-skill/usage.jsonl"
DB_REL = ".brainer/learn-skill/usage.sqlite3"
CAUSAL_STATUSES = ("skill-caused", "task-difficulty", "model-capability", "unknown")

# Mirrors compliance-canary's user_correction intent: a NEXT-turn correction after
# a skill fired is the strongest cheap signal that the skill misfired (= abort).
# Tightened after adversarial review: dropped bare "actually"/"instead"/"no " which
# false-fired on "actually great", "instead of X continue", "no problem"; added the
# real misses "didn't work", "still broken", "try again".
_CORRECTION_RE = re.compile(
    r"(?i)("
    r"\bno,\s|\bnope\b|"
    r"that'?s (?:wrong|not right|incorrect|not what)|"
    r"\bnot what i\b|\bi (?:said|meant|asked for)\b|"
    # bare "don't" is a correction (don't do that) UNLESS it heads a benign
    # continuation (don't forget/worry/… / "don't change anything else") — those
    # are encouragement or a scope guard, not a rejection of the just-run skill.
    r"\b(?:do ?n'?t|don'?t)\b(?!\s+(?:forget|worry|hesitate|bother|sweat|change anything))|"
    r"\bundo\b|\brevert\b|\bstop\b|"
    r"\b(?:that|it|this) (?:did ?n'?t|does ?n'?t|is ?n'?t) work|"
    r"\b(?:still|not) (?:broken|working)\b|"
    r"\btry again\b|\bwrong\b|you (?:misunderstood|missed)"
    r")"
)

# A turn that OPENS with approval ("Great, …", "thanks —", "perfect.") is a
# confirmation even if it later contains a soft "don't" (scope guard) — override
# to hit, but only when no STRONG correction signal also appears in the message.
_APPROVAL_LEAD_RE = re.compile(
    r"(?i)^\W*(?:great|thanks|thank you|perfect|nice|awesome|cool|ok(?:ay)?|"
    r"lgtm|looks good|love it|excellent|brilliant)\b"
)
_STRONG_CORRECTION_RE = re.compile(
    r"(?i)(\bwrong\b|\bincorrect\b|\bbroken\b|not what i|that'?s not|\bundo\b|"
    r"\brevert\b|\bredo\b|did ?n'?t work|does ?n'?t work|is ?n'?t work|"
    r"you (?:misunderstood|missed))"
)


def _is_correction(text: str) -> bool:
    """True when the next user turn rejects/corrects the just-run skill (=> abort).

    Guards against false aborts: an approval-led turn ('Great, don't change
    anything else') is a hit unless it carries a strong correction signal too."""
    if not text:
        return False
    if _APPROVAL_LEAD_RE.match(text) and not _STRONG_CORRECTION_RE.search(text):
        return False
    return bool(_CORRECTION_RE.search(text))


def _now() -> str:
    return _dt.datetime.now().isoformat(timespec="seconds")


def _root() -> Path:
    return Path(os.environ.get("CLAUDE_PROJECT_DIR") or ".")


def _store(root: Path | None = None) -> Path:
    """Legacy JSONL path retained for migration and compatibility."""
    return (root or _root()) / STORE_REL


def _database(root: Path | None = None) -> Path:
    return (root or _root()) / DB_REL


def _root_for_legacy_store(store: Path) -> Path:
    """Recover the project root from `<root>/.brainer/learn-skill/usage.jsonl`."""
    try:
        return store.parents[2]
    except IndexError:
        return _root()


def _legacy_records(store: Path) -> list[tuple[str, dict]]:
    """Parse legacy JSONL and assign stable per-payload occurrence fingerprints."""
    if not store.is_file():
        return []
    out: list[tuple[str, dict]] = []
    occurrences: dict[str, int] = {}
    for line in store.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(obj, dict) or not obj.get("skill"):
            continue
        digest = hashlib.sha256(
            json.dumps(obj, sort_keys=True, ensure_ascii=False,
                       separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        occurrence = occurrences.get(digest, 0)
        occurrences[digest] = occurrence + 1
        out.append((f"legacy:{digest}:{occurrence}", obj))
    return out


def _connect(root: Path | None = None) -> sqlite3.Connection:
    db = _database(root)
    db.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db, timeout=30.0)
    conn.execute("PRAGMA busy_timeout=30000")
    # Concurrent first-use processes can collide specifically while switching
    # journal mode; SQLite's busy_timeout is not consistently honored by this
    # PRAGMA on all builds. Retry only the lock case, with the same bounded cap.
    deadline = _time.monotonic() + 30.0
    while True:
        try:
            conn.execute("PRAGMA journal_mode=WAL")
            break
        except sqlite3.OperationalError as e:
            if "locked" not in str(e).lower() or _time.monotonic() >= deadline:
                conn.close()
                raise
            _time.sleep(0.02)
    conn.execute("PRAGMA synchronous=FULL")
    conn.execute(
        """CREATE TABLE IF NOT EXISTS events (
               id INTEGER PRIMARY KEY AUTOINCREMENT,
               legacy_fingerprint TEXT UNIQUE,
               event_key TEXT UNIQUE,
               payload TEXT NOT NULL
           )"""
    )
    columns = {row[1] for row in conn.execute("PRAGMA table_info(events)")}
    if "event_key" not in columns:
        conn.execute("ALTER TABLE events ADD COLUMN event_key TEXT")
        conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS events_event_key ON events(event_key)")
    return conn


def _event_key(record: dict) -> str | None:
    """Stable dedup key for transcript-mined events; manual records stay distinct."""
    if record.get("source") != "inferred":
        return None
    return "inferred:" + json.dumps(
        [record.get("skill"), record.get("ts"), record.get("dup_ord")],
        ensure_ascii=False, separators=(",", ":"),
    )


def _migrate_legacy(conn: sqlite3.Connection, legacy_store: Path) -> None:
    """Import every valid legacy row once, including intentional duplicates."""
    for fingerprint, record in _legacy_records(legacy_store):
        conn.execute(
            "INSERT OR IGNORE INTO events(legacy_fingerprint, event_key, payload) "
            "VALUES (?, ?, ?)",
            (fingerprint, _event_key(record), json.dumps(record, ensure_ascii=False)),
        )


def _insert_event(conn: sqlite3.Connection, rec: dict) -> int | None:
    """Single injection point for transaction rollback tests."""
    cursor = conn.execute(
        "INSERT OR IGNORE INTO events(legacy_fingerprint, event_key, payload) "
        "VALUES (NULL, ?, ?)",
        (_event_key(rec), json.dumps(rec, ensure_ascii=False)),
    )
    return int(cursor.lastrowid) if cursor.rowcount == 1 else None


def _append(store: Path, rec: dict) -> int | None:
    """Transactionally append one event to the SQLite WAL store.

    `BEGIN IMMEDIATE` serializes writers on every supported SQLite host. A failed
    insert rolls back without erasing a concurrent committed event.
    """
    root = _root_for_legacy_store(store)
    with _connect(root) as conn:
        conn.execute("BEGIN IMMEDIATE")
        try:
            _migrate_legacy(conn, store)
            inserted = _insert_event(conn, rec)
        except Exception:
            conn.rollback()
            raise
        conn.commit()
    return inserted


def _delete_event(event_id: int, root: Path | None = None) -> bool:
    """Delete one exact event for a caller rolling back a larger transaction."""
    with _connect(root) as conn:
        conn.execute("BEGIN IMMEDIATE")
        try:
            cursor = conn.execute("DELETE FROM events WHERE id = ?", (event_id,))
        except Exception:
            conn.rollback()
            raise
        conn.commit()
    return cursor.rowcount == 1


def _load(store: Path) -> list[dict]:
    root = _root_for_legacy_store(store)
    with _connect(root) as conn:
        conn.execute("BEGIN IMMEDIATE")
        try:
            _migrate_legacy(conn, store)
        except Exception:
            conn.rollback()
            raise
        conn.commit()
        rows = conn.execute("SELECT payload FROM events ORDER BY id").fetchall()
    out: list[dict] = []
    for (payload,) in rows:
        try:
            obj = json.loads(payload)
        except (TypeError, json.JSONDecodeError):
            continue
        if isinstance(obj, dict) and obj.get("skill"):
            out.append(obj)
    return out


# -------------------------- record ------------------------------------------

def cmd_record(args) -> int:
    store = _store()
    now = _now()
    rec = {
        "skill": args.skill,
        "ts": now,
        "recorded_at": now,
        "outcome": args.outcome,
        "source": "manual",
        "session": args.session or os.environ.get("CLAUDE_SESSION_ID", ""),
        "note": args.note or "",
    }
    for key in ("verifier_cause", "causal_status", "mechanism", "evidence_ref"):
        value = getattr(args, key, None)
        if value:
            rec[key] = value
    _append(store, rec)
    print(json.dumps(rec, ensure_ascii=False))
    return 0


# -------------------------- scan (transcript mining) ------------------------

def _normalize(events: list[dict]) -> list[dict]:
    """Map a Codex {type,payload} transcript into Claude event shape so the scanner
    works on both hosts; Claude transcripts pass through. Degrades to identity if the
    shared module is missing (then only Claude-shaped transcripts are understood)."""
    try:
        shared = Path(__file__).resolve().parent.parent.parent / "_shared"
        if str(shared) not in sys.path:
            sys.path.insert(0, str(shared))
        import transcript_norm
        return transcript_norm.normalize(events)
    except Exception:
        return events


def _iter_events(path: Path):
    try:
        raw = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return
    for line in raw.splitlines():
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict):
            yield obj


def _skill_invocations(events: list[dict]) -> list[dict]:
    """Find Skill tool_use events. Returns [{skill, ts, idx}] in transcript order."""
    out = []
    for i, e in enumerate(events):
        if e.get("type") != "assistant":
            continue
        msg = e.get("message") or {}
        for b in (msg.get("content") or []):
            if not isinstance(b, dict) or b.get("type") != "tool_use":
                continue
            if b.get("name") != "Skill":
                continue
            inp = b.get("input") or {}
            skill = inp.get("skill") or inp.get("command") or ""
            if skill:
                out.append({"skill": str(skill), "ts": e.get("timestamp", ""), "idx": i})
    return out


def _next_user_text(events: list[dict], after_idx: int) -> str:
    for e in events[after_idx + 1:]:
        if e.get("type") != "user":
            continue
        msg = e.get("message") or {}
        content = msg.get("content")
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            parts = [b.get("text", "") for b in content
                     if isinstance(b, dict) and b.get("type") == "text"]
            if parts:
                return "\n".join(parts)
    return ""


def _has_following_user(events: list[dict], after_idx: int) -> bool:
    """Is there ANY user turn after this invocation? Used by --defer-trailing: until the
    next user turn exists we can't tell a hit from an abort (a correction lands in that
    turn), so a per-turn (Codex Stop) scan should DEFER judging it rather than optimistically
    record a hit. A whole-session (Claude SessionEnd) scan finalizes instead."""
    return any(e.get("type") == "user" for e in events[after_idx + 1:])


def cmd_scan(args) -> int:
    tpath = Path(args.transcript)
    if not tpath.is_file():
        print(f"transcript not found: {tpath}", file=sys.stderr)
        return 2
    events = _normalize(list(_iter_events(tpath)))
    invocations = _skill_invocations(events)
    store = _store()
    # Dedup disambiguator: NOT the absolute event index (that shifts when any leading
    # event is inserted — a system/compaction header — and would double-count on
    # re-scan). Instead, the ordinal AMONG invocations sharing the same (skill, ts).
    # That survives prepends (relative order of same-(skill,ts) invocations is
    # unchanged) AND still separates distinct invocations when ts='' (the original
    # undercount bug). Both adversarial-review HIGH holes closed.
    dup_counts: dict = {}
    for inv in invocations:
        k = (inv["skill"], inv["ts"])
        inv["dup_ord"] = dup_counts.get(k, 0)
        dup_counts[k] = inv["dup_ord"] + 1
    existing = {(r.get("skill"), r.get("ts"), r.get("dup_ord")) for r in _load(store)}
    added = deferred = 0
    for inv in invocations:
        key = (inv["skill"], inv["ts"], inv["dup_ord"])
        if key in existing:
            continue  # idempotent re-scan
        if args.defer_trailing and not _has_following_user(events, inv["idx"]):
            deferred += 1
            continue  # no reply yet — can't judge hit/abort; the next scan will catch it
        nxt = _next_user_text(events, inv["idx"])
        outcome = "abort" if _is_correction(nxt) else "hit"
        rec = {
            "skill": inv["skill"], "ts": inv["ts"], "dup_ord": inv["dup_ord"],
            "recorded_at": _now(), "outcome": outcome,
            "source": "inferred",
            "session": args.session or "",
            "note": "inferred from transcript (next-turn correction)" if outcome == "abort" else "inferred clean",
        }
        if outcome == "abort":
            # Transcript inference establishes that a correction followed the skill,
            # not that the skill caused the failure. Keep that distinction explicit.
            rec["causal_status"] = "unknown"
        if _append(store, rec):
            existing.add(key)
            added += 1
    print(json.dumps({"scanned": len(invocations), "added": added,
                      "deferred": deferred, "store": str(_database())}))
    return 0


# -------------------------- stats / flag ------------------------------------

def _records(manual_only: bool, skill: str | None = None) -> list[dict]:
    recs = _load(_store())
    if manual_only:
        recs = [r for r in recs if r.get("source") == "manual"]
    if skill:
        recs = [r for r in recs if r.get("skill") == skill]
    return recs


def _parse_dt(s):
    """Parse an ISO-8601 timestamp to a tz-naive (UTC) datetime, or None. Tolerates a
    trailing 'Z' and tz offsets. Non-ISO junk (e.g. a transcript 'timestamp' of 'T1')
    returns None rather than being string-compared."""
    if not s or not isinstance(s, str):
        return None
    try:
        dt = _dt.datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is not None:
        dt = dt.astimezone(_dt.timezone.utc).replace(tzinfo=None)
    return dt


def _event_time(r: dict):
    """Chronological sort key as a real datetime — NOT a lexical string (which made a
    non-ISO ts like 'T1' sort AFTER a real ISO timestamp, re-masking a recent abort).
    Prefer the event time (ts); fall back to recorded_at; unparseable/missing sorts
    oldest so genuinely-timestamped records order after it."""
    return _parse_dt(r.get("ts")) or _parse_dt(r.get("recorded_at")) or _dt.datetime.min


def _post_checkpoint_records(manual_only: bool = False,
                             skill: str | None = None) -> dict[str, list[dict]]:
    """Chronological records after each skill's latest checkpoint.

    This is the single clean-slate view used by both aggregate stats and refinement
    evidence, so a pre-refinement abort cannot influence a later patch proposal.
    Empty lists are retained for skills whose latest event is a checkpoint.
    """
    by_skill: dict[str, list[dict]] = {}
    for record in _records(manual_only, skill):
        by_skill.setdefault(record["skill"], []).append(record)
    for name, records in by_skill.items():
        records = sorted(records, key=_event_time)
        last_checkpoint = max(
            (i for i, record in enumerate(records)
             if record.get("outcome") == "checkpoint"),
            default=-1,
        )
        by_skill[name] = [
            record for record in records[last_checkpoint + 1:]
            if record.get("outcome") != "checkpoint"
        ]
    return by_skill


def compute_stats(manual_only: bool = False) -> dict:
    """Per-skill: total/hits/aborts + TRAILING consecutive hits/aborts.

    Streaks are computed in CHRONOLOGICAL order (by event time), NOT file/append
    order — a late scan of an OLDER transcript appends old records at end-of-file,
    so file order would mask a more-recent abort and wrongly clear the promotion
    gate / dodge the demotion flag (adversarial-review HIGH bug). Python sort is
    stable, so equal timestamps keep append order."""
    by_skill = _post_checkpoint_records(manual_only)
    out: dict[str, dict] = {}
    for skill, rs in by_skill.items():
        if not rs:
            # only checkpoint(s) / nothing post-checkpoint → clean slate, zeroed.
            out[skill] = {"total": 0, "hits": 0, "aborts": 0,
                          "consecutive_hits": 0, "consecutive_aborts": 0, "last_outcome": None}
            continue
        hits = sum(1 for r in rs if r.get("outcome") == "hit")
        aborts = sum(1 for r in rs if r.get("outcome") == "abort")
        trail_hits = 0
        for r in reversed(rs):
            if r.get("outcome") == "hit":
                trail_hits += 1
            else:
                break
        trail_aborts = 0
        for r in reversed(rs):
            if r.get("outcome") == "abort":
                trail_aborts += 1
            else:
                break
        out[skill] = {
            "total": len(rs), "hits": hits, "aborts": aborts,
            "consecutive_hits": trail_hits, "consecutive_aborts": trail_aborts,
            "last_outcome": rs[-1].get("outcome"),
        }
    return out


def cmd_stats(args) -> int:
    stats = compute_stats(args.manual_only)
    if args.skill:
        stats = {k: v for k, v in stats.items() if k == args.skill}
    if args.json:
        print(json.dumps(stats, indent=2))
        return 0
    if not stats:
        print("(no usage recorded)")
        return 0
    for skill, s in sorted(stats.items()):
        print(f"{skill}: total={s['total']} hits={s['hits']} aborts={s['aborts']} "
              f"streak_hits={s['consecutive_hits']} streak_aborts={s['consecutive_aborts']} "
              f"last={s['last_outcome']}")
    return 0


def cmd_flag(args) -> int:
    stats = compute_stats(args.manual_only)
    flagged = {k: v for k, v in stats.items()
               if v["consecutive_aborts"] >= args.min_aborts}
    if args.json:
        print(json.dumps(flagged, indent=2))
        return 0
    if not flagged:
        print(f"no skills with >= {args.min_aborts} consecutive aborts")
        return 0
    for skill, s in sorted(flagged.items()):
        print(f"FLAG {skill}: {s['consecutive_aborts']} consecutive aborts "
              f"(total {s['total']}, last {s['last_outcome']}) — review for demote/deprecate")
    return 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="telemetry.py", description=__doc__)
    sub = p.add_subparsers(dest="cmd", required=True)

    r = sub.add_parser("record", help="Append an explicit hit/abort.")
    r.add_argument("--skill", required=True)
    r.add_argument("--outcome", required=True, choices=["hit", "abort", "checkpoint"])
    r.add_argument("--session", default=None)
    r.add_argument("--note", default=None)
    r.add_argument("--verifier-cause", default=None,
                   help="What the verifier observed (structured abort evidence).")
    r.add_argument("--causal-status", choices=CAUSAL_STATUSES, default=None,
                   help="Whether the failure is skill-caused, non-addressable, or unknown.")
    r.add_argument("--mechanism", default=None,
                   help="Reusable failure mechanism, when confirmed.")
    r.add_argument("--evidence-ref", default=None,
                   help="Path, trace, or other evidence reference.")
    r.set_defaults(func=cmd_record)

    s = sub.add_parser("scan", help="Mine a transcript for Skill invocations + infer outcome.")
    s.add_argument("--transcript", required=True)
    s.add_argument("--session", default=None)
    s.add_argument("--defer-trailing", action="store_true",
                   help="Skip invocations with no following user turn yet (per-turn/Codex Stop "
                        "scans) so hit/abort isn't judged before the reply exists.")
    s.set_defaults(func=cmd_scan)

    st = sub.add_parser("stats", help="Per-skill hit/abort aggregate.")
    st.add_argument("--skill", default=None)
    st.add_argument("--manual-only", action="store_true")
    st.add_argument("--json", action="store_true")
    st.set_defaults(func=cmd_stats)

    fl = sub.add_parser("flag", help="Skills with >= N consecutive aborts.")
    fl.add_argument("--min-aborts", type=int, default=3)
    fl.add_argument("--manual-only", action="store_true")
    fl.add_argument("--json", action="store_true")
    fl.set_defaults(func=cmd_flag)

    a = p.parse_args(argv)
    return a.func(a)


if __name__ == "__main__":
    sys.exit(main())
