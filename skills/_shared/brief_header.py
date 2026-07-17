#!/usr/bin/env python3
"""brief_header — render the standard subagent brief gate + active skill rules.

Hooks/probes do not fire inside subagents, so every subagent brief must carry
the gate and any active skill reminders inline. This tool renders that header in
one command from local skill frontmatter only.

Stdlib only. Frontmatter parsing is intentionally small: read `pulse_reminder:`
from a single line inside the leading `---` block of `SKILL.md`, stripping one
optional pair of matching quotes. Missing or reminder-less explicit skills warn
on stderr and are skipped. Rules are included only when named with ``--skills``;
``--list`` remains available for discovery without injecting them into a brief.
"""
from __future__ import annotations

import argparse
import os
import re
import sys
from dataclasses import dataclass


PHASE0_BLOCK = """PHASE 0 — before any edit: reply with your plan and EVERY disagreement with this
brief, citing real files as evidence — or state what you checked before concluding
it is sound. Verify named APIs/paths/versions against the live repo before
planning. Silent compliance is a lane defect; silent scope additions are a lane
defect."""


GATE_BLOCK = """GATE (re-run, do not self-certify): your final output is judged by a SEPARATE
verifier on a machine check — not your done-claim. Return raw findings/data, not
"done". State attempts tried + abandoned and every assumption. If you produce a
file/artifact, say exactly what you changed; do NOT touch anything outside the
named scope. END with "READY FOR JUDGING", never "complete"."""


LANE_REPORT_BLOCK = """LANE REPORT (hard shape — the orchestrator reads only this): summary <=200 words;
changed_paths (every file, exhaustive); evidence (exact commands + output lines
for each done-means criterion); attempts; assumptions; leftovers/concerns. End
with exactly one status line: STATUS: COMPLETE | COMPLETE_WITH_CONCERNS (list) |
BLOCKED (exact blocker + what you tried) — then the line READY FOR JUDGING. Raw
results only — no verdicts about your own work, no 'done'."""


@dataclass(frozen=True)
class SkillReminder:
    name: str
    reminder: str


def _strip_optional_quotes(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
        return value[1:-1].strip()
    return value


def pulse_reminder(path: str) -> str:
    """Return the single-line pulse_reminder from SKILL.md frontmatter, else ""."""
    try:
        with open(path, encoding="utf-8", errors="ignore") as fh:
            lines = fh.readlines()
    except OSError:
        return ""

    if not lines or lines[0].strip() != "---":
        return ""

    for line in lines[1:]:
        stripped = line.strip()
        if stripped == "---":
            return ""
        if stripped.startswith("pulse_reminder:"):
            return _strip_optional_quotes(stripped.split(":", 1)[1])
    return ""


def resolve_skills_root(root: str | None) -> str:
    """Resolve the skills root, falling back to .claude/skills only for default."""
    if root is None:
        root = "skills"
        if not os.path.isdir(root):
            root = os.path.join(".claude", "skills")
    if not os.path.isdir(root):
        raise OSError(f"skills root is not usable: {root}")
    return root


def discover(root: str) -> list[SkillReminder]:
    reminders: list[SkillReminder] = []
    try:
        names = sorted(os.listdir(root))
    except OSError:
        return reminders
    for name in names:
        skill_dir = os.path.join(root, name)
        if not os.path.isdir(skill_dir):
            continue
        reminder = pulse_reminder(os.path.join(skill_dir, "SKILL.md"))
        if reminder:
            reminders.append(SkillReminder(name, reminder))
    return reminders


def select(root: str, names: str | None) -> tuple[list[SkillReminder], int]:
    if not names:
        return [], 0

    selected: list[SkillReminder] = []
    seen: set[str] = set()
    for raw in names.split(","):
        name = raw.strip()
        if not name or name in seen:
            continue
        seen.add(name)
        reminder = pulse_reminder(os.path.join(root, name, "SKILL.md"))
        if reminder:
            selected.append(SkillReminder(name, reminder))
        else:
            print(f"WARNING: skill has no pulse_reminder or was not found: {name}", file=sys.stderr)
    return selected, 0


def render_header(args: argparse.Namespace, root: str) -> str:
    reminders, hidden_count = select(root, args.skills)
    lines = [f"GOAL: {args.task}"]
    if args.scope:
        lines.append(f"IN-SCOPE: {args.scope}")
    if args.out_of_scope:
        lines.append(f"OUT-OF-SCOPE: {args.out_of_scope}")
    if not args.no_phase0:
        lines.extend(["", PHASE0_BLOCK])
    lines.extend(["", GATE_BLOCK, "", "ACTIVE RULES:"])
    lines.extend(f"- {r.name}: {r.reminder}" for r in reminders)
    if not reminders:
        lines.append("- none (add only task-required rules with --skills)")
    if hidden_count:
        lines.append(f"- +{hidden_count} more (use --skills)")
    if not args.no_report:
        lines.extend(["", LANE_REPORT_BLOCK])
    return "\n".join(lines)


# --- brief lint: user-supplied literals must be VERBATIM (ORCHESTRATION §6) --
# Observed live 2026-07-07 (screenery "Baton"): a judge brief carried
# `'…/FINAL production/birthday …'` for a path the user had given in FULL —
# the lane burned calls re-discovering the folder. An elision marker adjacent
# to a path-like fragment means the composer summarized a literal instead of
# pasting it; a context-empty subagent cannot un-elide it.
_ELISION_RE = re.compile(
    r"(?:…|\.\.\.)\s*/"          # '…/' or '.../' — elided path prefix
    r"|/[\w ()+.-]+(?:…|/\.\.\.)"  # '/dir…' or '/dir/...' — elided tail
    r"|(?:<|\[)(?:path|dir|folder|file)(?:>|\])",  # '<path>' / '[folder]' stubs
    re.IGNORECASE)


def lint_brief(text: str) -> list[str]:
    findings = []
    for m in _ELISION_RE.finditer(text):
        start = max(0, m.start() - 40)
        findings.append(
            f"elided literal at char {m.start()}: ...{text[start:m.end()+20]!r}... "
            f"— paste the user-supplied value VERBATIM (ORCHESTRATION §6)")
    return findings


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--task", help="one-line goal for the subagent")
    p.add_argument("--scope", help="in-scope files/dirs")
    p.add_argument("--out-of-scope", help="one out-of-scope line")
    p.add_argument("--skills", help="comma-separated skill names to include")
    p.add_argument("--skills-root", help="skills root (default: skills, fallback: .claude/skills)")
    p.add_argument("--list", action="store_true", help="list discoverable skill reminders and exit")
    p.add_argument("--no-phase0", action="store_true", help="omit the PHASE 0 disagreement-gate block")
    p.add_argument("--no-report", action="store_true", help="omit the LANE REPORT block")
    p.add_argument("--lint-brief", metavar="FILE", nargs="?", const="-",
                   help="lint a composed brief (file or '-' for stdin) for elided "
                        "user literals; exit 1 on findings")
    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        root = resolve_skills_root(args.skills_root)
    except OSError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 2

    if args.list:
        for r in discover(root):
            print(f"{r.name}: {r.reminder}")
        return 0

    if args.lint_brief:
        text = (sys.stdin.read() if args.lint_brief == "-"
                else open(args.lint_brief, encoding="utf-8").read())
        findings = lint_brief(text)
        for f in findings:
            print(f"LINT: {f}")
        print("brief lint: " + ("FAIL" if findings else "clean"))
        return 1 if findings else 0

    if not args.task:
        parser.error("--task is required unless --list is used")

    print(render_header(args, root))
    return 0


if __name__ == "__main__":
    sys.exit(main())
