#!/usr/bin/env python3
"""Tests for brief_header.py — plain-python (no pytest dep), runnable standalone.

Shape mirrors test_model_roster.py: test_* functions return truthy on success,
main() prints PASS/FAIL lines, and the process exits with the failure count.
"""
from __future__ import annotations

import io
import os
import sys
import tempfile
from contextlib import redirect_stderr, redirect_stdout

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import brief_header as bh  # noqa: E402


def _write_skill(root: str, name: str, reminder: str) -> None:
    skill_dir = os.path.join(root, name)
    os.makedirs(skill_dir)
    with open(os.path.join(skill_dir, "SKILL.md"), "w", encoding="utf-8") as fh:
        fh.write("---\n")
        fh.write(f"name: {name}\n")
        fh.write(f'pulse_reminder: "{reminder}"\n')
        fh.write("---\n")
        fh.write(f"# {name}\n")


def _run(args: list[str]) -> tuple[int, str, str]:
    out = io.StringIO()
    err = io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        rc = bh.main(args)
    return rc, out.getvalue(), err.getvalue()


def test_header_contains_gate_block_verbatim():
    with tempfile.TemporaryDirectory() as root:
        _write_skill(root, "alpha", "keep alpha active")
        rc, out, _err = _run(["--skills-root", root, "--task", "check header", "--skills", "alpha"])
    return rc == 0 and bh.GATE_BLOCK in out


def test_skills_subset_includes_only_named_skills():
    with tempfile.TemporaryDirectory() as root:
        _write_skill(root, "alpha", "keep alpha active")
        _write_skill(root, "beta", "keep beta active")
        _write_skill(root, "gamma", "keep gamma active")
        rc, out, _err = _run(["--skills-root", root, "--task", "subset", "--skills", "gamma,alpha"])
    return (rc == 0
            and "- gamma: keep gamma active" in out
            and "- alpha: keep alpha active" in out
            and "- beta: keep beta active" not in out)


def test_unknown_skill_warns_but_exits_zero():
    with tempfile.TemporaryDirectory() as root:
        _write_skill(root, "alpha", "keep alpha active")
        rc, out, err = _run(["--skills-root", root, "--task", "warn", "--skills", "alpha,missing"])
    return (rc == 0
            and "- alpha: keep alpha active" in out
            and "WARNING:" in err
            and "missing" in err)


def test_list_outputs_known_skill_reminder_line():
    with tempfile.TemporaryDirectory() as root:
        _write_skill(root, "alpha", "keep alpha active")
        _write_skill(root, "beta", "keep beta active")
        rc, out, err = _run(["--skills-root", root, "--list"])
    return (rc == 0
            and err == ""
            and "alpha: keep alpha active" in out
            and "beta: keep beta active" in out)


TESTS = [v for k, v in sorted(globals().items()) if k.startswith("test_")]


def main() -> int:
    failures = 0
    for t in TESTS:
        try:
            ok = t()
        except Exception as e:  # noqa: BLE001
            ok = False
            print(f"ERROR {t.__name__}: {e}")
        if ok:
            print(f"PASS {t.__name__}")
        else:
            failures += 1
            print(f"FAIL {t.__name__}")
    total = len(TESTS)
    print(f"\n{total - failures}/{total} passed")
    return failures


if __name__ == "__main__":
    sys.exit(main())
