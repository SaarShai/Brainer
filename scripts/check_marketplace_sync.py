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
