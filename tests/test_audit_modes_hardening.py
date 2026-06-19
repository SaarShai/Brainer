import importlib.util
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BRAUDIT = ROOT / "skills" / "brainer-audit" / "tools"
TRETRO = ROOT / "skills" / "task-retrospective" / "tools"


def run(cmd, *, expect=0, cwd=ROOT, env=None, input_text=None):
    merged = os.environ.copy()
    merged["PYTHONDONTWRITEBYTECODE"] = "1"
    if env:
        merged.update(env)
    proc = subprocess.run(cmd, cwd=cwd, text=True, input=input_text, capture_output=True, env=merged)
    assert proc.returncode == expect, (cmd, proc.returncode, proc.stdout, proc.stderr)
    return proc


def load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def write_jsonl(path: Path, events):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for event in events:
            fh.write(json.dumps(event, sort_keys=True) + "\n")


def base_event(**kw):
    event = {
        "schema_version": 1,
        "mode": "brainer-audit",
        "session_id": "golden",
        "turn_id": "",
        "host": "codex",
        "project_path": "/repo",
        "event": "user_prompt",
        "timestamp": "2026-06-19T00:00:00Z",
        "content_summary": "hello",
    }
    event.update(kw)
    return event


def inspect_json(events_path: Path, *, expect=0):
    proc = run([sys.executable, str(BRAUDIT / "inspect_session.py"), "--events", str(events_path), "--format", "json"], expect=expect)
    return json.loads(proc.stdout)


def inspect_markdown(events_path: Path, *, expect=0):
    return run([sys.executable, str(BRAUDIT / "inspect_session.py"), "--events", str(events_path), "--format", "markdown"], expect=expect).stdout


def test_golden_clean_report_is_stable():
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "events.jsonl"
        write_jsonl(path, [base_event(content_summary="quiet hello")])
        report = inspect_json(path)
        assert report == {
            "schema_version": 1,
            "mode": "brainer-audit",
            "summary": {
                "audit_mode": "offline",
                "schema_version": 1,
                "host": "codex",
                "project": "/repo",
                "session": "golden",
                "event_count": 1,
                "event_types": {"user_prompt": 1},
                "evidence_quality": "medium",
            },
            "finding_counts": {},
            "findings": [],
        }
        md = inspect_markdown(path)
        assert md.startswith("# Brainer audit report\n")
        assert "1. No candidate Brainer improvement from this fixture." in md
        assert "events.jsonl:1: user_prompt" in md


def test_golden_detector_set_for_compound_fixture():
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "events.jsonl"
        claim = "Checks " + "passed and the work is " + "done."
        write_events = [
            base_event(event="user_prompt", content_summary="Run checks and update docs", requirements=["run checks", "update docs"]),
            base_event(event="assistant_message", content_summary=claim, completed_requirements=["run checks"]),
            base_event(event="tool_result", command="make noisy", output_bytes=50000, line_count=400, content_summary="progress progress"),
            base_event(event="tool_result", command="python broken.py", exit_code=1, error_signature="same-error"),
            base_event(event="tool_result", command="python broken.py", exit_code=1, error_signature="same-error"),
            base_event(event="file_change", path="wiki/L2_facts/new.md", content_summary="durable page"),
        ]
        write_jsonl(path, write_events)
        report = inspect_json(path)
        got = {finding["detector"] for finding in report["findings"]}
        assert got == {
            "dropped_requirement",
            "missed_output_filter",
            "repeated_tool_error_loop",
            "skill_trigger_opportunity",
            "unverified_completion_claim",
            "write_gate_bypass",
        }


def test_boundary_error_fixture_is_stable():
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "events.jsonl"
        phrase = "task-retrospective updated Brainer " + "skill obedience docs"
        write_jsonl(path, [
            base_event(event="file_change", mode="task-retrospective", path="skills/wiki-memory/SKILL.md", content_summary=phrase),
        ])
        report = inspect_json(path, expect=1)
        assert report["finding_counts"] == {"error": 1, "warn": 1}
        assert {f["detector"] for f in report["findings"]} == {
            "task_retrospective_boundary_violation",
            "write_gate_bypass",
        }


def test_antigravity_lower_fidelity_report_marker_is_stable():
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "events.jsonl"
        write_jsonl(path, [base_event(
            host="antigravity",
            event="session_end",
            collector="antigravity_sidecar",
            evidence_fidelity="lower-sidecar",
            content_summary="No artifact directories found; git-only sidecar evidence.",
        )])
        md = inspect_markdown(path)
        assert "Host: antigravity" in md
        assert "events.jsonl:1: session_end [lower-sidecar]" in md


def test_no_write_regression_across_collectors():
    env = {"BRAINER_CHECK_NO_WRITE": "1"}
    blocked_event_path = ROOT / ".brainer" / "brainer-audit" / "hardening-events.jsonl"
    proc = run([
        sys.executable, str(TRETRO / "task_audit.py"), "--root", str(ROOT), "start",
        "--task", "blocked", "--repeat-trigger", "blocked", "--task-id", "hardening-blocked"
    ], expect=2, env=env)
    assert "BRAINER_CHECK_NO_WRITE=1" in proc.stderr

    hook_payload = json.dumps({"session_id": "s", "prompt": "hello", "cwd": str(ROOT)})
    proc = run([
        sys.executable, str(BRAUDIT / "hook.py"), "--root", str(ROOT), "--host", "claude", "--event", "UserPromptSubmit", "--debug"
    ], input_text=hook_payload, env=env)
    assert json.loads(proc.stdout)["reason"] == "no_write"

    proc = run([
        sys.executable, str(BRAUDIT / "antigravity_sidecar.py"), "--root", str(ROOT), "snapshot", "--events", str(blocked_event_path)
    ], expect=2, env=env)
    assert "BRAINER_CHECK_NO_WRITE=1" in proc.stderr
    assert not blocked_event_path.exists()


def test_report_only_inspection_does_not_mutate_files():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        path = root / "events.jsonl"
        write_jsonl(path, [base_event(project_path=str(root))])
        before = {p.relative_to(root): p.read_bytes() for p in root.rglob("*") if p.is_file()}
        inspect_markdown(path)
        inspect_json(path)
        after = {p.relative_to(root): p.read_bytes() for p in root.rglob("*") if p.is_file()}
        assert after == before


def test_redaction_consistency_across_collectors():
    task_audit = load_module(TRETRO / "task_audit.py", "task_audit_hardening")
    ingest = load_module(BRAUDIT / "ingest_event.py", "ingest_event_hardening")
    normalize = load_module(BRAUDIT / "normalize.py", "normalize_hardening")
    watch = load_module(BRAUDIT / "watch_artifacts.py", "watch_artifacts_hardening")
    sensitive = "tok" + "en=abc123 " + "sec" + "ret: zzz " + "Authorization: Bearer qqq"
    for redact in [task_audit.redact, ingest.redact, normalize.redact, watch.redact]:
        out = redact(sensitive)
        assert "abc123" not in out
        assert "zzz" not in out
        assert "qqq" not in out
        assert "[REDACTED]" in out
