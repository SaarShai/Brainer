#!/usr/bin/env python3
"""coherence_drift_meter — count COHERENCE-drift incidents in session transcripts.

WHY: compliance-canary's probes catch PROCESS drift (filler, word-count,
unverified claims, dropped requests) but are blind to COHERENCE drift — the
agent solving a subtly-wrong problem, or violating a constraint the user set
earlier. Its own SKILL.md defers the semantic `llm_judge` probe that would catch
it. Before deciding whether a coherence/constraint re-anchor is worth BUILDING,
measure how often coherence drift actually escapes to the user.

WHAT IT COUNTS (per session), over the user's REAL typed turns only:
  - goal_correction       user says "that's not what I asked / not the goal"
  - constraint_reassert   user re-asserts a "don't" they'd already set
  (both = a drift incident that escaped the agent and reached the user)
  - self_correction       the AGENT caught its own thread-loss (resilience)

HONESTY: this is a regex PROXY over correction language, not ground truth. It is
a decision aid ("is an anchor worth building?"), NOT a quality gate. It reports;
it never fails a build. False positives/negatives are expected — read the
flagged lines, don't trust the bare count. Hook-injected `<system-reminder>` and
slash-`<command-*>` blocks are stripped FIRST so the canary's own "user
corrected you" text can't be miscounted as a real user correction.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

DEFAULT_DIR = Path.home() / ".claude" / "projects" / "-Users-za-Documents-Brainer"
MAX_CORRECTION_CHARS = 600  # a real correction is terse; longer = pasted content

# Strip harness/hook noise so only the human's typed words are matched.
_STRIP = re.compile(
    r"<system-reminder>.*?</system-reminder>"
    r"|<command-[a-z]+>.*?</command-[a-z]+>"
    r"|<local-command-[a-z]+>.*?</local-command-[a-z]+>"
    r"|<task-notification>.*?</task-notification>",
    re.DOTALL | re.IGNORECASE,
)

# A drift incident that reached the user: they correct the GOAL/intent.
GOAL_CORRECTION = [
    r"\bthat'?s not what i (asked|wanted|meant|said)\b",
    r"\bnot what i (asked|wanted|meant)\b",
    r"\bi (didn'?t|did not|never) ask(ed)? (you )?(for|to)\b",
    r"\bthat'?s not the (goal|point|task|ask|question)\b",
    r"\bthat'?s not it\b",
    r"\b(wrong|not the right) (thing|approach|direction|file|problem)\b",
    r"\bwhy (did|are) you\b",
    r"\bstop (doing|that)\b",
    r"\bthat'?s not what we('?re| are) (doing|building)\b",
    r"\bre-?read (the|my) (ask|request|goal|prompt)\b",
]
# A constraint the user had set, now re-asserted because it faded.
CONSTRAINT_REASSERT = [
    r"\bi (said|told you|asked you)\b.{0,30}\b(not|don'?t|never|do not)\b",
    r"\byou (weren'?t|were not|aren'?t) (supposed|allowed|meant) to\b",
    r"\bwe (agreed|decided|said) (not to|against)\b",
    r"\b(undo|revert) (that|it|this)\b",
    r"\bi (already )?(told|asked) you (not to|don'?t)\b",
    r"\byou should(n'?t| not) have\b",
]
# The AGENT catching its own drift (resilience — a GOOD sign, lowers the need).
SELF_CORRECTION = [
    r"\bthe (actual|real) (goal|task|ask) is\b",
    r"\bstep(ping)? back\b.{0,45}\b(goal|task|point|ask)\b",
    r"\bi (drifted|lost the thread|over-?reached|went off)\b",
    r"\bwait[,—-].{0,30}\b(the goal|that'?s not the|i was asked)\b",
    r"\bre-?anchor(ing)? (to|on) the (goal|ask|task|contract)\b",
]


def _compile(pats):
    return [re.compile(p, re.IGNORECASE) for p in pats]


GOAL_RE, CONS_RE, SELF_RE = _compile(GOAL_CORRECTION), _compile(CONSTRAINT_REASSERT), _compile(SELF_CORRECTION)


def _text(content) -> str:
    """Flatten a message.content (str or block list) to plain text."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        out = []
        for b in content:
            if isinstance(b, dict) and b.get("type") == "text":
                out.append(b.get("text", ""))
            elif isinstance(b, str):
                out.append(b)
        return "\n".join(out)
    return ""


