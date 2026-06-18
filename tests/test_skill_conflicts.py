import json
import subprocess
import sys
from pathlib import Path

import scripts.check_skill_conflicts as conflicts


ROOT = Path(__file__).resolve().parents[1]


def run_script(path: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, path],
        cwd=ROOT,
        text=True,
        capture_output=True,
    )


def test_skill_conflict_checker_passes():
    result = run_script("scripts/check_skill_conflicts.py")
    assert result.returncode == 0, result.stdout + result.stderr


def test_conflict_registry_has_no_unresolved_conflicts():
    data = json.loads((ROOT / "schema" / "skill_conflicts.json").read_text(encoding="utf-8"))
    assert data["conflicts"]
    assert all(conflict["status"] != "unresolved" for conflict in data["conflicts"])


def test_conflict_registry_references_existing_skills():
    skills = {
        path.name
        for path in (ROOT / "skills").iterdir()
        if path.is_dir() and not path.name.startswith("_") and (path / "SKILL.md").is_file()
    }
    data = json.loads((ROOT / "schema" / "skill_conflicts.json").read_text(encoding="utf-8"))
    for conflict in data["conflicts"]:
        assert set(conflict["skills"]) <= skills


def test_self_conflict_is_rejected():
    data = {
        "conflicts": [
            {
                "skills": ["wiki-memory", "wiki-memory"],
                "status": "accepted",
                "risk": "self conflict",
                "resolution": "none",
            }
        ]
    }
    errors = conflicts.validate_conflicts(data, {"wiki-memory"})
    assert any("unique" in error for error in errors)
