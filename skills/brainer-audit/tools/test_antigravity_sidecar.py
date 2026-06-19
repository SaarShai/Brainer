#!/usr/bin/env python3
"""Plain-python tests for Antigravity sidecar support."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
SIDECAR = HERE / "antigravity_sidecar.py"
AUDIT_SESSION = HERE / "audit_session.py"
INSPECT = HERE / "inspect_session.py"
REPO_ROOT = HERE.parents[2]


def run_cmd(cmd, *, expect=0, env=None):
    merged = os.environ.copy()
    merged["PYTHONDONTWRITEBYTECODE"] = "1"
    if env:
        merged.update(env)
    proc = subprocess.run(cmd, text=True, capture_output=True, env=merged)
    assert proc.returncode == expect, (cmd, proc.returncode, proc.stdout, proc.stderr)
    return proc


def run_git(root: Path, args):
    return run_cmd(["git", *args], expect=0)


def read_jsonl(path: Path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def init_git_with_diff(root: Path):
    run_cmd(["git", "init", str(root)])
    tracked = root / "tracked.txt"
    tracked.write_text("old\n", encoding="utf-8")
    run_cmd(["git", "-C", str(root), "add", "tracked.txt"])
    run_cmd([
        "git", "-C", str(root), "-c", "user.email=test@example.com", "-c", "user.name=Test", "commit", "-m", "init"
    ])
    tracked.write_text("new\n", encoding="utf-8")


def test_status_missing_artifact_dir_is_graceful():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        proc = run_cmd([sys.executable, str(SIDECAR), "--root", str(root), "--artifact-dir", "missing", "status"])
        data = json.loads(proc.stdout)
        assert data["host"] == "antigravity"
        assert data["native_hooks"] == "unverified"
        assert data["artifact_dirs"] == []
        assert data["evidence_fidelity"] == "lower-sidecar"


def test_snapshot_records_git_diff_and_artifact():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        init_git_with_diff(root)
        artifacts = root / "ag-artifacts"
        artifacts.mkdir()
        (artifacts / "plan.md").write_text("Plan artifact\n", encoding="utf-8")
        events = root / "events.jsonl"
        proc = run_cmd([
            sys.executable, str(SIDECAR), "--root", str(root), "--artifact-dir", str(artifacts),
            "snapshot", "--events", str(events), "--session-id", "ag", "--include-content"
        ])
        data = json.loads(proc.stdout)
        assert data["events_written"] >= 2
        rows = read_jsonl(events)
        assert {row["host"] for row in rows} == {"antigravity"}
        assert {row["evidence_fidelity"] for row in rows} == {"lower-sidecar"}
        assert any(row.get("event") == "git_snapshot" for row in rows)
        assert any(row.get("path", "").endswith("tracked.txt") for row in rows)
        assert any("Plan artifact" in row.get("content_summary", "") for row in rows)


def test_snapshot_with_active_marker_defaults_events_path():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        run_cmd([sys.executable, str(AUDIT_SESSION), "--root", str(root), "start", "--title", "ag", "--session-id", "ag"])
        run_cmd([sys.executable, str(SIDECAR), "--root", str(root), "snapshot", "--session-id", "ag"])
        path = root / ".brainer" / "brainer-audit" / "sessions" / "ag" / "events.jsonl"
        rows = read_jsonl(path)
        assert rows
        assert rows[0]["collector"] == "antigravity_sidecar"


def test_snapshot_without_events_or_marker_fails_cleanly():
    with tempfile.TemporaryDirectory() as tmp:
        proc = run_cmd([sys.executable, str(SIDECAR), "--root", tmp, "snapshot"], expect=2)
        assert "no --events path" in proc.stderr
        assert "Traceback" not in proc.stderr


def test_no_write_refuses_canonical_events_path():
    target = REPO_ROOT / ".brainer" / "brainer-audit" / "antigravity-events.jsonl"
    proc = run_cmd([
        sys.executable, str(SIDECAR), "--root", str(REPO_ROOT), "snapshot", "--events", str(target)
    ], env={"BRAINER_CHECK_NO_WRITE": "1"}, expect=2)
    assert "BRAINER_CHECK_NO_WRITE=1" in proc.stderr


def test_report_marks_antigravity_lower_fidelity():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        events = root / "events.jsonl"
        run_cmd([sys.executable, str(SIDECAR), "--root", str(root), "snapshot", "--events", str(events)])
        proc = run_cmd([sys.executable, str(INSPECT), "--events", str(events), "--format", "markdown"])
        assert "antigravity" in proc.stdout
        assert "lower-sidecar" in proc.stdout


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
        print(f"test_antigravity_sidecar.py: {failures} failure(s)", file=sys.stderr)
        return 1
    print("test_antigravity_sidecar.py: all PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
