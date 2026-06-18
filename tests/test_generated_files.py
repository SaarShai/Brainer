import subprocess
import sys
from pathlib import Path

import scripts.check_generated_files as generated


ROOT = Path(__file__).resolve().parents[1]


def run_script(path: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, path],
        cwd=ROOT,
        text=True,
        capture_output=True,
    )


def test_generated_file_checker_passes():
    result = run_script("scripts/check_generated_files.py")
    assert result.returncode == 0, result.stdout + result.stderr


def test_generated_files_doc_mentions_key_paths():
    text = (ROOT / "docs" / "GENERATED_FILES.md").read_text(encoding="utf-8")
    file_map = generated.parse_file_map(text)
    for path in [
        "AGENTS.md",
        "CLAUDE.md",
        "GEMINI.md",
        "skills/SKILLS_INDEX.md",
        "skills/HOOKS_MAP.md",
        ".codex/hooks.json",
        ".claude-plugin/marketplace.json",
        ".brainer/wiki.sqlite3",
        ".cache-lint-fingerprint.json",
    ]:
        assert path in file_map


def test_generated_sentinel_carriers_are_documented():
    doc = (ROOT / "docs" / "GENERATED_FILES.md").read_text(encoding="utf-8")
    file_map = generated.parse_file_map(doc)
    for path in ["AGENTS.md", "CLAUDE.md", "GEMINI.md", "skills/HOOKS_MAP.md"]:
        text = (ROOT / path).read_text(encoding="utf-8")
        assert "generated" in text.lower() or "brainer:skills-catalog:start" in text
        assert path in file_map


def test_generated_file_map_requires_exact_path_column():
    table = """| Path | Role | Source of truth | Generator or checker | Manual edits? | Drift action |
|---|---|---|---|---|---|
| `AGENTS.md` | carrier | skills | check | No | fix |

Mentioning CLAUDE.md in prose is not enough.
"""
    assert generated.parse_file_map(table) == {"AGENTS.md": ["`AGENTS.md`", "carrier", "skills", "check", "No", "fix"]}
