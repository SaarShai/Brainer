#!/usr/bin/env python3
"""Check that generated, derived, and synchronized surfaces are documented."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOC = ROOT / "docs" / "GENERATED_FILES.md"
README = ROOT / "README.md"

REQUIRED_DOC_PATHS = [
    "AGENTS.md",
    "CLAUDE.md",
    "GEMINI.md",
    "skills/SKILLS_INDEX.md",
    "skills/HOOKS_MAP.md",
    ".codex/hooks.json",
    ".gemini/settings.json",
    ".claude-plugin/marketplace.json",
    ".github/workflows/framework_ci.yml",
    ".gitignore",
    "schema/skill.schema.json",
    "schema/skill_conflicts.json",
]

OPTIONAL_OR_LOCAL_DOC_PATHS = [
    ".claude/settings.json",
    ".cursor/rules/",
    ".codex/skills/",
    ".gemini/skills/",
    ".brainer/",
    ".brainer/wiki.sqlite3",
    ".brainer/audit_results.json",
    ".brainer/audit_workflow.js",
    ".brainer/verify_results.json",
    ".brainer/verify_workflow.js",
    ".brainer/ledger/",
    ".brainer/sessions/",
    ".cache-lint-fingerprint.json",
    ".deepeval/",
    "scratch/",
    "eval/results/",
]

SENTINEL_CANDIDATES = [
    "AGENTS.md",
    "CLAUDE.md",
    "GEMINI.md",
    "skills/HOOKS_MAP.md",
]

SENTINELS = [
    "brainer:skills-catalog:start",
    "Auto-generated",
    "generated — do not edit",
    "do not hand-edit",
]


def parse_file_map(doc_text: str) -> dict[str, list[str]]:
    rows: dict[str, list[str]] = {}
    for line in doc_text.splitlines():
        stripped = line.strip()
        if not stripped.startswith("|") or stripped.startswith("|---"):
            continue
        cells = [cell.strip() for cell in stripped.strip("|").split("|")]
        if not cells or cells[0] in {"Path", ""}:
            continue
        path = cells[0].strip().strip("`")
        rows[path] = cells
    return rows


def main() -> int:
    errors: list[str] = []
    if not DOC.is_file():
        return fail(["docs/GENERATED_FILES.md is missing"])

    doc_text = DOC.read_text(encoding="utf-8", errors="replace")
    file_map = parse_file_map(doc_text)
    for rel in REQUIRED_DOC_PATHS + OPTIONAL_OR_LOCAL_DOC_PATHS:
        if rel not in file_map:
            errors.append(f"{rel} is not an exact Path entry in docs/GENERATED_FILES.md")

    for rel, cells in sorted(file_map.items()):
        if len(cells) < 6:
            errors.append(f"{rel}: generated-file table row must have 6 columns")
            continue
        labels = ("Role", "Source of truth", "Generator or checker", "Manual edits?", "Drift action")
        for label, value in zip(labels, cells[1:6]):
            if not value:
                errors.append(f"{rel}: missing {label} in docs/GENERATED_FILES.md")

    for rel in REQUIRED_DOC_PATHS:
        if not (ROOT / rel).exists():
            errors.append(f"required synchronized path is missing: {rel}")

    for rel in SENTINEL_CANDIDATES:
        path = ROOT / rel
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        if any(sentinel in text for sentinel in SENTINELS) and rel not in file_map:
            errors.append(f"{rel} contains generated sentinels but is not documented")

    if README.is_file():
        readme = README.read_text(encoding="utf-8", errors="replace")
        for phrase in (
            "make check",
            "docs/GENERATED_FILES.md",
            "docs/ADDING_A_SKILL.md",
            "docs/INSTALL_SAFETY.md",
            "docs/MEMORY_MODEL.md",
        ):
            if phrase not in readme:
                errors.append(f"README.md does not mention {phrase}")
    else:
        errors.append("README.md is missing")

    if "make check" not in doc_text:
        errors.append("docs/GENERATED_FILES.md does not mention make check")

    if errors:
        return fail(errors)

    print(f"Generated file policy check passed: {len(REQUIRED_DOC_PATHS)} required paths documented.")
    return 0


def fail(errors: list[str]) -> int:
    print("Generated file policy check failed:")
    for error in errors:
        print(f"- {error}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
