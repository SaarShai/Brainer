#!/usr/bin/env python3
"""Remove managed host hooks for skills marked ``auto-install: false``."""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


MANAGED_SKILL_RES = (
    re.compile(r"\.(?:claude|codex|gemini)/skills/([^/]+)/"),
    re.compile(r"\$\{CLAUDE_PROJECT_DIR:-\$PWD\}/skills/([^/]+)/"),
)


def managed_skill(command: str) -> str | None:
    for pattern in MANAGED_SKILL_RES:
        match = pattern.search(command)
        if match:
            return match.group(1)
    return None


def optin_skills(skills_root: Path) -> set[str]:
    names = set()
    for skill_md in skills_root.glob("*/SKILL.md"):
        text = skill_md.read_text(encoding="utf-8", errors="replace")
        if re.search(r"^auto-install:\s*false\s*$", text, re.M):
            names.add(skill_md.parent.name)
    return names


def prune(data: dict, optin: set[str]) -> tuple[dict, list[tuple[str, str, str]]]:
    hooks = data.get("hooks", {})
    removed: list[tuple[str, str, str]] = []
    for event in list(hooks):
        groups = []
        for group in hooks[event]:
            kept = []
            for hook in group.get("hooks", []):
                command = hook.get("command", "")
                name = managed_skill(command)
                if name and name in optin:
                    removed.append((name, event, command))
                else:
                    kept.append(hook)
            if kept:
                group["hooks"] = kept
                groups.append(group)
        if groups:
            hooks[event] = groups
        else:
            del hooks[event]
    data["hooks"] = hooks
    return data, removed


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--settings", type=Path, required=True)
    parser.add_argument("--skills-root", type=Path, required=True)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    if not args.settings.is_file():
        return 0
    try:
        data = json.loads(args.settings.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return 0
    data, removed = prune(data, optin_skills(args.skills_root))
    if removed and not args.dry_run:
        args.settings.write_text(
            json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
    for name, event, command in removed:
        prefix = "DRY: " if args.dry_run else ""
        print(f"    [prune-optin-hook] {prefix}{name}: {event} -> {command}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
