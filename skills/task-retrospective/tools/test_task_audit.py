#!/usr/bin/env python3
"""Plain-python tests for task_audit.py."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
TOOL = HERE / "task_audit.py"
REPO_ROOT = HERE.parents[2]


def run_cli(args, root=None, env=None, expect=0):
    cmd = [sys.executable, str(TOOL)]
    if root is not None:
        cmd += ["--root", str(root)]
    cmd += list(args)
    merged_env = os.environ.copy()
    merged_env["PYTHONDONTWRITEBYTECODE"] = "1"
    if env:
        merged_env.update(env)
    proc = subprocess.run(cmd, text=True, capture_output=True, env=merged_env)
    assert proc.returncode == expect, (cmd, proc.returncode, proc.stdout, proc.stderr)
    return proc


def load_json(stdout):
    return json.loads(stdout)


def read_jsonl(path):
    return [json.loads(line) for line in Path(path).read_text(encoding="utf-8").splitlines() if line]


def test_lifecycle_start_note_status_finish_report():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        start = run_cli([
            "start",
            "--task", "Fit artwork to dieline",
            "--repeat-trigger", "when adapting artwork to a dieline",
            "--goal", "align art to cut lines",
            "--definition-of-done", "all cut lines visible",
            "--constraint", "do not cover holes",
            "--task-id", "demo-task",
        ], root=root)
        started = load_json(start.stdout)
        assert started["active"] is True
        assert started["task_id"] == "demo-task"
        current = root / ".brainer" / "task-retrospective" / "current.json"
        assert current.exists()

        run_cli([
            "note", "--type", "correction",
            "--text", "User said the cut line was still misaligned.",
            "--implication", "Overlay template before moving artwork.",
        ], root=root)
        run_cli([
            "note", "--type", "evidence",
            "--text", "Overlay screenshot shows alignment is now correct.",
            "--evidence-ref", "screenshot:alignment.png",
        ], root=root)

        status = load_json(run_cli(["status"], root=root).stdout)
        assert status["active"] is True
        assert status["event_count"] == 3

        finish = load_json(run_cli(["finish", "--report", "--evidence-quality", "high"], root=root).stdout)
        assert finish["finished"] is True
        assert finish["active"] is False
        assert finish["event_count"] == 4
        assert finish["report_written"] is True
        assert not current.exists()

        report = Path(finish["report_path"])
        text = report.read_text(encoding="utf-8")
        assert "# Task-retrospective report" in text
        assert "Fit artwork to dieline" in text
        assert "User said the cut line was still misaligned." in text
        assert "Overlay screenshot shows alignment is now correct." in text
        assert "None written by `task_audit.py`" in text

        events = read_jsonl(root / ".brainer" / "task-retrospective" / "sessions" / "demo-task" / "events.jsonl")
        assert [event["type"] for event in events] == ["start", "correction", "evidence", "finish"]


def test_note_without_armed_session_fails_cleanly():
    with tempfile.TemporaryDirectory() as tmp:
        proc = run_cli(["note", "--type", "correction", "--text", "No active session"], root=tmp, expect=2)
        assert "not armed" in proc.stderr
        assert "Traceback" not in proc.stderr


def test_malformed_current_status_fails_without_traceback():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        current = root / ".brainer" / "task-retrospective" / "current.json"
        current.parent.mkdir(parents=True)
        current.write_text("{not json", encoding="utf-8")
        proc = run_cli(["status"], root=root, expect=2)
        assert "malformed" in proc.stderr
        assert "Traceback" not in proc.stderr


def test_no_write_refuses_canonical_repo_root():
    proc = run_cli([
        "start", "--task", "Blocked", "--repeat-trigger", "never", "--task-id", "blocked-test"
    ], root=REPO_ROOT, env={"BRAINER_CHECK_NO_WRITE": "1"}, expect=2)
    assert "BRAINER_CHECK_NO_WRITE=1" in proc.stderr
    assert "refusing to write" in proc.stderr


def test_no_write_allows_isolated_temp_fixture():
    with tempfile.TemporaryDirectory() as tmp:
        proc = run_cli([
            "start", "--task", "Temp fixture", "--repeat-trigger", "fixture", "--task-id", "fixture"
        ], root=tmp, env={"BRAINER_CHECK_NO_WRITE": "1"})
        data = load_json(proc.stdout)
        assert data["active"] is True
        assert Path(data["events_path"]).exists()


def test_secret_like_values_are_redacted():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        run_cli([
            "start", "--task", "Redact", "--repeat-trigger", "secret-shaped text", "--task-id", "redact"
        ], root=root)
        proc = run_cli([
            "note", "--type", "evidence", "--text", "token=abc123 password: hunter2 Authorization: Bearer xyz"
        ], root=root)
        data = load_json(proc.stdout)
        assert "abc123" not in json.dumps(data)
        assert "hunter2" not in json.dumps(data)
        assert "xyz" not in json.dumps(data)
        events = read_jsonl(root / ".brainer" / "task-retrospective" / "sessions" / "redact" / "events.jsonl")
        joined = json.dumps(events)
        assert "abc123" not in joined
        assert "hunter2" not in joined
        assert "xyz" not in joined
        assert "[REDACTED]" in joined


def test_after_the_fact_report_marks_reconstruction():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        run_cli([
            "start",
            "--task", "Reconstruct previous work",
            "--repeat-trigger", "when the user forgot to arm task audit",
            "--after-the-fact",
            "--task-id", "reconstruct",
        ], root=root)
        result = load_json(run_cli(["finish", "--report"], root=root).stdout)
        report = Path(result["report_path"]).read_text(encoding="utf-8")
        assert "retrospective reconstruction" in report
        assert result["evidence_quality"] == "low"


def main() -> int:
    failures = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"PASS {name}")
            except Exception as exc:  # pragma: no cover - standalone runner
                failures += 1
                print(f"FAIL {name}: {exc}", file=sys.stderr)
    if failures:
        print(f"test_task_audit.py: {failures} failure(s)", file=sys.stderr)
        return 1
    print("test_task_audit.py: all PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
