#!/usr/bin/env python3
"""Classify a consumer project's Brainer state before install.sh changes it.

Run this from a Brainer checkout after cloning it into <project>/.brainer.
It is read-only: exit 0 means the project can safely receive the requested
host's Brainer links; exit 2 means a local customization or damaged setup needs
human direction before an install/update; exit 1 is invalid input.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path


HOSTS = {
    "claude-code": (".claude", "skills", "settings.json"),
    "codex": (".codex", "skills", "hooks.json"),
    "gemini": (".gemini", "skills", "settings.json"),
}
REPO = Path(__file__).resolve().parents[1]


def git_status(path: Path) -> tuple[str, str]:
    try:
        result = subprocess.run(
            ["git", "-C", str(path), "status", "--porcelain"],
            text=True,
            capture_output=True,
            check=False,
            timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return "unknown", str(exc)
    if result.returncode:
        return "unknown", result.stderr.strip() or "git status failed"
    return ("dirty" if result.stdout.strip() else "clean"), ""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", required=True, type=Path)
    parser.add_argument("--host", required=True, choices=sorted(HOSTS))
    parser.add_argument(
        "--brainer-dir",
        type=Path,
        help="Brainer checkout; defaults to <project>/.brainer",
    )
    parser.add_argument("--json", action="store_true", help="emit a JSON report")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    project = args.project.resolve()
    if not project.is_dir():
        print(f"ERROR: project directory not found: {project}", file=sys.stderr)
        return 1
    brainer = (args.brainer_dir or project / ".brainer").resolve()
    host_dir_name, skills_dir_name, config_name = HOSTS[args.host]
    skill_root = project / host_dir_name / skills_dir_name
    source_skills = {p.name for p in (REPO / "skills").iterdir()
                     if p.is_dir() and p.name != "_shared" and (p / "SKILL.md").is_file()}

    blockers: list[str] = []
    notes: list[str] = []
    managed = 0
    repairable = 0
    unrelated = 0

    if not brainer.exists():
        notes.append("Brainer checkout: absent (fresh install after clone)")
    elif not (brainer / ".git").is_dir():
        blockers.append(f"Brainer checkout is not a git repository: {brainer}")
    else:
        state, detail = git_status(brainer)
        if state == "clean":
            notes.append("Brainer checkout: clean")
        elif state == "dirty":
            blockers.append(f"Brainer checkout has local changes: {brainer}")
        else:
            blockers.append(f"Cannot determine Brainer checkout state: {detail}")

    if not skill_root.exists():
        notes.append(f"{host_dir_name}/skills: absent")
    else:
        for entry in sorted(skill_root.iterdir()):
            if entry.name not in source_skills:
                unrelated += 1
                continue
            expected = brainer / "skills" / entry.name
            if not entry.is_symlink():
                blockers.append(f"Customized skill blocks update: {entry}")
                continue
            if not entry.exists():
                repairable += 1
                continue
            if entry.resolve() == expected.resolve():
                managed += 1
            else:
                blockers.append(f"Foreign skill symlink blocks update: {entry} -> {entry.resolve()}")

        missing = sorted(name for name in source_skills if not (skill_root / name).exists()
                         and not (skill_root / name).is_symlink())
        if missing:
            notes.append(f"Missing Brainer skill links: {len(missing)} (installer will add them)")

    config = project / host_dir_name / config_name
    if args.host == "gemini" and config.exists():
        try:
            json.loads(config.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            blockers.append(f"Invalid Gemini settings file: {config} ({exc})")
    elif config.exists():
        notes.append(f"Existing host config preserved: {config}")

    verdict = "STOP" if blockers else ("UPDATE" if managed or repairable else "INSTALL")
    report = {
        "project": str(project),
        "host": args.host,
        "brainer_dir": str(brainer),
        "verdict": verdict,
        "managed_skill_links": managed,
        "repairable_broken_links": repairable,
        "unrelated_host_skills": unrelated,
        "blockers": blockers,
        "notes": notes,
    }
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(f"Brainer project preflight: {verdict}")
        print(f"  project: {project}")
        print(f"  host: {args.host}")
        print(f"  managed skill links: {managed}")
        print(f"  repairable broken links: {repairable}")
        print(f"  unrelated host skills preserved: {unrelated}")
        for note in notes:
            print(f"  note: {note}")
        for blocker in blockers:
            print(f"  BLOCKER: {blocker}")
        if blockers:
            print("  action: stop; inspect or merge the listed local state before installing")
        else:
            print(f"  action: safe to {verdict.lower()} with the current Brainer checkout")
    return 2 if blockers else 0


if __name__ == "__main__":
    raise SystemExit(main())
