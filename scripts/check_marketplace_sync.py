#!/usr/bin/env python3
"""Assert the native Claude plugin package stays in sync with skills/.

WHY: marketplace.json's skills[] array drifted from the real skill set at least
TWICE (wiki/log.md: v1.4.0 "20 skills", then the v1.7 "15->16" change), because
nothing reconciled it — carrier-sync only covers CLAUDE/AGENTS/GEMINI.md. The
'think' skill was missing from the array while the manifest's own prose said
"16 skills". This converts that recurring manifest-drift class into a CI failure.

Fails if:
  - the marketplace does not source the bounded plugin/ package;
  - the package contains anything beyond its manifest, skills, and hooks;
  - a hook command references a missing/non-executable script or the package
    differs from the three default-on handlers;
  - any "<N> skills" / "All <N> skills" integer in the top-level description or
    the plugin description disagrees with the real skill count.

Dependency-free. Run: python3 scripts/check_marketplace_sync.py
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
MANIFEST = REPO / ".claude-plugin" / "marketplace.json"
PLUGIN_ROOT = REPO / "plugin"
SKILLS = PLUGIN_ROOT / "skills"
PLUGIN_MANIFEST = PLUGIN_ROOT / ".claude-plugin" / "plugin.json"
HOOKS_MANIFEST = PLUGIN_ROOT / "hooks" / "hooks.json"
HOOK_ROUTER = PLUGIN_ROOT / "hooks" / "project_hook_precedence.py"

EXPECTED_PLUGIN_ROUTES = {
    "UserPromptSubmit": (
        ".claude/skills/compliance-canary/tools/hook.sh",
        "skills/compliance-canary/tools/hook.sh",
    ),
    "PreCompact": (
        ".claude/skills/context-keeper/tools/hook.sh",
        "skills/context-keeper/tools/hook.sh",
    ),
    "SessionEnd": (
        ".claude/skills/context-keeper/tools/archive.sh",
        "skills/context-keeper/tools/archive.sh",
    ),
}


def discover_skill_dirs() -> set[str]:
    # Same predicate as check_carrier_sync.discover_skills: a dir not starting
    # with '_' that contains a SKILL.md. Do NOT just strip '*.md'/_shared — that
    # would wrongly include stray files and miss the SKILL.md requirement.
    return {d.name for d in SKILLS.iterdir()
            if d.is_dir() and not d.name.startswith("_") and (d / "SKILL.md").is_file()}


def main() -> int:
    errors: list[str] = []
    if not MANIFEST.is_file():
        print(f"marketplace-sync FAILED: {MANIFEST} missing")
        return 1
    data = json.loads(MANIFEST.read_text(encoding="utf-8"))
    dirs = discover_skill_dirs()
    n = len(dirs)

    plugin = (data.get("plugins") or [{}])[0]
    if plugin.get("source") != "./plugin":
        errors.append('plugins[0].source must be "./plugin" (the bounded package root)')
    allowed_package_entries = {".claude-plugin", "skills", "hooks"}
    if PLUGIN_ROOT.is_dir():
        extras = {path.name for path in PLUGIN_ROOT.iterdir()} - allowed_package_entries
        if extras:
            errors.append(f"plugin package has unexpected root entries: {sorted(extras)}")
    if not PLUGIN_MANIFEST.is_file():
        errors.append(".claude-plugin/plugin.json is missing")
    else:
        package = json.loads(PLUGIN_MANIFEST.read_text(encoding="utf-8"))
        if package.get("name") != "brainer":
            errors.append('.claude-plugin/plugin.json name must be "brainer"')
        if "skills" in package or "hooks" in package:
            errors.append("plugin.json must use default root skills/ and hooks/ locations")

    # "N skills" / "All N skills" prose must equal the real count.
    for label, text in (("top-level description", data.get("description", "")),
                        ("plugin description", plugin.get("description", ""))):
        for m in re.finditer(r"\b(?:all\s+)?(\d+)\s+skills\b", text, re.I):
            if int(m.group(1)) != n:
                errors.append(f'{label} says "{m.group(0)}" but there are {n} skills')

    declared_hooks: set[tuple[str, str, str]] = set()
    if not HOOKS_MANIFEST.is_file():
        errors.append("hooks/hooks.json is missing")
    else:
        if not HOOK_ROUTER.is_file():
            errors.append("hooks/project_hook_precedence.py is missing")
        hooks_data = json.loads(HOOKS_MANIFEST.read_text(encoding="utf-8"))
        for event, groups in hooks_data.get("hooks", {}).items():
            for group in groups:
                for handler in group.get("hooks", []):
                    args = handler.get("args", [])
                    expected_route = EXPECTED_PLUGIN_ROUTES.get(event)
                    if expected_route is None:
                        errors.append(f"unexpected default plugin hook event: {event}")
                        continue
                    expected_args = [
                        "${CLAUDE_PLUGIN_ROOT}/hooks/project_hook_precedence.py",
                        event,
                        *expected_route,
                    ]
                    if handler.get("type") != "command" or handler.get("command") != "python3":
                        errors.append(
                            f"{event} plugin hook must invoke project_hook_precedence.py with python3"
                        )
                        continue
                    if args != expected_args:
                        errors.append(
                            f"{event} plugin route differs from expected structural precedence: "
                            f"expected={expected_args!r}, got={args!r}"
                        )
                        continue
                    plugin_relative = expected_route[1]
                    parts = Path(plugin_relative).parts
                    skill = parts[1]
                    script_name = parts[-1]
                    declared_hooks.add((skill, event, script_name))
                    script = PLUGIN_ROOT / plugin_relative
                    if not script.is_file() or not script.stat().st_mode & 0o111:
                        errors.append(f"hook script missing or not executable: {plugin_relative}")

    intended_hooks = {
        ("compliance-canary", "UserPromptSubmit", "hook.sh"),
        ("context-keeper", "PreCompact", "hook.sh"),
        ("context-keeper", "SessionEnd", "archive.sh"),
    }
    if declared_hooks != intended_hooks:
        errors.append(
            f"plugin hooks differ from intended defaults: missing={sorted(intended_hooks - declared_hooks)}, "
            f"extra={sorted(declared_hooks - intended_hooks)}"
        )
    if errors:
        print("marketplace-sync FAILED:")
        for e in errors:
            print(f"  - {e}")
        print("\nFix: keep plugin/ limited to its manifest, skills, and hooks, "
              "and update the 'N skills' prose to match plugin/skills/.")
        return 1
    print(f"marketplace-sync OK: bounded plugin packages {n} skills and 3 default hooks; prose in sync.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
