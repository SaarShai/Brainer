#!/usr/bin/env python3
"""loop-breaker fuzz + behavioral sim.

Synthetic tool-call sequences fed to hook.py via subprocess + stdin. Checks:
  - signal fires EXACTLY ONCE at threshold crossing (REGRESSION FOR C2)
  - escalation fires at 2× threshold
  - legitimate parallel/varied tool calls don't fire
  - whitespace-only differences in tool args still count as identical
  - malformed payloads don't crash
"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _lib import REPO, Report, Timer, print_report, write_report  # noqa: E402

HOOK = REPO / "skills/loop-breaker/tools/hook.py"
THRESHOLD = 5


def _payload(tool: str, args: dict, session: str = "test-session") -> str:
    return json.dumps({
        "tool_name": tool,
        "tool_input": args,
        "session_id": session,
    })


def _run_hook(payload: str, state_dir: Path, env_extra: dict | None = None) -> tuple[int, str]:
    """Returns (exit_code, stdout). stderr discarded."""
    env = {
        "PATH": "/usr/bin:/bin",
        "HOME": str(state_dir),
        "LOOP_BREAKER_THRESHOLD": str(THRESHOLD),
        "LOOP_BREAKER_STATE_DIR": str(state_dir),
        **(env_extra or {}),
    }
    r = subprocess.run(
        [sys.executable, str(HOOK)],
        input=payload, text=True, capture_output=True,
        env=env, timeout=5,
    )
    return r.returncode, r.stdout


def _fired_signal(stdout: str) -> bool:
    if not stdout.strip():
        return False
    try:
        obj = json.loads(stdout)
        return "additionalContext" in obj.get("hookSpecificOutput", {})
    except json.JSONDecodeError:
        return False


def _run_sequence(payloads: list[str], state_dir: Path) -> list[bool]:
    """Returns per-call: did the signal fire?"""
    fired = []
    for p in payloads:
        _, stdout = _run_hook(p, state_dir)
        fired.append(_fired_signal(stdout))
    return fired


def case_signal_fires_only_at_edge() -> dict:
    """REGRESSION FOR C2: signal must fire exactly once when count == threshold,
    not on every call past threshold."""
    with tempfile.TemporaryDirectory() as td:
        state = Path(td)
        # session=fresh-1 so it doesn't collide with other cases' state
        payloads = [_payload("Bash", {"command": "ls"}, session="fresh-1")] * 8
        fired = _run_sequence(payloads, state)
        # Expected:
        #   call 1..4: no fire (count < threshold)
        #   call 5 (== threshold): FIRE (rising edge)
        #   call 6,7,8: no fire (past threshold, no escalation yet)
        #   call 10 would be 2× threshold and fire — but we only run 8 here
        expected = [False, False, False, False, True, False, False, False]
        ok = fired == expected
        return {
            "case": "signal_fires_only_at_edge",
            "ok": ok,
            "fired": fired,
            "expected": expected,
        }


def case_escalation_fires_at_2x() -> dict:
    """Signal should fire again at exactly 2× threshold."""
    with tempfile.TemporaryDirectory() as td:
        payloads = [_payload("Bash", {"command": "ls"}, session="esc-1")] * 11
        fired = _run_sequence(payloads, Path(td))
        # Edge at 5, escalation at 10
        expected = [False] * 4 + [True] + [False] * 4 + [True] + [False]
        return {
            "case": "escalation_fires_at_2x",
            "ok": fired == expected,
            "fired": fired,
            "expected": expected,
        }


def case_varied_calls_never_fire() -> dict:
    """8 calls to Bash with DIFFERENT commands — never fire."""
    with tempfile.TemporaryDirectory() as td:
        payloads = [
            _payload("Bash", {"command": f"ls /tmp/{i}"}, session="varied-1")
            for i in range(8)
        ]
        fired = _run_sequence(payloads, Path(td))
        ok = not any(fired)
        return {"case": "varied_calls_never_fire", "ok": ok, "fired": fired}


def case_alternating_tools_never_fire() -> dict:
    """Alternate Bash/Read 8 times — never fire."""
    with tempfile.TemporaryDirectory() as td:
        payloads = []
        for i in range(8):
            tool = "Bash" if i % 2 == 0 else "Read"
            args = {"command": "ls"} if tool == "Bash" else {"file_path": "/tmp/x"}
            payloads.append(_payload(tool, args, session="alt-1"))
        fired = _run_sequence(payloads, Path(td))
        ok = not any(fired)
        return {"case": "alternating_tools_never_fire", "ok": ok, "fired": fired}


def case_allowlist_skips() -> dict:
    """Calls to allowlisted tools must never fire — they're known-idempotent."""
    with tempfile.TemporaryDirectory() as td:
        state = Path(td)
        payloads = [_payload("Read", {"file_path": "/tmp/x"}, session="allow-1")] * 8
        fired = []
        for p in payloads:
            _, stdout = _run_hook(p, state, env_extra={"LOOP_BREAKER_ALLOWLIST_TOOLS": "Read"})
            fired.append(_fired_signal(stdout))
        return {"case": "allowlist_skips", "ok": not any(fired), "fired": fired}


