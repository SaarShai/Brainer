#!/usr/bin/env python3
"""Assert the resident skills-catalog in each host carrier is in sync with skills/.

So a contributor (or a future you) never has to *manually* verify that a
slash-triggered skill like `/think` is actually wired into the docs agents read.
CI fails if:
  - a carrier (CLAUDE.md / AGENTS.md / GEMINI.md) or its catalog block is missing;
  - a skill in skills/ is absent from a carrier's catalog block;
  - a slash-only skill (frontmatter `disable-model-invocation: true`) is not
    listed as `/<name>` in every carrier.

Dependency-free (no PyYAML). Run: python3 scripts/check_carrier_sync.py
If it fails, run ./install.sh to regenerate the carriers, then commit them.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SKILLS = REPO / "skills"
CARRIERS = ["CLAUDE.md", "AGENTS.md", "GEMINI.md"]
START = "<!-- brainer:skills-catalog:start -->"
END = "<!-- brainer:skills-catalog:end -->"


def frontmatter_flag(text: str, key: str) -> bool:
    m = re.match(r"^---\n(.*?)\n---\n", text, re.DOTALL)
    if not m:
        return False
    for line in m.group(1).splitlines():
        if line.strip().startswith(f"{key}:"):
            return line.split(":", 1)[1].strip().lower() == "true"
    return False


def catalog_block(doc: str) -> str | None:
    i, j = doc.find(START), doc.find(END)
    if i == -1 or j == -1 or j < i:
        return None
    return doc[i:j]


def discover_skills() -> list[tuple[str, bool]]:
    skills = []
    for d in sorted(SKILLS.iterdir()):
        if not d.is_dir() or d.name.startswith("_"):
            continue
        sm = d / "SKILL.md"
        if not sm.is_file():
            continue
        slash = frontmatter_flag(sm.read_text(encoding="utf-8"), "disable-model-invocation")
        skills.append((d.name, slash))
    return skills


def main() -> int:
    skills = discover_skills()
    errors: list[str] = []

    for carrier in CARRIERS:
        path = REPO / carrier
        if not path.is_file():
            errors.append(f"{carrier}: file missing")
            continue
        block = catalog_block(path.read_text(encoding="utf-8"))
        if block is None:
            errors.append(f"{carrier}: no skills-catalog block")
            continue
        for name, slash in skills:
            token = f"`/{name}`" if slash else f"`{name}`"
            if token not in block:
                kind = "slash skill" if slash else "skill"
                errors.append(f"{carrier}: {kind} {token} not listed in catalog")

    if errors:
        print("carrier-sync FAILED:")
        for e in errors:
            print(f"  - {e}")
        print("\nFix: run `./install.sh` to regenerate the resident catalogs, "
              "then commit the updated CLAUDE.md / AGENTS.md / GEMINI.md.")
        return 1

    n_slash = sum(1 for _, s in skills if s)
    print(f"carrier-sync OK: {len(skills)} skills x {len(CARRIERS)} carriers in sync "
          f"({n_slash} slash-only).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
