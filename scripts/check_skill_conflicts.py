#!/usr/bin/env python3
"""Validate the explicit skill conflict registry."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONFLICTS = ROOT / "schema" / "skill_conflicts.json"
SKILLS = ROOT / "skills"
ALLOWED_STATUS = {"accepted", "resolved", "unresolved"}
PASSING_STATUS = {"accepted", "resolved"}


def real_skills() -> set[str]:
    return {
        d.name for d in SKILLS.iterdir()
        if d.is_dir() and not d.name.startswith("_") and (d / "SKILL.md").is_file()
    }


def validate_conflicts(data: object, skills: set[str]) -> list[str]:
    errors: list[str] = []
    if not isinstance(data, dict):
        return ["schema/skill_conflicts.json must contain an object"]
    conflicts = data.get("conflicts")
    if not isinstance(conflicts, list):
        return ["schema/skill_conflicts.json must contain a conflicts list"]

    seen: set[tuple[str, ...]] = set()
    for idx, conflict in enumerate(conflicts, start=1):
        if not isinstance(conflict, dict):
            errors.append(f"conflict #{idx}: must be an object")
            continue
        names = conflict.get("skills")
        if not isinstance(names, list) or len(names) < 2 or not all(isinstance(s, str) for s in names):
            errors.append(f"conflict #{idx}: skills must be a list of at least two skill names")
            continue
        if len(set(names)) != len(names) or len(set(names)) < 2:
            errors.append(f"conflict #{idx}: skills must contain at least two unique skill names")
            continue
        key = tuple(sorted(names))
        if key in seen:
            errors.append(f"conflict #{idx}: duplicate conflict entry for {' + '.join(key)}")
        seen.add(key)
        missing = sorted(set(names) - skills)
        if missing:
            errors.append(f"{' + '.join(names)}: unknown skill(s): {missing}")
        status = conflict.get("status")
        if status not in ALLOWED_STATUS:
            errors.append(f"{' + '.join(names)}: status must be one of {sorted(ALLOWED_STATUS)}")
        elif status not in PASSING_STATUS:
            errors.append(f"{' + '.join(names)}: unresolved conflicts fail the gate")
        for field in ("risk", "resolution"):
            if not isinstance(conflict.get(field), str) or not conflict[field].strip():
                errors.append(f"{' + '.join(names)}: missing {field}")
    return errors


def main() -> int:
    if not CONFLICTS.is_file():
        return fail([f"missing {CONFLICTS.relative_to(ROOT)}"])

    try:
        data = json.loads(CONFLICTS.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return fail([f"invalid JSON in schema/skill_conflicts.json: {exc}"])

    conflicts = data.get("conflicts") if isinstance(data, dict) else []
    errors = validate_conflicts(data, real_skills())

    if errors:
        return fail(errors)

    print(f"Skill conflict check passed: {len(conflicts)} documented conflict resolutions.")
    return 0


def fail(errors: list[str]) -> int:
    print("Skill conflict check failed:")
    for error in errors:
        print(f"- {error}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
