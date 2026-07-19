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
        try:
            rc = bh.main(args)
        except SystemExit as exc:
            rc = int(exc.code)
    return rc, out.getvalue(), err.getvalue()


def _valid_brief(*, scope: str = "src/widget.py", verify: str = "python3 -m unittest") -> str:
    return "\n".join((
        "GOAL: implement the bounded change",
        f"IN-SCOPE: {scope}",
        "OUT-OF-SCOPE: unrelated modules",
        "DONE MEANS:",
        "- requested behavior is present",
        "- focused regression test passes",
        f"VERIFY: {verify}",
        "",
        bh.GATE_BLOCK,
        "",
        bh.LANE_REPORT_BLOCK,
    ))


def test_header_contains_gate_block_verbatim():
    with tempfile.TemporaryDirectory() as root:
        _write_skill(root, "alpha", "keep alpha active")
        rc, out, _err = _run(["--skills-root", root, "--task", "check header", "--skills", "alpha"])
    return rc == 0 and bh.GATE_BLOCK in out


def test_rendered_blocks_share_required_marker_constants():
    return (bh.GATE_MARKER in bh.GATE_BLOCK
            and bh.LANE_REPORT_MARKER in bh.LANE_REPORT_BLOCK
            and bh.READY_MARKER in bh.GATE_BLOCK
            and bh.READY_MARKER in bh.LANE_REPORT_BLOCK
            and bh._REQUIRED_MARKERS == (  # noqa: SLF001
                bh.GATE_MARKER, bh.LANE_REPORT_MARKER, bh.READY_MARKER))


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


def test_default_discovers_but_injects_no_skill_rules():
    with tempfile.TemporaryDirectory() as root:
        _write_skill(root, "alpha", "keep alpha active")
        _write_skill(root, "beta", "keep beta active")
        rc, out, err = _run(["--skills-root", root, "--task", "default"])
    return (rc == 0
            and err == ""
            and "keep alpha active" not in out
            and "keep beta active" not in out
            and "none (add only task-required rules with --skills)" in out)


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


def test_default_output_contains_phase0_and_lane_report_blocks():
    with tempfile.TemporaryDirectory() as root:
        _write_skill(root, "alpha", "keep alpha active")
        rc, out, _err = _run(["--skills-root", root, "--task", "check new blocks", "--skills", "alpha"])
    return (rc == 0
            and bh.PHASE0_BLOCK in out
            and bh.LANE_REPORT_BLOCK in out
            and "PHASE 0" in out
            and "STATUS: COMPLETE" in out
            and "READY FOR JUDGING" in out)


def test_no_phase0_flag_removes_only_phase0_block():
    with tempfile.TemporaryDirectory() as root:
        _write_skill(root, "alpha", "keep alpha active")
        rc, out, _err = _run(
            ["--skills-root", root, "--task", "no phase0", "--skills", "alpha", "--no-phase0"]
        )
    return (rc == 0
            and bh.PHASE0_BLOCK not in out
            and bh.GATE_BLOCK in out
            and bh.LANE_REPORT_BLOCK in out)


def test_no_report_flag_removes_only_lane_report_block():
    with tempfile.TemporaryDirectory() as root:
        _write_skill(root, "alpha", "keep alpha active")
        rc, out, _err = _run(
            ["--skills-root", root, "--task", "no report", "--skills", "alpha", "--no-report"]
        )
    return (rc == 0
            and bh.LANE_REPORT_BLOCK not in out
            and bh.PHASE0_BLOCK in out
            and bh.GATE_BLOCK in out)


def test_plain_lint_remains_backward_compatible():
    old_stdin = sys.stdin
    try:
        sys.stdin = io.StringIO("")
        with tempfile.TemporaryDirectory() as root:
            rc, out, _err = _run([
                "--skills-root", root, "--lint-brief", "-",
            ])
    finally:
        sys.stdin = old_stdin
    return rc == 0 and "brief lint: clean" in out


def test_strict_contract_accepts_coding_and_research_briefs():
    briefs = (
        _valid_brief(),
        _valid_brief(
            scope="the supplied interview transcripts",
            verify="compare every extracted claim with its source transcript",
        ).replace("VERIFY:", "VERIFICATION:", 1),
    )
    for brief in briefs:
        old_stdin = sys.stdin
        try:
            sys.stdin = io.StringIO(brief)
            with tempfile.TemporaryDirectory() as root:
                rc, out, _err = _run([
                    "--skills-root", root, "--lint-brief", "-", "--strict-contract",
                ])
        finally:
            sys.stdin = old_stdin
        if rc != 0 or "brief lint: clean" not in out:
            return False
    return True


