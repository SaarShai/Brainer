#!/usr/bin/env python3
"""Cross-repo sync audit: are Brainer's vendored skill copies in sibling repos
in sync with the canonical source here?

WHY THIS EXISTS: every check in this repo was per-FILE (propagation byte-diff of
the files I happened to touch) or per-TOOL (unit tests). Nothing audited the
SKILL SET across the sibling repos. A bug fixed here can sit unfixed in N
vendored copies indefinitely, and a duplicate/renamed skill in a sibling stays
invisible — both were found late, by accident, for exactly this missing-lens
reason. This is that missing lens as a standing, repeatable check.

For every sibling repo (a dir alongside Brainer that has skills/ + install.sh),
and every file under Brainer's skills/ (real files only — no .venv/__pycache__),
classify the sibling's copy:

  identical   byte-for-byte == canonical Brainer
  DIFFERS     present but not identical (stale fix OR local customization —
              run `--diff <repo> <relpath>` or sibling_sync judgment to tell which)
  absent      Brainer has it, sibling does not (partial adoption — informational)

Also reports skills present in a sibling but NOT in Brainer (sibling-only —
candidate divergence / a skill that should be upstreamed or is a local fork).

This is REPORT-ONLY and NOT a gate: siblings are independent repos that may
legitimately customize or partially adopt. The point is visibility — you can no
longer be unaware that 8 repos are behind.

Usage:
  python3 scripts/sibling_sync_audit.py            # summary table
  python3 scripts/sibling_sync_audit.py --files    # list every DIFFERS file
  python3 scripts/sibling_sync_audit.py --json
"""
from __future__ import annotations

import argparse
import filecmp
import json
import sys
from pathlib import Path

BRAINER = Path(__file__).resolve().parent.parent
DOCS = BRAINER.parent
SKIP = {".venv", "venv", "__pycache__", ".git", ".pytest_cache", "node_modules",
        ".mypy_cache", ".ruff_cache", "dist", "build"}


def is_sibling(d: Path) -> bool:
    return (d.is_dir() and d != BRAINER
            and (d / "skills").is_dir() and (d / "install.sh").is_file())


def skill_files(root: Path) -> list[Path]:
    out = []
    for p in (root / "skills").rglob("*"):
        if not p.is_file():
            continue
        if any(part in SKIP for part in p.relative_to(root).parts):
            continue
        out.append(p.relative_to(root))
    return out


def skill_names(root: Path) -> set[str]:
    return {d.name for d in (root / "skills").iterdir()
            if d.is_dir() and d.name != "_shared" and (d / "SKILL.md").is_file()}


def audit() -> dict:
    canon_files = skill_files(BRAINER)
    canon_skills = skill_names(BRAINER)
    sibs = sorted((d for d in DOCS.iterdir() if is_sibling(d)), key=lambda p: p.name)
    report = {"canonical_files": len(canon_files), "canonical_skills": len(canon_skills),
              "siblings": []}
    for sib in sibs:
        differs, absent = [], []
        identical = 0
        for rel in canon_files:
            sp = sib / rel
            if not sp.is_file():
                absent.append(str(rel))
            elif filecmp.cmp(BRAINER / rel, sp, shallow=False):
                identical += 1
            else:
                differs.append(str(rel))
        sib_skills = skill_names(sib)
        report["siblings"].append({
            "repo": sib.name,
            "shared_skills": sorted(canon_skills & sib_skills),
            "identical": identical,
            "differs": sorted(differs),
            "absent_count": len(absent),
            "sibling_only_skills": sorted(sib_skills - canon_skills),
        })
    return report


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--files", action="store_true", help="list every DIFFERS file")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()
    rep = audit()
    if args.json:
        print(json.dumps(rep, indent=2))
        return 0
    print(f"canonical: {rep['canonical_files']} skill files, "
          f"{rep['canonical_skills']} skills (Brainer)\n")
    print(f"{'sibling':<18}{'shared':>7}{'ident':>7}{'differ':>7}{'absent':>7}  sibling-only-skills")
    for s in rep["siblings"]:
        print(f"{s['repo']:<18}{len(s['shared_skills']):>7}{s['identical']:>7}"
              f"{len(s['differs']):>7}{s['absent_count']:>7}  "
              f"{','.join(s['sibling_only_skills']) or '-'}")
        if args.files and s["differs"]:
            for f in s["differs"]:
                print(f"      DIFFERS  {f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
