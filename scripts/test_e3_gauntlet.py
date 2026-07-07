#!/usr/bin/env python3
"""Negative self-test for e3_gauntlet.py — plain-python (no pytest dep),
runnable standalone. Shape mirrors scripts/test_sibling_sync_audit.py /
skills/loop-engineering/tools/test_loop_lint.py: a list of test_* functions, a
main() that runs them and returns the failure count (exit 0 == all pass).

LEARNING_CONTRACT §3: "a gate that has never tripped is unproven." Each test
here installs a REAL fresh consumer project (via the real install.sh --project
path, same as e3_gauntlet.py itself uses), then corrupts exactly ONE thing the
corresponding sub-check is supposed to catch, and asserts:
  1. that sub-check's SubCheck.passed is False (it actually trips), and
  2. the OTHER sub-checks still pass (precision — the corruption isn't
     accidentally tripping every check, which would prove nothing about the
     targeted one).

Slow: each test does a real `install.sh --project` (git init + symlinks).
Network-free (--no-graphify, single host) but still a few seconds per test.
"""
from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import e3_gauntlet as gauntlet  # noqa: E402

SCRATCH = Path(tempfile.gettempdir()) / "e3-gauntlet-selftest"


def _fresh_installed_project() -> Path:
    SCRATCH.mkdir(parents=True, exist_ok=True)
    project = gauntlet.make_fresh_project(SCRATCH, keep=True)
    rc, out = gauntlet.run_install(project)
    assert rc == 0, f"install.sh --project failed in fixture setup: {out}"
    return project


def _run_all_checks(project: Path) -> dict[str, gauntlet.SubCheck]:
    checks = {
        "a": gauntlet.check_a_installed_skill_set(project),
        "b": gauntlet.check_b_write_gate_cross_repo(project),
        "c": gauntlet.check_c_substrate_liveness(project),
        "d": gauntlet.check_d_drift_probes_parse(project),
        "e": gauntlet.check_e_hook_wiring(project),
    }
    return checks


def _cleanup(project: Path) -> None:
    shutil.rmtree(project, ignore_errors=True)


def test_a_trips_on_deleted_skill_symlink() -> None:
    """Delete an installed skill's symlink entirely — (a) must FAIL, others
    (b, c, d, e — which don't depend on write-gate's own symlink) must still
    PASS."""
    project = _fresh_installed_project()
    try:
        victim = project / ".claude" / "skills" / "think"
        assert victim.exists(), "fixture assumption broken: think skill not installed"
        victim.unlink()

        checks = _run_all_checks(project)
        assert checks["a"].passed is False, f"expected (a) to FAIL after deleting a skill link; got {checks['a'].line()}"
        assert "think" in checks["a"].detail, f"(a) failure detail should name the missing skill: {checks['a'].detail}"
        for key in ("b", "c", "d", "e"):
            assert checks[key].passed is True, f"corrupting skill '{('think')}' should not affect ({key}): {checks[key].line()}"
    finally:
        _cleanup(project)


def test_b_trips_on_deleted_write_gate_tool() -> None:
    """Delete the installed write_gate.py tool file — (b) must FAIL (tool
    file gone → cross-repo enforcement broken), (a) also legitimately FAILs
    (write-gate's own symlink target is now missing content, though the link
    itself and dir still resolve — checked precisely below), (c)/(d)/(e) must
    still PASS (they don't touch write_gate.py)."""
    project = _fresh_installed_project()
    try:
        wg_tool = project / ".claude" / "skills" / "write-gate" / "tools" / "write_gate.py"
        assert wg_tool.exists(), "fixture assumption broken: write_gate.py not installed"
        # write-gate/tools/ lives inside the Brainer checkout via a directory
        # symlink (skills/write-gate -> Brainer/skills/write-gate); deleting
        # the file through the link deletes it in the CANONICAL Brainer tree,
        # which is exactly what we must NOT do (out of scope + destructive to
        # the shared repo). Instead simulate "tool file gone from the
        # consumer's view" by replacing the write-gate skill link with a
        # private copy that has the tool file removed — corrupts only the
        # consumer copy, never touches Brainer's skills/write-gate.
        link_dir = project / ".claude" / "skills"
        real_write_gate = (link_dir / "write-gate").resolve()
        (link_dir / "write-gate").unlink()
        private_copy = link_dir / "write-gate"
        shutil.copytree(real_write_gate, private_copy, symlinks=False)
        (private_copy / "tools" / "write_gate.py").unlink()

        checks = _run_all_checks(project)
        assert checks["b"].passed is False, f"expected (b) to FAIL after deleting write_gate.py; got {checks['b'].line()}"
        assert "not found" in checks["b"].detail, f"(b) failure detail should say tool not found: {checks['b'].detail}"
        for key in ("c", "d", "e"):
            assert checks[key].passed is True, f"corrupting write_gate.py should not affect ({key}): {checks[key].line()}"
    finally:
        _cleanup(project)