def test_strict_contract_rejects_each_missing_required_field():
    for field in ("GOAL", "IN-SCOPE", "OUT-OF-SCOPE", "DONE MEANS", "VERIFY"):
        brief = "\n".join(
            line for line in _valid_brief().splitlines()
            if not line.startswith(f"{field}:")
        )
        findings = bh.lint_brief(brief, strict_contract=True)
        if not any(f"missing required field: {field}" in finding for finding in findings):
            return False
    return True


def test_strict_contract_rejects_duplicate_required_fields():
    for field in ("GOAL", "IN-SCOPE", "OUT-OF-SCOPE", "DONE MEANS", "VERIFY"):
        duplicate = next(
            line for line in _valid_brief().splitlines()
            if line.startswith(f"{field}:")
        )
        findings = bh.lint_brief(
            _valid_brief() + f"\n{duplicate}", strict_contract=True)
        if not any(f"duplicate required field: {field}" in finding for finding in findings):
            return False
    return True


def test_strict_contract_rejects_empty_and_placeholder_values():
    empty_replacements = (
        ("GOAL: implement the bounded change", "GOAL:"),
        ("IN-SCOPE: src/widget.py", "IN-SCOPE:"),
        ("OUT-OF-SCOPE: unrelated modules", "OUT-OF-SCOPE:"),
        ("DONE MEANS:\n- requested behavior is present\n- focused regression test passes",
         "DONE MEANS:"),
        ("VERIFY: python3 -m unittest", "VERIFY:"),
    )
    for original, replacement in empty_replacements:
        findings = bh.lint_brief(
            _valid_brief().replace(original, replacement), strict_contract=True)
        if not any("empty required field" in f for f in findings):
            return False

    placeholder_replacements = (
        ("GOAL: implement the bounded change", "GOAL: <goal>"),
        ("GOAL: implement the bounded change", "GOAL: TODO later"),
        ("IN-SCOPE: src/widget.py", "IN-SCOPE: [TBD]"),
        ("OUT-OF-SCOPE: unrelated modules", "OUT-OF-SCOPE: TODO"),
        ("- requested behavior is present", "- <criterion>"),
        ("VERIFY: python3 -m unittest", "VERIFY: <command>"),
    )
    for original, replacement in placeholder_replacements:
        findings = bh.lint_brief(
            _valid_brief().replace(original, replacement), strict_contract=True)
        if not any("placeholder in required field" in f for f in findings):
            return False
    return True


def test_strict_contract_accepts_inline_done_means():
    brief = _valid_brief().replace(
        "DONE MEANS:\n- requested behavior is present\n- focused regression test passes",
        "DONE MEANS: requested behavior and its focused regression test pass",
    )
    return bh.lint_brief(brief, strict_contract=True) == []


def test_strict_contract_accepts_shell_redirection_in_verify():
    brief = _valid_brief(verify="command <in >out")
    return bh.lint_brief(brief, strict_contract=True) == []


def test_strict_contract_rejects_more_than_five_done_criteria():
    criteria = "\n".join(f"- criterion {n}" for n in range(1, 7))
    brief = _valid_brief().replace(
        "- requested behavior is present\n- focused regression test passes", criteria)
    findings = bh.lint_brief(brief, strict_contract=True)
    return any("DONE MEANS has 6 criteria; maximum is 5" in f for f in findings)


def test_strict_contract_requires_gate_report_and_ready_markers():
    markers = (
        "GATE (re-run, do not self-certify):",
        "LANE REPORT (hard shape",
        "READY FOR JUDGING",
    )
    for marker in markers:
        findings = bh.lint_brief(
            _valid_brief().replace(marker, "REMOVED"), strict_contract=True)
        if not any(f"missing required marker: {marker}" in f for f in findings):
            return False
    return True


def test_strict_contract_keeps_elided_literal_check():
    findings = bh.lint_brief(
        _valid_brief(scope="…/FINAL production/widget.py"), strict_contract=True)
    return any("elided literal" in finding for finding in findings)


def test_strict_contract_without_lint_is_cli_misuse():
    with tempfile.TemporaryDirectory() as root:
        rc, _out, err = _run([
            "--skills-root", root, "--task", "misuse", "--strict-contract",
        ])
    return rc == 2 and "--strict-contract requires --lint-brief" in err


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
