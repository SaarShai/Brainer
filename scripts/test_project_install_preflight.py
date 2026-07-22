#!/usr/bin/env python3
"""Hermetic safety tests for project_install_preflight.py."""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


SCRIPT = Path(__file__).resolve().parent / "project_install_preflight.py"
FAILS: list[str] = []


def check(name: str, condition: bool) -> None:
    print(f"  [{'PASS' if condition else 'FAIL'}] {name}")
    if not condition:
        FAILS.append(name)


def run(project: Path, brainer: Path) -> tuple[int, dict]:
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--project", str(project), "--host", "codex",
         "--brainer-dir", str(brainer), "--json"],
        text=True,
        capture_output=True,
    )
    return result.returncode, json.loads(result.stdout)


def git_init(path: Path) -> None:
    subprocess.run(["git", "init", "-q", str(path)], check=True)
    subprocess.run(["git", "-C", str(path), "config", "user.email", "test@example.com"], check=True)
    subprocess.run(["git", "-C", str(path), "config", "user.name", "test"], check=True)
    (path / "README.md").write_text("fixture\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(path), "add", "-A"], check=True)
    subprocess.run(["git", "-C", str(path), "commit", "-qm", "init"], check=True)


def main() -> int:
    if shutil.which("git") is None:
        print("SKIP project-install preflight tests (git not on PATH)")
        return 0
    root = Path(tempfile.mkdtemp(prefix="brainer-preflight-"))
    try:
        project = root / "project"
        project.mkdir()
        brainer = project / ".brainer"
        brainer.mkdir()
        target = brainer / "skills" / "index-first"
        target.mkdir(parents=True)
        git_init(brainer)

        rc, report = run(project, brainer)
        check("clean project is installable", rc == 0 and report["verdict"] == "INSTALL")

        skill_link = project / ".codex" / "skills" / "index-first"
        skill_link.parent.mkdir(parents=True)
        skill_link.symlink_to(target)
        rc, report = run(project, brainer)
        check("managed link is updateable", rc == 0 and report["verdict"] == "UPDATE"
              and report["managed_skill_links"] == 1)

        skill_link.unlink()
        skill_link.mkdir()
        rc, report = run(project, brainer)
        check("customized canonical skill blocks update", rc == 2 and report["verdict"] == "STOP"
              and any("Customized skill" in b for b in report["blockers"]))

        shutil.rmtree(skill_link)
        foreign = root / "foreign-skill"
        foreign.mkdir()
        skill_link.symlink_to(foreign)
        rc, report = run(project, brainer)
        check("foreign canonical skill symlink blocks update", rc == 2 and report["verdict"] == "STOP"
              and any("Foreign skill" in b for b in report["blockers"]))

        skill_link.unlink()
        skill_link.symlink_to(root / "missing-target")
        rc, report = run(project, brainer)
        check("broken canonical symlink is repairable", rc == 0 and report["repairable_broken_links"] == 1)

        (brainer / "local-change.txt").write_text("do not overwrite\n", encoding="utf-8")
        rc, report = run(project, brainer)
        check("dirty Brainer checkout blocks update", rc == 2 and report["verdict"] == "STOP"
              and any("local changes" in b for b in report["blockers"]))
    finally:
        shutil.rmtree(root)
    if FAILS:
        print(f"FAIL: {len(FAILS)} preflight test(s) failed")
        return 1
    print("PASS: project-install preflight tests")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