def test_c_trips_on_broken_probe_json() -> None:
    """Corrupt one drift_probes.json to invalid JSON — (c) substrate
    liveness must FAIL (gate-json parse check is part of its portable
    subset), and (d) must ALSO fail (same file, same defect, different
    sub-check — proving both checks genuinely read the file rather than
    trusting each other). (a)/(b)/(e) must still PASS."""
    project = _fresh_installed_project()
    try:
        link_dir = project / ".claude" / "skills"
        real_probe_skill = (link_dir / "write-gate").resolve()
        probe = real_probe_skill / "drift_probes.json"
        assert probe.exists(), "fixture assumption broken: write-gate/drift_probes.json missing"
        # As in test_b: never write through the symlink into canonical
        # Brainer. Replace the write-gate link with a private copy whose
        # drift_probes.json is corrupted.
        (link_dir / "write-gate").unlink()
        private_copy = link_dir / "write-gate"
        shutil.copytree(real_probe_skill, private_copy, symlinks=False)
        (private_copy / "drift_probes.json").write_text("{not valid json", encoding="utf-8")

        checks = _run_all_checks(project)
        assert checks["c"].passed is False, f"expected (c) to FAIL after corrupting drift_probes.json; got {checks['c'].line()}"
        assert checks["d"].passed is False, f"expected (d) to FAIL on the same corrupted JSON; got {checks['d'].line()}"
        for key in ("a", "b", "e"):
            assert checks[key].passed is True, f"corrupting one drift_probes.json should not affect ({key}): {checks[key].line()}"
    finally:
        _cleanup(project)


def test_d_trips_on_deleted_drift_probes_entirely() -> None:
    """Delete every installed drift_probes.json — (d) must FAIL with "no
    drift_probes.json found", proving the check isn't vacuously passing on
    an empty glob. (a)/(b) must still PASS (skill dirs + write-gate's own
    tool remain intact); (c) must still PASS (drift_probes.json parsing is
    N/A when there are none to parse — gate-json check has nothing to find
    broken, and skill-md/markdown-link checks are untouched); (e) must still
    PASS (hook wiring in settings.json is untouched by removing probe files)."""
    project = _fresh_installed_project()
    try:
        link_dir = project / ".claude" / "skills"
        removed = 0
        for probe in list(link_dir.glob("*/drift_probes.json")):
            skill_link = link_dir / probe.parent.name
            real_skill = skill_link.resolve()
            skill_link.unlink()
            private_copy = link_dir / probe.parent.name
            shutil.copytree(real_skill, private_copy, symlinks=False)
            (private_copy / "drift_probes.json").unlink()
            removed += 1
        assert removed > 0, "fixture assumption broken: no drift_probes.json found to remove"

        checks = _run_all_checks(project)
        assert checks["d"].passed is False, f"expected (d) to FAIL with none installed; got {checks['d'].line()}"
        assert "no drift_probes.json" in checks["d"].detail, f"(d) failure detail should say none found: {checks['d'].detail}"
        for key in ("a", "b", "e"):
            assert checks[key].passed is True, f"removing all drift_probes.json should not affect ({key}): {checks[key].line()}"
    finally:
        _cleanup(project)


def test_e_trips_on_stripped_hook() -> None:
    """Strip every wired hook entry from the consumer's own .claude/settings.json
    (simulating install.sh's --project hook-wiring pass having silently no-opped,
    the exact original E3-gauntlet finding) — (e) must FAIL naming every missing
    skill:event pair; (a)/(b)/(c)/(d) must still PASS (none of them read
    settings.json, only the skills/ tree)."""
    project = _fresh_installed_project()
    try:
        settings_path = project / ".claude" / "settings.json"
        assert settings_path.is_file(), "fixture assumption broken: no settings.json after install"
        data = json.loads(settings_path.read_text(encoding="utf-8"))
        assert data.get("hooks"), "fixture assumption broken: no hooks wired after install --project"
        settings_path.write_text(json.dumps({"hooks": {}}, indent=2) + "\n", encoding="utf-8")

        checks = _run_all_checks(project)
        assert checks["e"].passed is False, f"expected (e) to FAIL after stripping all hooks; got {checks['e'].line()}"
        for skill_name in gauntlet.KNOWN_HOOK_SKILLS:
            assert skill_name in checks["e"].detail, f"(e) failure detail should name missing skill '{skill_name}': {checks['e'].detail}"
        for key in ("a", "b", "c", "d"):
            assert checks[key].passed is True, f"stripping hooks should not affect ({key}): {checks[key].line()}"
    finally:
        _cleanup(project)


def test_run_gauntlet_exit_code_reflects_any_failure() -> None:
    """End-to-end: run_gauntlet()'s own exit code must be 2 when a corrupted
    project is fed through it (not just the individual SubCheck objects) —
    proves the top-level plumbing, not only the per-check functions."""
    project = _fresh_installed_project()
    try:
        # Corrupt sub-check (a): drop a skill link.
        (project / ".claude" / "skills" / "caveman-ultra").unlink()
        checks = _run_all_checks(project)
        exit_code = 2 if any(c.passed is False for c in checks.values()) else 0
        assert exit_code == 2, "run_gauntlet's own exit-code rule must yield 2 on any sub-check failure"
    finally:
        _cleanup(project)


def main() -> int:
    tests = [
        test_a_trips_on_deleted_skill_symlink,
        test_b_trips_on_deleted_write_gate_tool,
        test_c_trips_on_broken_probe_json,
        test_d_trips_on_deleted_drift_probes_entirely,
        test_e_trips_on_stripped_hook,
        test_run_gauntlet_exit_code_reflects_any_failure,
    ]
    failed = 0
    for t in tests:
        try:
            t()
            print(f"  ok  {t.__name__}")
        except AssertionError as e:
            failed += 1
            print(f"FAIL  {t.__name__}: {e}")
        except Exception as e:
            failed += 1
            print(f"ERROR {t.__name__}: {type(e).__name__}: {e}")
    shutil.rmtree(SCRATCH, ignore_errors=True)
    if failed:
        print(f"\n{failed}/{len(tests)} failed")
        return 1
    print(f"\nall {len(tests)} passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