def _records(path: Path):
    try:
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            line = line.strip()
            if line:
                try:
                    yield json.loads(line)
                except ValueError:
                    continue
    except OSError:
        return


def scan_session(path: Path) -> dict:
    """Return per-session counts + the matched snippets (for auditing)."""
    goal = cons = self_c = incidents = 0
    hits = []
    for obj in _records(path):
        t = obj.get("type")
        msg = obj.get("message")
        if not isinstance(msg, dict):
            continue
        role = msg.get("role") or t
        raw = _text(msg.get("content"))
        if not raw:
            continue
        # Tool results arrive on user-role turns; skip anything that is purely a
        # tool_result block (no human prose). _text() already drops non-text
        # blocks, so a tool-result-only turn flattens to "".
        clean = _STRIP.sub(" ", raw).strip()
        if not clean:
            continue
        # A real correction is terse. A long turn matching a pattern is almost
        # always pasted/quoted CONTENT (a doc, a spec, an article) that merely
        # contains correction-like phrases — a precision killer. Cap it.
        if role == "user" and len(clean) > MAX_CORRECTION_CHARS:
            continue
        if role == "user":
            is_goal = any(r.search(clean) for r in GOAL_RE)
            is_cons = any(r.search(clean) for r in CONS_RE)
            if is_goal:
                goal += 1
            if is_cons:
                cons += 1
            if is_goal or is_cons:
                # One turn = ONE incident, even if it trips both buckets.
                incidents += 1
                hits.append(("goal" if is_goal else "constraint", clean[:140]))
        elif role == "assistant":
            for r in SELF_RE:
                if r.search(clean):
                    self_c += 1
                    hits.append(("self", clean[:140]))
                    break
    return {
        "session": path.stem[:8],
        "goal_correction": goal,
        "constraint_reassert": cons,
        "self_correction": self_c,
        "incidents": incidents,  # user-facing drift turns = the cost signal
        "hits": hits,
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Measure coherence-drift incidents in transcripts (proxy, not a gate).")
    ap.add_argument("paths", nargs="*", help="session .jsonl files; default = the project's transcript dir")
    ap.add_argument("--dir", default=str(DEFAULT_DIR), help="transcript directory")
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    ap.add_argument("--show-hits", action="store_true", help="print the matched snippets")
    ap.add_argument("--threshold", type=float, default=1.5,
                    help="avg incidents/session at/above which an anchor may pay off (default 1.5)")
    a = ap.parse_args(argv)

    if a.paths:
        files = [Path(p) for p in a.paths]
    else:
        d = Path(a.dir)
        files = sorted(d.glob("*.jsonl")) if d.is_dir() else []
    files = [f for f in files if f.is_file()]

    rows = [scan_session(f) for f in files]
    n = len(rows)
    tot_inc = sum(r["incidents"] for r in rows)
    tot_self = sum(r["self_correction"] for r in rows)
    avg = (tot_inc / n) if n else 0.0
    drifty = [r for r in rows if r["incidents"] > 0]

    summary = {
        "sessions": n,
        "total_incidents": tot_inc,
        "avg_incidents_per_session": round(avg, 2),
        "sessions_with_any_incident": len(drifty),
        "total_self_corrections": tot_self,
        "threshold": a.threshold,
        "verdict": (
            "anchor-may-pay-off" if avg >= a.threshold
            else "stack-holds-dont-add"
        ),
    }

    if a.json:
        print(json.dumps({"summary": summary, "sessions": [{k: v for k, v in r.items() if k != "hits"} for r in rows]}, indent=2))
        return 0

    print(f"coherence_drift_meter — {n} session(s) scanned (heuristic proxy, not ground truth)")
    print(f"  user-facing drift incidents : {tot_inc}  (avg {avg:.2f}/session, {len(drifty)} session(s) affected)")
    print(f"  agent self-corrections      : {tot_self}  (resilience — caught before reaching the user)")
    print(f"  verdict (threshold {a.threshold}/session): {summary['verdict']}")
    if summary["verdict"] == "stack-holds-dont-add":
        print("  -> ledger close-gate + loop anchor_files already cover the load; a new re-anchor is unjustified.")
    else:
        print("  -> drift escapes to the user often enough; the tiny ledger-carries-constraints extension may pay off.")
    if a.show_hits:
        for r in drifty:
            for kind, snip in r["hits"]:
                if kind != "self":
                    print(f"    [{r['session']}] {kind}: {snip}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