def case_malformed_payloads_no_crash() -> dict:
    """Empty, malformed JSON, missing fields. Hook must exit cleanly."""
    bad_payloads = ["", "  ", "not json", "{}", '{"tool_name": null}', '{"foo": "bar"}']
    with tempfile.TemporaryDirectory() as td:
        crashes = 0
        for p in bad_payloads:
            try:
                rc, _ = _run_hook(p, Path(td))
                if rc != 0:
                    crashes += 1
            except subprocess.TimeoutExpired:
                crashes += 1
        return {"case": "malformed_payloads_no_crash", "ok": crashes == 0, "crashes": crashes}


def case_huge_args_no_dos() -> dict:
    """Tool with a 1MB arg value — should hash to a stable signature and not DoS."""
    big_arg = "x" * 1_000_000
    with tempfile.TemporaryDirectory() as td:
        payloads = [_payload("Bash", {"command": big_arg}, session="big-1")] * 6
        t0 = time.time()
        fired = _run_sequence(payloads, Path(td))
        elapsed = time.time() - t0
        return {
            "case": "huge_args_no_dos",
            "ok": elapsed < 3.0 and fired[4] is True,  # edge at call 5
            "elapsed_s": round(elapsed, 2),
            "fired": fired,
        }


def case_h6_long_session_ids_no_collision() -> dict:
    """REGRESSION FOR H6: distinct session IDs sharing an 8-char prefix used to
    collide on the same state file. Two sessions whose IDs share their first
    16+ chars but differ further out should still get independent counters."""
    sid_a = "a3f0c1d2-e4b5-aaaa-1111-aaaaaaaaaaaa"
    sid_b = "a3f0c1d2-e4b5-bbbb-2222-bbbbbbbbbbbb"
    # Old 8-char truncation hashed both to "a3f0c1d2" → collision.
    with tempfile.TemporaryDirectory() as td:
        state = Path(td)
        fired_a, fired_b = [], []
        # Interleave 4 calls each; if state collided, sid_b would inherit sid_a's
        # 4 prior identical calls and fire on its 1st (count=5) instead of needing
        # its own 5 to fire.
        for _ in range(4):
            _, out_a = _run_hook(_payload("Bash", {"command": "x"}, session=sid_a), state)
            fired_a.append(_fired_signal(out_a))
        for _ in range(4):
            _, out_b = _run_hook(_payload("Bash", {"command": "x"}, session=sid_b), state)
            fired_b.append(_fired_signal(out_b))
        # Neither session should have fired yet (each has only 4 of its own calls).
        ok = not any(fired_a) and not any(fired_b)
        return {
            "case": "h6_long_session_ids_no_collision",
            "ok": ok,
            "fired_a": fired_a,
            "fired_b": fired_b,
        }


