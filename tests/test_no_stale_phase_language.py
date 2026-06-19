"""Guard: shipped skill docs/tools must not carry stale PR-phase language.

Once the live Claude/Codex hooks and the Antigravity sidecar shipped, prose
like "PR 4 adds ...", "PR 5 owns ...", "... come later", or "before PR 4"
became false — it describes already-present, opt-in features as future work.
This test fails CI on those phrases so they cannot creep back in.

Scope:
  - every skills/*/SKILL.md
  - skills/brainer-audit/tools/report.py (the report renderer embeds prose)

Explicitly EXCLUDED: docs/AUDIT_MODES_ROADMAP.md is a historical roadmap and is
allowed to keep phase language; it is never scanned here.
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKILLS = ROOT / "skills"

# Forbidden stale-phase patterns. Case-insensitive.
FORBIDDEN = [
    re.compile(r"PR \d+ adds", re.IGNORECASE),
    re.compile(r"PR \d+ owns", re.IGNORECASE),
    re.compile(r"come later", re.IGNORECASE),
    re.compile(r"before PR \d+", re.IGNORECASE),
]


def scanned_files() -> list[Path]:
    files = sorted(
        d / "SKILL.md"
        for d in SKILLS.iterdir()
        if d.is_dir() and not d.name.startswith("_") and (d / "SKILL.md").is_file()
    )
    report = SKILLS / "brainer-audit" / "tools" / "report.py"
    if report.is_file():
        files.append(report)
    return files


def find_violations(path: Path) -> list[str]:
    hits: list[str] = []
    for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        for pat in FORBIDDEN:
            if pat.search(line):
                rel = path.relative_to(ROOT)
                hits.append(f"{rel}:{lineno}: {line.strip()}")
                break
    return hits


def test_roadmap_doc_is_not_scanned():
    # The historical roadmap must never be part of the scanned set, so it can
    # keep phase language without tripping this guard.
    roadmap = ROOT / "docs" / "AUDIT_MODES_ROADMAP.md"
    assert roadmap not in scanned_files()


def test_no_stale_phase_language():
    violations: list[str] = []
    for path in scanned_files():
        violations.extend(find_violations(path))
    assert not violations, "stale PR-phase language found:\n" + "\n".join(violations)
