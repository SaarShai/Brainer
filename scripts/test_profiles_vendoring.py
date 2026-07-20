#!/usr/bin/env python3
"""Regression guard for the vendored-tree corpus-dependency crash found live
in every sibling checkout during the 2026-07-20 propagation round (b5eaea2):
siblings vendor skills/ but not eval/, so test_profiles.py's frozen-corpus
armed-arm hard-negative checks (which imported
eval/skills_effectiveness/cases.py directly) crashed with FileNotFoundError
after 33 checks (found live via a PROMPTER traceback). Fixed with an
existence-guard around the import plus an INFO skip line.

Closed further (2026-07-20 pre-mortem #4): the 15 hard-negative cases now
ship as a static fixture (skills/compliance-canary/tools/fixtures/
armed_corpus_cases.json) inside skills/, so a vendored sibling tree runs
them too — no more skip line, no more coverage gap. The eval/ import
survives only as a belt-and-braces fallback for a missing fixture, plus (when
eval/ IS present) a canonical-only fixture/live-corpus drift check.

Verifies all three arms: the real canonical tree (fixture AND eval/ both
present) runs the armed-arm checks plus the extra drift check (one more PASS
than the vendored-sim arm, no skip line); a copy of skills/ alone (fixture
present, no eval/) also runs the armed-arm checks with no skip line, at
exactly one PASS fewer than canonical; a copy of skills/ with the fixture
additionally deleted (neither fixture nor eval/) is the only arm that prints
the skip line.

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
FIXTURE_REL = Path("compliance-canary") / "tools" / "fixtures" / "armed_corpus_cases.json"
SKIP_LINE = ("INFO armed-hard-negative-corpus-skipped "
             "(fixture and eval corpus both absent in this checkout)")
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

    # Simulated sibling checkout: skills/ copied alone (fixture included, since
    # it lives inside skills/), no eval/ alongside it. This is the arm the
    # 2026-07-20 fix targets: the fixture now covers the hard negatives, so
    # this must run them too (no skip line) — one PASS short of canonical,
    # which also runs the canonical-only fixture/live-corpus drift check.
    tmp = Path(tempfile.mkdtemp(prefix="cc-novendoreval-"))
    sim_passes = None
    try:
        shutil.copytree(REPO / "skills", tmp / "skills", ignore=IGNORE)
        sim_script = tmp / "skills" / "compliance-canary" / "tools" / "test_profiles.py"
        sim = run_from(tmp, sim_script)
        if sim.returncode != 0:
            fails.append(f"vendored-only run must exit 0: {sim.stdout[-500:]} {sim.stderr[-500:]}")
        if SKIP_LINE in sim.stdout:
            fails.append("vendored tree shipping the fixture must NOT print the skip line")
        sim_passes = sim.stdout.count("PASS ")
        if canon_passes - sim_passes != 1:
            fails.append(f"canonical run ({canon_passes} PASS) must run exactly ONE more check "
                        f"than the eval-less fixture-backed vendored run ({sim_passes} PASS) "
                        "(the canonical-only fixture/live-corpus drift check)")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    # Third arm: a vendored tree missing BOTH the fixture AND eval/ — the only
    # shape that should still print the skip line. Simulated by deleting the
    # fixture from a fresh copy of the sibling tree (cheap: same copytree).
    tmp2 = Path(tempfile.mkdtemp(prefix="cc-nofixture-noeval-"))
    try:
        shutil.copytree(REPO / "skills", tmp2 / "skills", ignore=IGNORE)
        (tmp2 / "skills" / FIXTURE_REL).unlink()
        bare_script = tmp2 / "skills" / "compliance-canary" / "tools" / "test_profiles.py"
        bare = run_from(tmp2, bare_script)
        if bare.returncode != 0:
            fails.append(f"fixture-less+eval-less run must exit 0: "
                        f"{bare.stdout[-500:]} {bare.stderr[-500:]}")
        if SKIP_LINE not in bare.stdout:
            fails.append("a tree lacking BOTH the fixture and eval/ must print the skip INFO line")
    finally:
        shutil.rmtree(tmp2, ignore_errors=True)

    if fails:
        print("FAILED:")
        for f in fails:
            print(" -", f)
        return 1
    print(f"ALL PASS (canonical={canon_passes} checks, vendored-sim={sim_passes} checks, "
          "skip-guard correct in all three arms)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
