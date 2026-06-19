"""Guard: every shipped SKILL.md frontmatter must be STANDARD YAML.

This is the regression test for the class of bug where a `description:` (or any
other field) value containing `: ` (colon-space) was shipped as an UNquoted
plain scalar — which `yaml.safe_load` (the parser GitHub and agentskills.io
use) rejects with "mapping values are not allowed here". Seven SKILL.md files
shipped broken because the old `make lint` used a hand-rolled `partition(":")`
parser that never ran real YAML.

We require PyYAML here (importorskip) so the strict parse is actually exercised
wherever the test suite runs; the production linter keeps a graceful fallback
for hosts without PyYAML.
"""
from __future__ import annotations

from pathlib import Path

import pytest

yaml = pytest.importorskip("yaml")

ROOT = Path(__file__).resolve().parents[1]
SKILLS = ROOT / "skills"


def skill_md_paths() -> list[Path]:
    return sorted(
        d / "SKILL.md"
        for d in SKILLS.iterdir()
        if d.is_dir() and not d.name.startswith("_") and (d / "SKILL.md").is_file()
    )


def frontmatter_block(text: str) -> str | None:
    if not text.startswith("---\n"):
        return None
    end = text.find("\n---", 4)
    if end == -1:
        return None
    return text[4:end]


def test_skill_md_files_exist():
    paths = skill_md_paths()
    assert paths, "no skills/*/SKILL.md files discovered"


@pytest.mark.parametrize("path", skill_md_paths(), ids=lambda p: p.parent.name)
def test_frontmatter_is_valid_yaml(path: Path):
    text = path.read_text(encoding="utf-8")
    block = frontmatter_block(text)
    assert block is not None, f"{path}: missing YAML frontmatter delimited by ---"

    try:
        data = yaml.safe_load(block)
    except yaml.YAMLError as exc:  # pragma: no cover - failure path
        first = str(exc).splitlines()[0] if str(exc) else exc.__class__.__name__
        pytest.fail(f"{path}: frontmatter is not valid YAML (yaml.safe_load: {first})")

    assert isinstance(data, dict), f"{path}: frontmatter did not parse to a mapping"

    for field in ("name", "description"):
        assert field in data, f"{path}: missing required frontmatter field '{field}'"
        value = data[field]
        assert isinstance(value, str) and value.strip(), (
            f"{path}: frontmatter field '{field}' must be a non-empty string"
        )
