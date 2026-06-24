#!/usr/bin/env python3
"""learn-skill session hooks — make the self-improvement loop run unattended, but
keep every skill-MUTATING step human/agent-gated (loop-engineering: an unattended
write path needs a gate; here the unattended path is append/read-only only).

  session-end   — read the SessionEnd payload from stdin, `telemetry scan` the
                  transcript (APPEND-only usage log; never mutates a skill). Exit 0.
  session-start — print a SILENT-unless-actionable nudge: which learned skills are
                  promote-READY (telemetry cleared the gate), demote candidates
                  (>= N consecutive aborts), or stale (source drifted). It does NOT
                  promote/demote/mark — it surfaces; the agent runs the gated command.
                  Cache-safe: prints nothing when there is nothing to act on.

Both hooks ALWAYS exit 0 — a failing SessionStart/End hook would disrupt the session.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE))
import telemetry  # noqa: E402
import learn  # noqa: E402

PROMOTE_MIN = int(os.environ.get("LEARN_SKILL_PROMOTE_MIN", "3"))
DEMOTE_MIN = int(os.environ.get("LEARN_SKILL_DEMOTE_MIN", "3"))


def _skills_dir() -> Path:
    override = os.environ.get("LEARN_SKILL_SKILLS_DIR")
    if override:
        return Path(override)
    # The installed skills live under .claude/skills; fall back to ./skills (repo).
    for cand in (Path(".claude/skills"), Path("skills")):
        if cand.is_dir():
            return cand
    return Path("skills")


def cmd_session_end() -> int:
    raw = sys.stdin.read()
    if not raw.strip():
        return 0
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return 0
    if not isinstance(payload, dict):
        return 0
    tpath = payload.get("transcript_path") or ""
    if not tpath or not Path(tpath).is_file():
        return 0
    try:
        telemetry.main(["scan", "--transcript", tpath,
                        "--session", str(payload.get("session_id") or "")])
    except Exception:
        pass  # never fail the session
    return 0


def _learned_skills(skills_dir: Path):
    for sm in sorted(skills_dir.glob("*/SKILL.md")):
        try:
            fm = learn._frontmatter(sm.read_text(encoding="utf-8", errors="replace"))
        except OSError:
            continue
        # Only skills BORN from /learn (they carry a learned_at stamp) — never a
        # hand-authored skill that merely happens to be status: trusted.
        if fm.get("status") in ("proposed", "trusted", "stale") and fm.get("learned_at"):
            yield sm.parent.name, fm, sm


def cmd_session_start() -> int:
    skills_dir = _skills_dir()
    try:
        stats = telemetry.compute_stats()
    except Exception:
        stats = {}
    promote_ready, refine_cand, stale, needs_tools = [], [], [], []
    for name, fm, sm in _learned_skills(skills_dir):
        s = stats.get(name, {})
        status = fm.get("status")
        if status == "proposed":
            if s.get("hits", 0) >= PROMOTE_MIN and s.get("consecutive_hits", 0) >= PROMOTE_MIN \
                    and s.get("consecutive_aborts", 0) == 0:
                promote_ready.append(name)
        if status == "trusted":
            if s.get("consecutive_aborts", 0) >= DEMOTE_MIN:
                refine_cand.append(name)
            # #1 conditional activation: a trusted skill whose CLI deps are absent here
            miss = learn._missing_tools(fm.get("requires_tools", ""))
            if miss:
                needs_tools.append(f"{name} (needs {', '.join(miss)})")
        # staleness: read-only verdict (no --apply)
        source = fm.get("source", "")
        if source:
            verdict, _ = learn._source_freshness(source, fm.get("learned_at", ""),
                                                 Path("."), 90)
            if verdict == "stale":
                stale.append(name)
    if not (promote_ready or refine_cand or stale or needs_tools):
        return 0  # silent — nothing to act on (cache-safe)
    lines = ["<system-reminder>", "learn-skill: learned skills need attention —"]
    if promote_ready:
        lines.append(f"- PROMOTE-ready ({PROMOTE_MIN}+ clean hits): {', '.join(promote_ready)} "
                     f"→ run `learn.py promote --name <n>`")
    if refine_cand:
        lines.append(f"- FAILING ({DEMOTE_MIN}+ aborts): {', '.join(refine_cand)} → "
                     f"`learn.py refine --name <n>` to improve (patch), or `demote` to retire")
    if needs_tools:
        lines.append(f"- MISSING TOOLS (won't work here): {', '.join(needs_tools)} → install, or don't rely on it")
    if stale:
        lines.append(f"- STALE source: {', '.join(stale)} → re-`/learn` then `learn.py staleness --apply`")
    lines.append("(surfaced only — these commands mutate SKILL.md and stay agent-run, not automatic)")
    lines.append("</system-reminder>")
    sys.stdout.write("\n".join(lines) + "\n")
    return 0


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    cmd = argv[0] if argv else ""
    if cmd == "session-end":
        return cmd_session_end()
    if cmd == "session-start":
        return cmd_session_start()
    sys.stderr.write("usage: hooks.py {session-end|session-start}\n")
    return 0  # exit 0 even on misuse — hook safety


if __name__ == "__main__":
    sys.exit(main())
