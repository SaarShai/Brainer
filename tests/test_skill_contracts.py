import re
import subprocess
import sys
from pathlib import Path

import scripts.check_skill_contracts as contracts


ROOT = Path(__file__).resolve().parents[1]


def run_script(path: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, path],
        cwd=ROOT,
        text=True,
        capture_output=True,
    )


def parse_index_skills() -> set[str]:
    text = (ROOT / "skills" / "SKILLS_INDEX.md").read_text(encoding="utf-8")
    return set(re.findall(r"\|\s*\[([a-z0-9][a-z0-9-]*)\]\([^)]+/SKILL\.md\)", text))


def disk_skills() -> set[str]:
    return {
        path.name
        for path in (ROOT / "skills").iterdir()
        if path.is_dir() and not path.name.startswith("_") and (path / "SKILL.md").is_file()
    }


def test_skill_contract_checker_passes():
    result = run_script("scripts/check_skill_contracts.py")
    assert result.returncode == 0, result.stdout + result.stderr


def test_skills_index_covers_disk_and_only_disk():
    assert parse_index_skills() == disk_skills()


def test_every_skill_has_nonempty_skill_md():
    for skill in disk_skills():
        text = (ROOT / "skills" / skill / "SKILL.md").read_text(encoding="utf-8")
        assert text.strip(), skill
        assert f"name: {skill}" in text.split("---", 2)[1], skill


def test_frontmatter_block_lists_are_validated():
    text = """---
name: example-skill
description: Use when testing parser behavior.
host_support:
  - madeuphost
---

# example-skill
"""
    fm = contracts.parse_frontmatter(text)
    errors: list[str] = []
    contracts.validate_optional_metadata("example-skill", fm, errors)
    assert "host_support" in "\n".join(errors)


def test_hooks_map_table_parser_ignores_prose_mentions():
    text = (
        "# Hooks map\n\n"
        "| Skill | Hook event(s) | Entry | Installer |\n"
        "|---|---|---|---|\n"
        "| prompt-triage | UserPromptSubmit | `x` | `y` |\n\n"
        "output-filter appears in prose only.\n"
    )
    assert contracts.parse_hooks_map_skills(text) == {"prompt-triage"}
