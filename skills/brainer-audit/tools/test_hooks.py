#!/usr/bin/env python3
"""Plain-python tests for brainer-audit Claude/Codex hook adapters."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
HOOK = HERE / "hook.py"
AUDIT_SESSION = HERE / "audit_session.py"
TASK_AUDIT = HERE.parents[1] / "task-retrospective" / "tools" / "task_audit.py"
REPO_ROOT = HERE.parents[2]


def run_cmd(cmd, *, input_obj=None, expect=0, env=None):
    merged = os.environ.copy()
    merged["PYTHONDONTWRITEBYTECODE"] = "1"
    if env:
        merged.update(env)
    stdin = json.dumps(input_obj) if input_obj is not None else None
    proc = subprocess.run(cmd, input=stdin, text=True, capture_output=True, env=merged)
    assert proc.returncode == expect, (cmd, proc.returncode, proc.stdout, proc.stderr)
    return proc


def read_jsonl(path: Path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def test_inactive_hook_writes_nothing():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        proc = run_cmd([
            sys.executable, str(HOOK), "--root", str(root), "--host", "claude", "--event", "UserPromptSubmit", "--debug"
        ], input_obj={"session_id": "s1", "prompt": "hello", "cwd": str(root)})
        payload = json.loads(proc.stderr)
        assert payload["written"] == 0
        assert not (root / ".brainer").exists()


def test_brainer_audit_marker_records_claude_event():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        run_cmd([sys.executable, str(AUDIT_SESSION), "--root", str(root), "start", "--title", "demo", "--session-id", "demo"])
        proc = run_cmd([
            sys.executable, str(HOOK), "--root", str(root), "--host", "claude", "--event", "UserPromptSubmit", "--debug"
        ], input_obj={"session_id": "s1", "prompt": "please audit", "cwd": str(root)})
        assert json.loads(proc.stderr)["written"] == 1
        events_path = root / ".brainer" / "brainer-audit" / "sessions" / "demo" / "events.jsonl"
        events = read_jsonl(events_path)
        assert len(events) == 1
        assert events[0]["host"] == "claude"
        assert events[0]["event"] == "user_prompt"
        assert events[0]["content_summary"] == "please audit"


def test_codex_post_tool_use_normalizes_to_tool_result():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        run_cmd([sys.executable, str(AUDIT_SESSION), "--root", str(root), "start", "--title", "codex", "--session-id", "codex"])
        run_cmd([
            sys.executable, str(HOOK), "--root", str(root), "--host", "codex", "--event", "PostToolUse"
        ], input_obj={"session_id": "s2", "tool_name": "Bash", "command": "pytest -q", "exit_code": 0, "cwd": str(root)})
        events = read_jsonl(root / ".brainer" / "brainer-audit" / "sessions" / "codex" / "events.jsonl")
        assert events[0]["host"] == "codex"
        assert events[0]["event"] == "tool_result"
        assert events[0]["command"] == "pytest -q"
        assert events[0]["exit_code"] == 0


def test_task_retrospective_marker_gets_lightweight_note():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        run_cmd([
            sys.executable, str(TASK_AUDIT), "--root", str(root), "start",
            "--task", "demo task", "--repeat-trigger", "repeat", "--task-id", "task-demo"
        ])
        run_cmd([
            sys.executable, str(HOOK), "--root", str(root), "--host", "claude", "--event", "UserPromptSubmit"
        ], input_obj={"session_id": "s3", "prompt": "No, use the other file", "cwd": str(root)})
        path = root / ".brainer" / "task-retrospective" / "sessions" / "task-demo" / "events.jsonl"
        events = read_jsonl(path)
        assert events[-1]["mode"] == "task-retrospective"
        assert events[-1]["type"] == "correction"
        assert "other file" in events[-1]["text"]


def test_no_write_mode_silences_canonical_write():
    proc = run_cmd([
        sys.executable, str(HOOK), "--root", str(REPO_ROOT), "--host", "claude", "--event", "UserPromptSubmit", "--debug"
    ], input_obj={"session_id": "s4", "prompt": "hello", "cwd": str(REPO_ROOT)}, env={"BRAINER_CHECK_NO_WRITE": "1"})
    assert json.loads(proc.stderr)["reason"] == "no_write"


def test_malformed_payload_exits_zero_for_host_safety():
    proc = subprocess.run(
        [sys.executable, str(HOOK), "--host", "claude", "--event", "UserPromptSubmit", "--debug"],
        input="{bad json",
        text=True,
        capture_output=True,
    )
    assert proc.returncode == 0
    assert "error" in proc.stderr  # --debug diagnostics go to stderr (stdout is the host channel)


def main() -> int:
    failures = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"PASS {name}")
            except Exception as exc:
                failures += 1
                print(f"FAIL {name}: {exc}", file=sys.stderr)
    if failures:
        print(f"test_hooks.py: {failures} failure(s)", file=sys.stderr)
        return 1
    print("test_hooks.py: all PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
