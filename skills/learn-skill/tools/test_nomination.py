#!/usr/bin/env python3
"""Tests for the workflow_nomination detector (lives in compliance-canary/hook.py).
Run: python skills/learn-skill/tools/test_nomination.py"""
from __future__ import annotations

import sys
from pathlib import Path

_HOOK = Path(__file__).resolve().parents[2] / "compliance-canary" / "tools"
sys.path.insert(0, str(_HOOK))
import hook  # noqa: E402

PROBE = {"kind": "workflow_nomination", "min_tool_calls": 6, "_probe_id": "learn-skill:nominate"}
DONE_MSG = [{"text": "Done — all tests pass and the feature is complete."}]
PROMISE_MSG = [{"text": "Next I'll start wiring the installer."}]
EDIT_USES = [{"name": "Edit", "input": {}}]
TRIVIAL_USES = [{"name": "Bash", "input": {"command": "npm test"}},
                {"name": "Bash", "input": {"command": "git status"}}]


def _det(messages, tool_uses, calls, errs=0):
    traj = {"tool_calls": calls, "tool_errors": errs}
    return hook.detect_workflow_nomination(PROBE, messages, tool_uses, None,
                                           user_prompt="", traj_stats=traj)


def test_fires_on_nontrivial_completed_workflow():
    r = _det(DONE_MSG, EDIT_USES, calls=8)
    assert r is not None and r["tool_calls"] == 8, r
    print("ok test_fires_on_nontrivial_completed_workflow")


def test_silent_below_floor():
    assert _det(DONE_MSG, EDIT_USES, calls=4) is None
    print("ok test_silent_below_floor")


def test_silent_without_completion_claim():
    assert _det(PROMISE_MSG, EDIT_USES, calls=10) is None
    print("ok test_silent_without_completion_claim")


def test_silent_when_all_trivial():
    assert _det(DONE_MSG, TRIVIAL_USES, calls=9) is None
    print("ok test_silent_when_all_trivial")


def test_substantive_bash_fires():
    uses = [{"name": "Bash", "input": {"command": "python3 my_custom_pipeline.py --transform"}}]
    assert _det(DONE_MSG, uses, calls=7) is not None
    print("ok test_substantive_bash_fires")


def test_recovered_flag():
    r = _det(DONE_MSG, EDIT_USES, calls=8, errs=3)
    assert r["recovered_after_errors"] is True
    print("ok test_recovered_flag")


def test_env_and_sudo_prefix_still_trivial():
    """LOW regression: env-var / sudo prefixes must not smuggle boilerplate past the
    triviality filter."""
    uses = [{"name": "Bash", "input": {"command": "FOO=1 BAR=2 npm test"}},
            {"name": "Bash", "input": {"command": "sudo make install"}}]
    assert _det(DONE_MSG, uses, calls=9) is None
    print("ok test_env_and_sudo_prefix_still_trivial")


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
    print(f"\nALL {len(fns)} TESTS PASSED")
