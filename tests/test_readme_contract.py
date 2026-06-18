import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def run_script(path: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, path],
        cwd=ROOT,
        text=True,
        capture_output=True,
    )


def test_readme_mentions_canonical_check_and_docs():
    text = (ROOT / "README.md").read_text(encoding="utf-8")
    for phrase in [
        "make check",
        "docs/GENERATED_FILES.md",
        "docs/ADDING_A_SKILL.md",
        "docs/INSTALL_SAFETY.md",
        "docs/MEMORY_MODEL.md",
    ]:
        assert phrase in text


def test_wiki_hygiene_checker_passes():
    result = run_script("scripts/check_wiki_hygiene.py")
    assert result.returncode == 0, result.stdout + result.stderr
