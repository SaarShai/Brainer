#!/usr/bin/env python3
"""Regression guard for the vendored-tree corpus-dependency crash found live
in every sibling checkout during the 2026-07-20 propagation round (b5eaea2):
siblings vendor skills/ but not eval/, so test_profiles.py's frozen-corpus
armed-arm hard-negative checks (which imported
eval/skills_effectiveness/cases.py directly) crashed with FileNotFoundError
after 33 checks (found live via a PROMPTER traceback). Fixed with an
existence-guard around the import plus an INFO skip line.

Verifies BOTH directions so the guard can never silently regress into
"skip everywhere": a copy of skills/ alone (no eval/ alongside it) must still
exit 0 and print the skip line; the real canonical tree (which DOES ship
eval/) must run the armed-arm hard-negative checks (no skip line, and
strictly more PASS lines than the eval-less vendored run).

Lives in scripts/ (not skills/compliance-canary/tools/) because it is a
canonical-only meta-test: it asserts on the DIFFERENCE between the canonical
repo (which ships eval/) and a vendored sibling checkout (which never does).
Siblings vendor skills/ wholesale but not scripts/ or eval/, so this test
never ships to them and can't fail on their guaranteed-eval-less trees.
"""
from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]  # scripts -> Brainer
TEST_PROFILES = REPO / "skills" / "compliance-canary" / "tools" / "test_profiles.py"
SKIP_LINE = "INFO armed-hard-negative-corpus-skipped (eval corpus not vendored in this checkout)"
IGNORE = shutil.ignore_patterns("__pycache__", "*.pyc", ".venv", "venv", ".pytest_cache")


def run_from(cwd: Path, script: Path) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(script)], cwd=cwd, text=True,
                          capture_output=True, timeout=60)


def main() -> int:
    fails: list[str] = []

    # Control: the real canonical tree ships eval/, so the frozen corpus runs.
    canon = run_from(REPO, TEST_PROFILES)
    if canon.returncode != 0:
        fails.append(f"canonical run must exit 0: {canon.stdout[-500:]} {canon.stderr[-500:]}")
    if SKIP_LINE in canon.stdout:
        fails.append("canonical tree (ships eval/) must NOT print the skip line")
    canon_passes = canon.stdout.count("PASS ")

    # Simulated sibling checkout: skills/ copied alone, no eval/ alongside it.
    tmp = Path(tempfile.mkdtemp(prefix="cc-novendoreval-"))
    sim_passes = None
    try:
        shutil.copytree(REPO / "skills", tmp / "skills", ignore=IGNORE)
        sim_script = tmp / "skills" / "compliance-canary" / "tools" / "test_profiles.py"
        sim = run_from(tmp, sim_script)
        if sim.returncode != 0:
            fails.append(f"vendored-only run must exit 0: {sim.stdout[-500:]} {sim.stderr[-500:]}")
        if SKIP_LINE not in sim.stdout:
            fails.append("vendored tree lacking eval/ must print the skip INFO line")
        sim_passes = sim.stdout.count("PASS ")
        if not (canon_passes > sim_passes):
            fails.append(f"canonical run ({canon_passes} PASS) must run MORE checks than "
                        f"the eval-less vendored run ({sim_passes} PASS)")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    if fails:
        print("FAILED:")
        for f in fails:
            print(" -", f)
        return 1
    print(f"ALL PASS (canonical={canon_passes} checks, vendored-sim={sim_passes} checks, "
          "skip-guard correct in both directions)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
