#!/usr/bin/env python3
"""Check Brainer skill inventory and transitional metadata contracts.

The hard gate today is inventory drift: every real skill directory must be in
skills/SKILLS_INDEX.md, every indexed skill must exist, and hook-capable skills
must appear in skills/HOOKS_MAP.md. Existing frontmatter is accepted with the
agentskills.io fields (`name`, `description`); richer Brainer fields are
validated when present and documented in schema/skill.schema.json.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SKILLS_DIR = ROOT / "skills"
INDEX = SKILLS_DIR / "SKILLS_INDEX.md"
HOOKS_MAP = SKILLS_DIR / "HOOKS_MAP.md"
SCHEMA = ROOT / "schema" / "skill.schema.json"

NAME_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")
INDEX_RE = re.compile(r"\|\s*\[([a-z0-9][a-z0-9-]*)\]\(([^)]+/SKILL\.md)\)\s*\|\s*([^|]+?)\s*\|")

TRIGGER_TYPES = {"slash", "model", "hook", "manual"}
RISK_LEVELS = {"low", "medium", "high"}
HOST_SUPPORT = {"claude", "codex", "gemini", "copilot", "generic"}
SIDE_EFFECTS = {
    "none",
    "reads_repo",
    "writes_files",
    "runs_commands",
    "updates_memory",
    "network",
    "installs_hooks",
    "edits_host_config",
    "dispatches_subagents",
}
REQUIRES_TOOLS = {
    "none",
    "read",
    "write",
    "edit",
    "bash",
    "grep",
    "glob",
    "ls",
    "web",
    "memory",
    "filesystem",
    "host_hooks",
    "subagent",
}


def parse_frontmatter(text: str) -> dict[str, Any]:
    if not text.startswith("---\n"):
        return {}
    end = text.find("\n---\n", 4)
    if end == -1:
        return {}
    out: dict[str, Any] = {}
    current_list_key: str | None = None
    for raw in text[4:end].splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("- "):
            if current_list_key is None:
                out.setdefault("__parse_errors__", []).append(f"list item without key: {line}")
                continue
            out[current_list_key].append(line[2:].strip().strip("'\""))
            continue
        current_list_key = None
        if ":" not in line:
            out.setdefault("__parse_errors__", []).append(f"unsupported frontmatter line: {line}")
            continue
        key, value = line.split(":", 1)
        key = key.strip()
        value = value.strip()
        if not value:
            out[key] = []
            current_list_key = key
            continue
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        out[key] = value
    return out


def parse_scalar_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(part).strip().strip("'\"") for part in value if str(part).strip()]
    value = str(value).strip()
    if value.startswith("[") and value.endswith("]"):
        value = value[1:-1]
    if not value:
        return []
    return [part.strip().strip("'\"") for part in value.split(",") if part.strip()]


def skill_dirs() -> list[Path]:
    return sorted(
        d for d in SKILLS_DIR.iterdir()
        if d.is_dir() and not d.name.startswith("_") and (d / "SKILL.md").is_file()
    )


def parse_index() -> tuple[dict[str, str], list[str]]:
    text = INDEX.read_text(encoding="utf-8")
    seen: dict[str, str] = {}
    duplicates: list[str] = []
    for match in INDEX_RE.finditer(text):
        name = match.group(1)
        desc = match.group(3).strip()
        if name in seen:
            duplicates.append(name)
        seen[name] = desc
    return seen, duplicates


def has_hook_entry(skill_dir: Path) -> bool:
    tools = skill_dir / "tools"
    return any((tools / filename).is_file() for filename in ("hook.sh", "hook.py"))


def parse_hooks_map_skills(text: str | None = None) -> set[str]:
    if text is None:
        text = HOOKS_MAP.read_text(encoding="utf-8", errors="replace")
    skills: set[str] = set()
    for line in text.splitlines():
        if not line.startswith("| "):
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if len(cells) < 4 or cells[0] in {"Skill", "---"}:
            continue
        if NAME_RE.fullmatch(cells[0]):
            skills.add(cells[0])
    return skills


def validate_optional_metadata(skill: str, fm: dict[str, Any], errors: list[str]) -> None:
    for parse_error in fm.get("__parse_errors__", []):
        errors.append(f"{skill}: {parse_error}")
    if "trigger_type" in fm and fm["trigger_type"] not in TRIGGER_TYPES:
        errors.append(f"{skill}: trigger_type must be one of {sorted(TRIGGER_TYPES)}, got {fm['trigger_type']!r}")
    if "risk_level" in fm and fm["risk_level"] not in RISK_LEVELS:
        errors.append(f"{skill}: risk_level must be one of {sorted(RISK_LEVELS)}, got {fm['risk_level']!r}")

    # `requires_tools` is overloaded: canonical skills use the closed capability
    # vocabulary (read/bash/…), but a LEARNED skill (carries `source:`) uses it for
    # external CLI executables (gh, jq) validated at runtime by learn.py check-tools
    # (shutil.which), not against this set. Exempt learned skills from the closed-set
    # check so the contract gate doesn't reject a legitimately-learned dependency.
    is_learned = "source" in fm
    for key, allowed in (
        ("host_support", HOST_SUPPORT),
        ("side_effects", SIDE_EFFECTS),
        ("requires_tools", REQUIRES_TOOLS),
    ):
        if key not in fm:
            continue
        if key == "requires_tools" and is_learned:
            continue
        values = parse_scalar_list(fm[key])
        unknown = sorted(set(values) - allowed)
        if unknown:
            errors.append(f"{skill}: {key} has unknown value(s): {unknown}")


def main() -> int:
    errors: list[str] = []

    for required in (SKILLS_DIR, INDEX, HOOKS_MAP, SCHEMA):
        if not required.exists():
            errors.append(f"missing required path: {required.relative_to(ROOT)}")
    if errors:
        return fail(errors)

    dirs = skill_dirs()
    disk_names = [d.name for d in dirs]
    index_skills, duplicate_index = parse_index()
    index_names = set(index_skills)
    disk_set = set(disk_names)

    for name in disk_names:
        if not NAME_RE.fullmatch(name):
            errors.append(f"skills/{name}: directory name is not lowercase kebab-case")
    for name in sorted(disk_set - index_names):
        errors.append(f"skills/{name}/SKILL.md exists but {name!r} is missing from skills/SKILLS_INDEX.md")
    for name in sorted(index_names - disk_set):
        errors.append(f"skills/SKILLS_INDEX.md lists {name!r}, but skills/{name}/SKILL.md does not exist")
    for name in sorted(set(duplicate_index)):
        errors.append(f"skills/SKILLS_INDEX.md lists {name!r} more than once")
    if len(disk_names) != len(set(disk_names)):
        errors.append("duplicate skill directory names detected")

    hook_map_skills = parse_hooks_map_skills()
    hook_capable_skills = {skill_dir.name for skill_dir in dirs if has_hook_entry(skill_dir)}
    for name in sorted(hook_capable_skills - hook_map_skills):
        errors.append(f"{name}: ships hook tooling but is missing from the skills/HOOKS_MAP.md table")
    for name in sorted(hook_map_skills - hook_capable_skills):
        errors.append(f"skills/HOOKS_MAP.md lists {name!r}, but that skill has no hook.sh or hook.py entry")

    for skill_dir in dirs:
        skill = skill_dir.name
        skill_md = skill_dir / "SKILL.md"
        text = skill_md.read_text(encoding="utf-8", errors="replace")
        if not text.strip():
            errors.append(f"skills/{skill}/SKILL.md is empty")
            continue
        fm = parse_frontmatter(text)
        if not fm:
            errors.append(f"skills/{skill}/SKILL.md is missing YAML frontmatter")
            continue
        if fm.get("name") != skill:
            errors.append(f"skills/{skill}/SKILL.md frontmatter name must equal directory name")
        desc = fm.get("description", "").strip()
        if len(desc) < 10:
            errors.append(f"skills/{skill}/SKILL.md description is missing or too short")
        if skill in index_skills and not index_skills[skill]:
            errors.append(f"skills/SKILLS_INDEX.md has an empty description for {skill!r}")
        validate_optional_metadata(skill, fm, errors)

    if errors:
        return fail(errors)

    print(f"Skill contract check passed: {len(disk_names)} skills match disk, index, metadata, and hook map.")
    return 0


def fail(errors: list[str]) -> int:
    print("Skill contract check failed:")
    for error in errors:
        print(f"- {error}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