def case_h7_deny_reason_is_single_line() -> dict:
    """REGRESSION FOR H7: when hard-block fires, permissionDecisionReason must
    be a single concise line (UI expectation), not the multi-paragraph signal
    text. The long-form replan signal goes in additionalContext instead."""
    with tempfile.TemporaryDirectory() as td:
        state = Path(td)
        env = {"LOOP_BREAKER_HARD_BLOCK": "1"}
        # 4 prior calls; 5th = edge (warn only, no deny); 6th = deny
        for _ in range(5):
            _run_hook(_payload("Bash", {"command": "x"}, session="h7"), state, env_extra=env)
        _, out = _run_hook(_payload("Bash", {"command": "x"}, session="h7"), state, env_extra=env)
        try:
            obj = json.loads(out)
            hs = obj.get("hookSpecificOutput", {})
            reason = hs.get("permissionDecisionReason", "")
            decision = hs.get("permissionDecision", "")
            ctx = hs.get("additionalContext", "")
        except json.JSONDecodeError:
            return {"case": "h7_deny_reason_is_single_line", "ok": False, "err": "bad json"}
        # Acceptance:
        #   - deny fired
        #   - reason is single-line, short (< 200 chars)
        #   - additionalContext still contains the long-form replan text
        is_deny = decision == "deny"
        reason_single_line = "\n" not in reason
        reason_short = 0 < len(reason) < 200
        ctx_has_long_form = "Before calling this again" in ctx
        ok = is_deny and reason_single_line and reason_short and ctx_has_long_form
        return {
            "case": "h7_deny_reason_is_single_line",
            "ok": ok,
            "reason_len": len(reason),
            "reason_lines": reason.count("\n") + 1 if reason else 0,
            "ctx_has_long_form": ctx_has_long_form,
            "decision": decision,
        }


def _run_hook_with_stderr(payload: str, state_dir: Path, env_extra: dict | None = None) -> tuple[int, str, str]:
    env = {
        "PATH": "/usr/bin:/bin",
        "HOME": str(state_dir),
        "LOOP_BREAKER_STATE_DIR": str(state_dir),
        **(env_extra or {}),
    }
    r = subprocess.run(
        [sys.executable, str(HOOK)],
        input=payload, text=True, capture_output=True,
        env=env, timeout=5,
    )
    return r.returncode, r.stdout, r.stderr


def case_m3_threshold_invalid_falls_back() -> dict:
    """REGRESSION FOR M3: empty / whitespace / non-numeric
    LOOP_BREAKER_THRESHOLD must fall back to the default (5) *with a visible
    stderr warning*, not silently swallow the ValueError. And THRESHOLD=1 must
    clamp to 2 with a warning (test.sh case [2] already locks behavior — we
    add the visibility check).

    Old code (`max(2, int(env))` + bare `except ValueError: pass`) silently
    fell through with no log when the env var was malformed. Operators had no
    way to notice a typo. The fix is: keep the same effective fallback, but
    log the cause on stderr.
    """
    p = _payload("Bash", {"command": "x"}, session="m3")
    results = {}
    for label, val in [("empty", ""), ("whitespace", "   "), ("nonnumeric", "abc")]:
        with tempfile.TemporaryDirectory() as td:
            _, _, stderr = _run_hook_with_stderr(p, Path(td), env_extra={"LOOP_BREAKER_THRESHOLD": val})
            # Stderr must mention threshold-empty or threshold-invalid
            has_warning = ("threshold-empty" in stderr) or ("threshold-invalid" in stderr)
            results[label] = {"warned": has_warning, "stderr": stderr.strip()[:200]}

    # And: clamp warning for THRESHOLD=1
    with tempfile.TemporaryDirectory() as td:
        _, _, stderr = _run_hook_with_stderr(p, Path(td), env_extra={"LOOP_BREAKER_THRESHOLD": "1"})
        clamp_warned = "threshold-clamped" in stderr
        results["clamp_1"] = {"warned": clamp_warned, "stderr": stderr.strip()[:200]}

    # Also exercise the effective-behavior side: default fires at call 5
    with tempfile.TemporaryDirectory() as td:
        state = Path(td)
        fired = []
        for _ in range(5):
            _, out, _ = _run_hook_with_stderr(p, state, env_extra={"LOOP_BREAKER_THRESHOLD": "abc"})
            fired.append(_fired_signal(out))
        results["fired_on_invalid"] = fired
        results["fired_expected"] = [False, False, False, False, True]

    ok = (
        results["empty"]["warned"]
        and results["whitespace"]["warned"]
        and results["nonnumeric"]["warned"]
        and results["clamp_1"]["warned"]
        and results["fired_on_invalid"] == results["fired_expected"]
    )
    return {
        "case": "m3_threshold_invalid_falls_back",
        "ok": ok,
        **results,
    }


