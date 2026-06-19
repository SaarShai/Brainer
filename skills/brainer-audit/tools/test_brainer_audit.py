#!/usr/bin/env python3
"""Plain-python tests for the brainer-audit offline MVP."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
INGEST = HERE / "ingest_event.py"
INSPECT = HERE / "inspect_session.py"


def run_cmd(cmd, expect=0, extra_env=None):
    env = os.environ.copy()
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    if extra_env:
        env.update(extra_env)
    proc = subprocess.run(cmd, text=True, capture_output=True, env=env)
    assert proc.returncode == expect, (cmd, proc.returncode, proc.stdout, proc.stderr)
    return proc


def write_events(path: Path, events):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for event in events:
            base = {
                "schema_version": 1,
                "mode": "brainer-audit",
                "session_id": "s1",
                "host": "codex",
                "project_path": "/Users/za/Documents/Brainer",
                "timestamp": "2026-06-18T00:00:00Z",
            }
            base.update(event)
            fh.write(json.dumps(base, sort_keys=True) + "\n")


def audit_json(path: Path, expect=0):
    proc = run_cmd([sys.executable, str(INSPECT), "--events", str(path), "--format", "json"], expect=expect)
    return json.loads(proc.stdout)


def names(report):
    return {f["detector"] for f in report["findings"]}


def test_ingest_event_writes_schema_and_extra_fields():
    with tempfile.TemporaryDirectory() as tmp:
        events = Path(tmp) / "events.jsonl"
        proc = run_cmd([
            sys.executable, str(INGEST),
            "--events", str(events),
            "--event", "user_prompt",
            "--host", "codex",
            "--content-summary", "please record the decision",
            "--field", 'requirements=["record decision"]',
        ])
        payload = json.loads(proc.stdout)
        assert payload["ok"] is True
        assert payload["event"]["schema_version"] == 1
        assert payload["event"]["mode"] == "brainer-audit"
        stored = json.loads(events.read_text(encoding="utf-8"))
        assert stored["requirements"] == ["record decision"]


def test_completion_and_requirement_findings():
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "events.jsonl"
        claim = "Checks " + "passed and the work is " + "done."
        write_events(path, [
            {"event": "user_prompt", "content_summary": "Run tests and update docs", "requirements": ["run tests", "update docs"]},
            {"event": "assistant_message", "content_summary": claim, "completed_requirements": ["run tests"]},
        ])
        report = audit_json(path)
        got = names(report)
        assert "unverified_completion_claim" in got
        assert "dropped_requirement" in got


def test_recent_verification_suppresses_completion_claim():
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "events.jsonl"
        claim = "Checks " + "passed and this is " + "ready."
        write_events(path, [
            {"event": "tool_call", "command": "pytest -q"},
            {"event": "tool_result", "command": "pytest -q", "exit_code": 0, "content_summary": "2 passed"},
            {"event": "assistant_message", "content_summary": claim},
        ])
        assert "unverified_completion_claim" not in names(audit_json(path))


def test_output_filter_and_error_loop_findings():
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "events.jsonl"
        write_events(path, [
            {"event": "tool_result", "command": "make noisy", "output_bytes": 50000, "line_count": 400, "content_summary": "progress progress"},
            {"event": "tool_result", "command": "python broken.py", "exit_code": 1, "error_signature": "same-error"},
            {"event": "tool_result", "command": "python broken.py", "exit_code": 1, "error_signature": "same-error"},
        ])
        got = names(audit_json(path))
        assert "missed_output_filter" in got
        assert "repeated_tool_error_loop" in got


def test_boundary_violation_is_error():
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "events.jsonl"
        phrase = "task-retrospective updated Brainer " + "skill obedience docs"
        write_events(path, [
            {"event": "file_change", "mode": "task-retrospective", "path": "skills/wiki-memory/SKILL.md", "content_summary": phrase},
        ])
        report = audit_json(path, expect=1)
        assert "task_retrospective_boundary_violation" in names(report)
        assert report["finding_counts"]["error"] == 1


def test_write_gate_bypass_and_suppression():
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "events.jsonl"
        write_events(path, [
            {"event": "file_change", "path": "wiki/L2_facts/new-fact.md", "content_summary": "new durable page"},
        ])
        assert "write_gate_bypass" in names(audit_json(path))

        gated = Path(tmp) / "gated.jsonl"
        write_events(gated, [
            {"event": "tool_call", "command": "python skills/write-gate/tools/write_gate.py gate --kind fact --file candidate.md"},
            {"event": "file_change", "path": "wiki/L2_facts/new-fact.md", "content_summary": "new durable page"},
        ])
        assert "write_gate_bypass" not in names(audit_json(gated))


def test_markdown_report_is_report_only():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        path = root / "events.jsonl"
        write_events(path, [{"event": "user_prompt", "content_summary": "hello"}])
        before = sorted(p.relative_to(root) for p in root.rglob("*"))
        proc = run_cmd([sys.executable, str(INSPECT), "--events", str(path), "--format", "markdown"])
        after = sorted(p.relative_to(root) for p in root.rglob("*"))
        assert before == after
        assert proc.stdout.startswith("# Brainer audit report")
        # audit_mode is now derived from the actual collection source; this
        # fixture is a hand-ingested offline event with no live/sidecar provenance.
        assert "Audit mode: offline" in proc.stdout
        assert "offline-report-only" not in proc.stdout


def test_audit_mode_derived_from_event_source():
    # offline (hand-ingested fixture, no live/sidecar provenance)
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "events.jsonl"
        write_events(path, [{"event": "user_prompt", "content_summary": "hi"}])
        assert audit_json(path)["summary"]["audit_mode"] == "offline"
    # live-hook (normalize.py sets hook_event_name)
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "events.jsonl"
        write_events(path, [{"event": "user_prompt", "hook_event_name": "UserPromptSubmit", "session_id": "hook"}])
        assert audit_json(path)["summary"]["audit_mode"] == "live-hook"
    # sidecar (collector marker)
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "events.jsonl"
        write_events(path, [{"event": "git_snapshot", "collector": "antigravity_sidecar", "evidence_fidelity": "lower-sidecar"}])
        assert audit_json(path)["summary"]["audit_mode"] == "sidecar"
    # mixed (offline + live-hook)
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "events.jsonl"
        write_events(path, [
            {"event": "user_prompt", "content_summary": "offline one"},
            {"event": "tool_call", "hook_event_name": "PreToolUse"},
        ])
        assert audit_json(path)["summary"]["audit_mode"] == "mixed"


def test_malformed_events_fail_cleanly():
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "events.jsonl"
        path.write_text("{bad json\n", encoding="utf-8")
        proc = run_cmd([sys.executable, str(INSPECT), "--events", str(path)], expect=2)
        assert "malformed" in proc.stderr
        assert "Traceback" not in proc.stderr


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
        print(f"test_brainer_audit.py: {failures} failure(s)", file=sys.stderr)
        return 1
    print("test_brainer_audit.py: all PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
