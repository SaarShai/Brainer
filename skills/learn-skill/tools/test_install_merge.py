#!/usr/bin/env python3
"""Regression tests for hook_merge.py — the installer's JSON-mutating logic.

Covers the failure modes an adversarial review raised for the Codex hooks merge:
re-install idempotency, stale-wiring prune, path-change re-wire (must NOT double-fire),
preservation of unrelated hooks, and refusal to clobber a corrupt config.
"""
import json
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
MERGE = HERE / "hook_merge.py"

CODEX_END = "bash ./.codex/skills/learn-skill/tools/hook_codex_stop.sh"
CODEX_START = "bash ./.codex/skills/learn-skill/tools/hook_session_start.sh"


def _run(kind, path, end, start):
    return subprocess.run([sys.executable, str(MERGE), kind, str(path), end, start],
                          capture_output=True, text=True)


def _count(data, event, needle="learn-skill"):
    return sum(1 for r in data.get("hooks", {}).get(event, [])
               for h in r.get("hooks", []) if needle in h.get("command", ""))


def test_codex_idempotent():
    """Three re-installs → exactly one learn-skill hook per event, every time."""
    with tempfile.TemporaryDirectory() as t:
        hp = Path(t) / "hooks.json"
        for _ in range(3):
            r = _run("codex", hp, CODEX_END, CODEX_START)
            assert r.returncode == 0, r.stderr
            data = json.loads(hp.read_text())
            assert _count(data, "Stop") == 1, data
            assert _count(data, "UserPromptSubmit") == 1, data
    print("ok test_codex_idempotent")


def test_codex_prunes_stale_and_preserves_others():
    """A stale Stop->hook_session_end.sh wiring is pruned; a non-learn-skill hook stays."""
    with tempfile.TemporaryDirectory() as t:
        hp = Path(t) / "hooks.json"
        hp.write_text(json.dumps({"hooks": {"Stop": [{"matcher": "*", "hooks": [
            {"type": "command", "command": "bash ./.codex/skills/learn-skill/tools/hook_session_end.sh"},
            {"type": "command", "command": "bash ./.codex/skills/OTHER/run.sh"}]}]}}))
        assert _run("codex", hp, CODEX_END, CODEX_START).returncode == 0
        data = json.loads(hp.read_text())
        cmds = [h["command"] for r in data["hooks"]["Stop"] for h in r["hooks"]]
        assert CODEX_END in cmds, cmds                       # new wiring added
        assert not any("hook_session_end.sh" in c for c in cmds), cmds  # stale pruned
        assert any("OTHER" in c for c in cmds), cmds         # unrelated hook preserved
        assert _count(data, "Stop") == 1, cmds
    print("ok test_codex_prunes_stale_and_preserves_others")


def test_codex_path_change_no_double_wire():
    """Re-wire to a different command path → old learn-skill hook pruned, not doubled."""
    with tempfile.TemporaryDirectory() as t:
        hp = Path(t) / "hooks.json"
        assert _run("codex", hp, CODEX_END, CODEX_START).returncode == 0
        moved = "bash ./.claude/skills/learn-skill/tools/hook_codex_stop.sh"
        assert _run("codex", hp, moved, CODEX_START).returncode == 0
        data = json.loads(hp.read_text())
        assert _count(data, "Stop") == 1, data
        cmds = [h["command"] for r in data["hooks"]["Stop"] for h in r["hooks"]]
        assert moved in cmds and CODEX_END not in cmds, cmds
    print("ok test_codex_path_change_no_double_wire")


def test_corrupt_config_aborts_without_clobber():
    """A corrupt config is NOT overwritten — installer aborts so the human fixes it."""
    with tempfile.TemporaryDirectory() as t:
        hp = Path(t) / "hooks.json"
        hp.write_text("{not valid json")
        r = _run("codex", hp, CODEX_END, CODEX_START)
        assert r.returncode == 1, r
        assert "ABORT" in r.stderr, r.stderr
        assert hp.read_text() == "{not valid json"          # untouched
    print("ok test_corrupt_config_aborts_without_clobber")


def test_settings_idempotent_no_prune():
    """Claude settings merge is idempotent and does NOT prune (stable paths)."""
    end = "bash ./.claude/skills/learn-skill/tools/hook_session_end.sh"
    start = "bash ./.claude/skills/learn-skill/tools/hook_session_start.sh"
    with tempfile.TemporaryDirectory() as t:
        sp = Path(t) / "settings.json"
        for _ in range(2):
            assert _run("settings", sp, end, start).returncode == 0
        data = json.loads(sp.read_text())
        assert _count(data, "SessionEnd") == 1, data
        assert _count(data, "SessionStart") == 1, data
    print("ok test_settings_idempotent_no_prune")


def test_settings_preserves_existing_hooks():
    """An unrelated SessionStart hook survives the merge."""
    end = "bash ./.claude/skills/learn-skill/tools/hook_session_end.sh"
    start = "bash ./.claude/skills/learn-skill/tools/hook_session_start.sh"
    with tempfile.TemporaryDirectory() as t:
        sp = Path(t) / "settings.json"
        sp.write_text(json.dumps({"hooks": {"SessionStart": [{"matcher": "*", "hooks": [
            {"type": "command", "command": "bash ./other-tool.sh"}]}]}, "permissions": {"allow": ["x"]}}))
        assert _run("settings", sp, end, start).returncode == 0
        data = json.loads(sp.read_text())
        cmds = [h["command"] for r in data["hooks"]["SessionStart"] for h in r["hooks"]]
        assert "bash ./other-tool.sh" in cmds, cmds
        assert data.get("permissions") == {"allow": ["x"]}, data   # untouched
    print("ok test_settings_preserves_existing_hooks")


if __name__ == "__main__":
    test_codex_idempotent()
    test_codex_prunes_stale_and_preserves_others()
    test_codex_path_change_no_double_wire()
    test_corrupt_config_aborts_without_clobber()
    test_settings_idempotent_no_prune()
    test_settings_preserves_existing_hooks()
    print("ALL 6 TESTS PASSED")
