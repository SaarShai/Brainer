#!/usr/bin/env python3
"""Detect overlap between skill descriptions — flag candidates for merge."""
from __future__ import annotations

import re
import sys
from collections import Counter
from pathlib import Path


STOP = set(
    "a an and or the of to for in on at by with this that use uses using when whenever then "
    "is are be can do don't not no it its as into out only ".split()
)


def keywords(desc: str) -> set[str]:
    words = re.findall(r"[a-zA-Z][a-zA-Z0-9-]{2,}", desc.lower())
    return {w for w in words if w not in STOP}


def parse_frontmatter(text: str) -> dict[str, str]:
    m = re.match(r"^---\n(.*?)\n---\n", text, re.DOTALL)
    if not m:
        return {}
    fm: dict[str, str] = {}
    for line in m.group(1).splitlines():
        if ":" in line:
            k, _, v = line.partition(":")
            fm[k.strip()] = v.strip()
    return fm


def main(argv: list[str]) -> int:
    root = Path(argv[1]) if len(argv) > 1 else Path("skills")
    if not root.is_dir():
        print(f"{root}: not a directory", file=sys.stderr)
        return 2
    skills: dict[str, set[str]] = {}
    for skill_dir in sorted(root.iterdir()):
        if not skill_dir.is_dir():
            continue
        skill_md = skill_dir / "SKILL.md"
        if not skill_md.exists():
            continue
        fm = parse_frontmatter(skill_md.read_text())
        desc = fm.get("description", "")
        skills[skill_dir.name] = keywords(desc)

    names = list(skills)
    print(f"# Overlap report ({len(names)} skills)\n")
    flagged = 0
    for i, a in enumerate(names):
        for b in names[i + 1 :]:
            shared = skills[a] & skills[b]
            if not shared:
                continue
            ratio = 2 * len(shared) / (len(skills[a]) + len(skills[b]))
            if ratio >= 0.25:
                flagged += 1
                top = sorted(shared, key=lambda w: (len(w), w), reverse=True)[:8]
                print(f"- **{a}** ↔ **{b}** ({ratio:.0%} overlap): {', '.join(top)}")
    if not flagged:
        print("No significant overlap.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
