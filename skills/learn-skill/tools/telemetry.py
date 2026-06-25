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

Store: `.brainer/learn-skill/usage.jsonl` (one JSON record per line), under
CLAUDE_PROJECT_DIR when set (stable across cwd changes), else ./ .

Record shape:
  {"skill","ts","outcome":"hit|abort","source":"manual|inferred","session","note"}

CLI:
  telemetry.py record --skill S --outcome {hit,abort} [--session ID] [--note T]
  telemetry.py scan --transcript PATH [--session ID]      # idempotent (dedup by skill+ts)
  telemetry.py stats [--skill S] [--manual-only] [--json]
  telemetry.py flag  [--min-aborts N] [--manual-only] [--json]   # deprecation candidates
"""
from __future__ import annotations

import argparse
import datetime as _dt
import json
import os
import re
import sys
from pathlib import Path

STORE_REL = ".brainer/learn-skill/usage.jsonl"

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
    return (root or _root()) / STORE_REL


def _load(store: Path) -> list[dict]:
    if not store.is_file():
        return []
    out: list[dict] = []
    for line in store.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict) and obj.get("skill"):
            out.append(obj)
    return out


def _append(store: Path, rec: dict) -> None:
    store.parent.mkdir(parents=True, exist_ok=True)
    with open(store, "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")


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
        _append(store, rec)
        existing.add(key)
        added += 1
    print(json.dumps({"scanned": len(invocations), "added": added,
                      "deferred": deferred, "store": str(store)}))
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


def compute_stats(manual_only: bool = False) -> dict:
    """Per-skill: total/hits/aborts + TRAILING consecutive hits/aborts.

    Streaks are computed in CHRONOLOGICAL order (by event time), NOT file/append
    order — a late scan of an OLDER transcript appends old records at end-of-file,
    so file order would mask a more-recent abort and wrongly clear the promotion
    gate / dodge the demotion flag (adversarial-review HIGH bug). Python sort is
    stable, so equal timestamps keep append order."""
    recs = _records(manual_only)
    by_skill: dict[str, list[dict]] = {}
    for r in recs:
        by_skill.setdefault(r["skill"], []).append(r)
    out: dict[str, dict] = {}
    for skill, rs in by_skill.items():
        rs = sorted(rs, key=_event_time)
        # A `checkpoint` record (written when a skill is refined) is a clean-slate
        # marker: only usage AFTER the latest checkpoint counts, so a refined skill
        # re-earns trust from scratch and isn't haunted by pre-refinement aborts.
        last_cp = max((i for i, r in enumerate(rs)
                       if r.get("outcome") == "checkpoint"), default=-1)
        rs = [r for r in rs[last_cp + 1:] if r.get("outcome") != "checkpoint"]
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
