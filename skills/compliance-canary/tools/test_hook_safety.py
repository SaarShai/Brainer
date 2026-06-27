#!/usr/bin/env python3
"""Tests for hook-safety tooling (BUILD #7).

Covers:
  1. hook_validate.py PASSES on the 3 real existing hook entrypoints
     (compliance-canary, context-keeper, prompt-triage — all already exit 0
     on every path).
  2. hook_validate.py FLAGS a crafted temp hook that exits 1 / prints partial
     stdout before erroring / shells out without a timeout.
  3. deadline.py returns control / exits 0 cleanly on a simulated timeout.
  4. The new `hook_output_anomaly` probe is valid per check_drift_probes.py.

Standalone python3 (no pytest). Exit code is the verdict.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import textwrap
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[2]
VALIDATE = HERE / "hook_validate.py"
DEADLINE = HERE / "deadline.py"
CHECK_PROBES = REPO_ROOT / "scripts" / "check_drift_probes.py"

PASS = 0
FAIL = 0
FAILED: list[str] = []


def check(label: str, cond: bool, detail: str = "") -> None:
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"PASS {label}")
    else:
        FAIL += 1
        FAILED.append(label)
        print(f"FAIL {label}{('  — ' + detail) if detail else ''}")


def run_validate(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(VALIDATE), *args],
        capture_output=True,
        text=True,
        timeout=60,
    )


# ── 1. real hooks pass ──────────────────────────────────────────────────────
def test_real_hooks_pass() -> None:
    real = [
        REPO_ROOT / "skills" / "compliance-canary" / "tools" / "hook.py",
        REPO_ROOT / "skills" / "compliance-canary" / "tools" / "hook.sh",
        REPO_ROOT / "skills" / "context-keeper" / "tools" / "hook.py",
        REPO_ROOT / "skills" / "context-keeper" / "tools" / "hook.sh",
        REPO_ROOT / "skills" / "prompt-triage" / "tools" / "hook.sh",
    ]
    for f in real:
        check(f"real-exists:{f.relative_to(REPO_ROOT)}", f.is_file())
    proc = run_validate(*[str(f) for f in real])
    check(
        "real-hooks-clean",
        proc.returncode == 0,
        f"rc={proc.returncode} out={proc.stdout.strip()[-400:]}",
    )


def test_repo_sweep_runs() -> None:
    # No args → sweep every entrypoint under skills/*/tools/. The sweep must run
    # and must NOT flag any of the three in-scope hooks (compliance-canary,
    # context-keeper, prompt-triage). Other skills' entrypoints are out of scope
    # here — a finding elsewhere is a legitimate report, not a test failure.
    proc = run_validate("--json")
    try:
        data = json.loads(proc.stdout)
    except json.JSONDecodeError:
        check("repo-sweep-runs", False, proc.stdout[-400:])
        return
    flagged = set(data.get("files", {}))
    in_scope = {
        "skills/compliance-canary/tools/hook.py",
        "skills/compliance-canary/tools/hook.sh",
        "skills/context-keeper/tools/hook.py",
        "skills/context-keeper/tools/hook.sh",
        "skills/prompt-triage/tools/hook.sh",
    }
    leaked = in_scope & flagged
    check("repo-sweep-runs", isinstance(data.get("findings"), int))
    check("repo-sweep-inscope-clean", not leaked, f"leaked={leaked}")


# ── 2. crafted bad hook is flagged ──────────────────────────────────────────
BAD_PY = textwrap.dedent(
    '''\
    #!/usr/bin/env python3
    import sys, subprocess
    def main():
        sys.stdout.write("partial output before any error\\n")
        if not sys.stdin.read():
            print("log: empty payload")   # log to stdout
            sys.exit(1)                    # non-zero on error path
        subprocess.run(["true"])           # no timeout=
        return 0
    if __name__ == "__main__":
        sys.exit(main())
    '''
)

BAD_SH = textwrap.dedent(
    '''\
    #!/usr/bin/env bash
    set -e
    python3 "$(dirname "$0")/worker.py"
    '''
)


def test_bad_py_flagged() -> None:
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "hook.py"
        p.write_text(BAD_PY, encoding="utf-8")
        proc = run_validate(str(p))
        out = proc.stdout
        check("bad-py-nonzero-rc", proc.returncode != 0, f"rc={proc.returncode}")
        check("bad-py-flags-exit", "nonzero_exit" in out, out[-400:])
        check("bad-py-flags-partial-stdout", "partial_stdout" in out, out[-400:])
        check("bad-py-flags-no-timeout", "subprocess_no_timeout" in out, out[-400:])
        check("bad-py-flags-stdout-log", "stdout_log" in out, out[-400:])


def test_bad_sh_flagged() -> None:
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "hook.sh"
        p.write_text(BAD_SH, encoding="utf-8")
        proc = run_validate(str(p))
        out = proc.stdout
        check("bad-sh-nonzero-rc", proc.returncode != 0, f"rc={proc.returncode}")
        # `set -e` with no `exit 0`/`|| true` guard can leak a non-zero exit.
        check("bad-sh-flags-exit", "nonzero_exit" in out, out[-400:])


# ── 3. deadline wrapper exits 0 / returns control on timeout ────────────────
def test_deadline_timeout_returns_control() -> None:
    # In-process: the context manager must surface a HookDeadline on overrun
    # and let the caller fall through to a clean exit, NOT raise out.
    prog = textwrap.dedent(
        f'''\
        import sys, time
        sys.path.insert(0, {str(HERE)!r})
        import deadline
        fired = False
        try:
            with deadline.hard_deadline(0.2):
                time.sleep(5)
        except deadline.HookDeadline:
            fired = True
        print("FIRED" if fired else "NOFIRE")
        sys.exit(0)
        '''
    )
    proc = subprocess.run(
        [sys.executable, "-c", prog], capture_output=True, text=True, timeout=30
    )
    check("deadline-fires", "FIRED" in proc.stdout, proc.stdout + proc.stderr)
    check("deadline-clean-exit", proc.returncode == 0, f"rc={proc.returncode}")


def test_deadline_guard_helper_exits_zero() -> None:
    # The `run_or_exit0` convenience: on timeout it must _exit(0) — the cbm
    # cardinal rule — never propagate a non-zero status to the host.
    prog = textwrap.dedent(
        f'''\
        import sys, time
        sys.path.insert(0, {str(HERE)!r})
        import deadline
        deadline.run_or_exit0(lambda: time.sleep(5), seconds=0.2)
        print("SHOULD-NOT-REACH")   # deadline must _exit(0) first
        sys.exit(7)
        '''
    )
    proc = subprocess.run(
        [sys.executable, "-c", prog], capture_output=True, text=True, timeout=30
    )
    check("deadline-run-exit0", proc.returncode == 0, f"rc={proc.returncode}")
    check(
        "deadline-run-no-reach",
        "SHOULD-NOT-REACH" not in proc.stdout,
        proc.stdout,
    )


def test_deadline_no_timeout_runs_normally() -> None:
    prog = textwrap.dedent(
        f'''\
        import sys
        sys.path.insert(0, {str(HERE)!r})
        import deadline
        with deadline.hard_deadline(5):
            x = 2 + 2
        print(x)
        '''
    )
    proc = subprocess.run(
        [sys.executable, "-c", prog], capture_output=True, text=True, timeout=30
    )
    check("deadline-passthrough", proc.stdout.strip() == "4", proc.stdout + proc.stderr)


# ── 4. new probe is valid per check_drift_probes.py ─────────────────────────
def test_probe_valid() -> None:
    proc = subprocess.run(
        [sys.executable, str(CHECK_PROBES)],
        capture_output=True,
        text=True,
        timeout=30,
        cwd=str(REPO_ROOT),
    )
    check("probe-check-passes", proc.returncode == 0, proc.stdout + proc.stderr)
    probes = json.loads(
        (REPO_ROOT / "skills" / "compliance-canary" / "drift_probes.json").read_text()
    )
    ids = {p.get("id") for p in probes}
    check("probe-present", "hook-output-anomaly" in ids, str(ids))


def main() -> int:
    test_real_hooks_pass()
    test_repo_sweep_runs()
    test_bad_py_flagged()
    test_bad_sh_flagged()
    test_deadline_timeout_returns_control()
    test_deadline_guard_helper_exits_zero()
    test_deadline_no_timeout_runs_normally()
    test_probe_valid()
    print()
    if FAIL == 0:
        print(f"test_hook_safety: {PASS}/{PASS} PASS")
        return 0
    print(f"test_hook_safety: {PASS} passed, {FAIL} FAILED:")
    for f in FAILED:
        print(f"  - {f}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