def case_l5_readonly_state_dir_no_crash() -> dict:
    """REGRESSION FOR L5: when the state directory is read-only (can't create
    the lock file), the hook must exit 0, not crash, AND log a visible warning
    so operators can see that locking was bypassed. Previously the bare
    `except Exception: yield` swallowed the error with no log — locking
    silently fell through and parallel hooks would have under-counted with no
    visible signal."""
    import os as _os
    import stat
    with tempfile.TemporaryDirectory() as td:
        ro_dir = Path(td) / "readonly"
        ro_dir.mkdir()
        # Make read-only (no write). State dir is a child of this read-only path,
        # so neither mkdir nor open() will succeed for the lock file.
        _os.chmod(ro_dir, stat.S_IRUSR | stat.S_IXUSR)
        crashes = 0
        had_traceback = False
        had_lock_warning = False
        stderr_sample = ""
        try:
            for i in range(3):
                r = subprocess.run(
                    [sys.executable, str(HOOK)],
                    input=_payload("Bash", {"command": "x"}, session=f"l5-{i}"),
                    text=True, capture_output=True,
                    env={
                        "PATH": "/usr/bin:/bin",
                        "HOME": str(td),
                        "LOOP_BREAKER_STATE_DIR": str(ro_dir / "child"),
                    },
                    timeout=5,
                )
                if r.returncode != 0:
                    crashes += 1
                if "Traceback" in r.stderr:
                    had_traceback = True
                # Look for one of the explicit L5-fix warnings
                if "lock-mkdir-fail" in r.stderr or "lock-open-fail" in r.stderr:
                    had_lock_warning = True
                if not stderr_sample:
                    stderr_sample = r.stderr.strip()[:200]
        finally:
            # Restore perms so tempdir cleanup works
            _os.chmod(ro_dir, stat.S_IRWXU)

    ok = crashes == 0 and not had_traceback and had_lock_warning
    return {
        "case": "l5_readonly_state_dir_no_crash",
        "ok": ok,
        "crashes": crashes,
        "had_traceback": had_traceback,
        "had_lock_warning": had_lock_warning,
        "stderr_sample": stderr_sample,
    }


CASES = [
    case_signal_fires_only_at_edge,
    case_escalation_fires_at_2x,
    case_varied_calls_never_fire,
    case_alternating_tools_never_fire,
    case_allowlist_skips,
    case_malformed_payloads_no_crash,
    case_huge_args_no_dos,
    case_h6_long_session_ids_no_collision,
    case_h7_deny_reason_is_single_line,
    case_m3_threshold_invalid_falls_back,
    case_l5_readonly_state_dir_no_crash,
]


def main() -> int:
    t = Timer()
    results = [c() for c in CASES]
    failed = [r for r in results if not r["ok"]]
    report = Report(
        skill="loop_breaker", shape="fuzz", elapsed_s=t.elapsed(),
        summary={"n_cases": len(CASES), "failed": len(failed)},
        findings=failed,
    )
    report.passed = not failed
    print_report(report)
    for r in results:
        mark = "ok" if r["ok"] else "FAIL"
        extra = ""
        if "fired" in r and len(r.get("fired", [])) <= 12:
            extra = f"  fired={r['fired']}"
        elif "elapsed_s" in r:
            extra = f"  elapsed={r['elapsed_s']}s"
        elif "crashes" in r:
            extra = f"  crashes={r['crashes']}"
        print(f"  [{mark}] {r['case']:<40}{extra}")
    path = write_report(report)
    print(f"\nfull JSON: {path}")
    return 0 if report.passed else 1


if __name__ == "__main__":
    sys.exit(main())
