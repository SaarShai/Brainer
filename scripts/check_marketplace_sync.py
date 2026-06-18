#!/usr/bin/env python3
"""Assert .claude-plugin/marketplace.json stays in sync with skills/.

WHY: marketplace.json's skills[] array drifted from the real skill set at least
TWICE (wiki/log.md: v1.4.0 "20 skills", then the v1.7 "15->16" change), because
nothing reconciled it — carrier-sync only covers CLAUDE/AGENTS/GEMINI.md. The
'think' skill was missing from the array while the manifest's own prose said
"16 skills". This converts that recurring manifest-drift class into a CI failure.

Fails if:
  - plugins[0].skills[] != the set of real skill dirs (dirs not starting with
    '_' that contain a SKILL.md — the SAME predicate as check_carrier_sync.py);
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
SKILLS = REPO / "skills"
MANIFEST = REPO / ".claude-plugin" / "marketplace.json"
HOOK_EVENT_RE = re.compile(r'hooks\.setdefault\("([^"]+)"')


def discover_skill_dirs() -> set[str]:
    # Same predicate as check_carrier_sync.discover_skills: a dir not starting
    # with '_' that contains a SKILL.md. Do NOT just strip '*.md'/_shared — that
    # would wrongly include stray files and miss the SKILL.md requirement.
    return {d.name for d in SKILLS.iterdir()
            if d.is_dir() and not d.name.startswith("_") and (d / "SKILL.md").is_file()}


def frontmatter_value(path: Path, key: str) -> str:
    text = path.read_text(encoding="utf-8", errors="replace")
    if not text.startswith("---\n"):
        return ""
    end = text.find("\n---\n", 4)
    if end == -1:
        return ""
    for line in text[4:end].splitlines():
        if line.strip().startswith(f"{key}:"):
            return line.split(":", 1)[1].strip()
    return ""


def auto_install_hook_skills() -> set[tuple[str, str]]:
    expected: set[tuple[str, str]] = set()
    for skill_dir in SKILLS.iterdir():
        skill_md = skill_dir / "SKILL.md"
        installer = skill_dir / "tools" / "install.sh"
        if not skill_md.is_file() or not installer.is_file():
            continue
        if frontmatter_value(skill_md, "auto-install").lower() != "true":
            continue
        events = HOOK_EVENT_RE.findall(installer.read_text(encoding="utf-8", errors="replace"))
        for event in events:
            expected.add((skill_dir.name, event))
    return expected


def main() -> int:
    errors: list[str] = []
    if not MANIFEST.is_file():
        print(f"marketplace-sync FAILED: {MANIFEST} missing")
        return 1
    data = json.loads(MANIFEST.read_text(encoding="utf-8"))
    dirs = discover_skill_dirs()
    n = len(dirs)

    plugin = (data.get("plugins") or [{}])[0]
    listed = set(plugin.get("skills", []))
    missing = dirs - listed
    extra = listed - dirs
    if missing:
        errors.append(f"skills[] is MISSING real skills: {sorted(missing)}")
    if extra:
        errors.append(f"skills[] lists NON-EXISTENT skills: {sorted(extra)}")

    # "N skills" / "All N skills" prose must equal the real count.
    for label, text in (("top-level description", data.get("description", "")),
                        ("plugin description", plugin.get("description", ""))):
        for m in re.finditer(r"\b(?:all\s+)?(\d+)\s+skills\b", text, re.I):
            if int(m.group(1)) != n:
                errors.append(f'{label} says "{m.group(0)}" but there are {n} skills')

    hooks = plugin.get("hooks", [])
    declared_hooks = set()
    for hook in hooks:
        command = hook.get("command", "")
        event = hook.get("event", "")
        m = re.search(r"/skills/([\w-]+)/tools/", command)
        if m and event:
            declared_hooks.add((m.group(1), event))
    for skill, event in sorted(auto_install_hook_skills() - declared_hooks):
        errors.append(f"auto-install hook missing from plugin hooks: {skill} {event}")

    if errors:
        print("marketplace-sync FAILED:")
        for e in errors:
            print(f"  - {e}")
        print("\nFix: add/remove the skill in .claude-plugin/marketplace.json "
              "skills[] and update the 'N skills' prose to match skills/.")
        return 1
    print(f"marketplace-sync OK: {n} skills, array + prose in sync.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
