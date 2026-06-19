#!/usr/bin/env python3
"""Path-confinement tests for shared audit_paths helper + tool integration.

Covers the four escape vectors the review flagged: ``../`` traversal, an
absolute path outside the root, a symlink whose target is outside the root, and
a tampered marker pointing at a canonical skill file. Both the shared helper and
the end-to-end tool behavior (tampered marker is refused, not followed) are
exercised.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
SHARED = HERE.parent.parent / "_shared"  # skills/_shared
if str(SHARED) not in sys.path:
    sys.path.insert(0, str(SHARED))

from audit_paths import PathConfinementError, is_within, safe_resolve_under  # noqa: E402

AUDIT_SESSION = HERE / "audit_session.py"
SIDECAR = HERE / "antigravity_sidecar.py"
TASK_AUDIT = HERE.parents[1] / "task-retrospective" / "tools" / "task_audit.py"
REPO_ROOT = HERE.parents[2]
CANONICAL_SKILL_FILE = HERE / "hook.py"  # a real canonical file a tampered marker might target


def run_cmd(cmd, *, input_obj=None, expect=0, env=None):
    merged = os.environ.copy()
    merged["PYTHONDONTWRITEBYTECODE"] = "1"
    if env:
        merged.update(env)
    stdin = json.dumps(input_obj) if input_obj is not None else None
    proc = subprocess.run(cmd, input=stdin, text=True, capture_output=True, env=merged)
    assert proc.returncode == expect, (cmd, proc.returncode, proc.stdout, proc.stderr)
    return proc


# ---------------------------------------------------------------------------
# Shared helper unit tests
# ---------------------------------------------------------------------------

def test_helper_accepts_path_inside_base():
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp) / "store"
        base.mkdir()
        good = safe_resolve_under(base, "sessions/x/events.jsonl")
        assert good == (base / "sessions" / "x" / "events.jsonl").resolve()
        assert is_within(base, good)


def test_helper_rejects_dotdot_traversal():
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp) / "store"
        base.mkdir()
        try:
            safe_resolve_under(base, "../../etc/passwd")
            raise AssertionError("traversal not rejected")
        except PathConfinementError:
            pass


def test_helper_rejects_absolute_outside():
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp) / "store"
        base.mkdir()
        try:
            safe_resolve_under(base, "/etc/passwd")
            raise AssertionError("absolute escape not rejected")
        except PathConfinementError:
            pass


def test_helper_rejects_symlink_escape():
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp) / "store"
        base.mkdir()
        outside = Path(tmp) / "outside"
        outside.mkdir()
        link = base / "link"
        link.symlink_to(outside, target_is_directory=True)
        # A path that lexically looks inside base but resolves through the symlink
        # to a location outside base must be rejected.
        try:
            safe_resolve_under(base, "link/escaped.jsonl")
            raise AssertionError("symlink escape not rejected")
        except PathConfinementError:
            pass


def test_helper_rejects_empty():
    with tempfile.TemporaryDirectory() as tmp:
        try:
            safe_resolve_under(Path(tmp), "")
            raise AssertionError("empty path not rejected")
        except PathConfinementError:
            pass


# ---------------------------------------------------------------------------
# End-to-end: a tampered marker must NOT redirect a write outside the store
# ---------------------------------------------------------------------------

def _write_marker(marker: Path, events_path: str, extra=None):
    marker.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": 1,
        "mode": marker.parent.name,
        "status": "active",
        "session_id": "tampered",
        "task_id": "tampered",
        "task": "t",
        "repeat_trigger": "r",
        "title": "t",
        "events_path": events_path,
        "report_path": str(marker.parent / "sessions" / "x" / "report.md"),
        "json_report_path": str(marker.parent / "sessions" / "x" / "report.json"),
        "project_path": str(marker.parents[1]),
    }
    if extra:
        payload.update(extra)
    marker.write_text(json.dumps(payload), encoding="utf-8")


def test_audit_session_finish_refuses_marker_pointing_at_canonical_file():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        marker = root / ".brainer" / "brainer-audit" / "current.json"
        _write_marker(marker, str(CANONICAL_SKILL_FILE))
        before = CANONICAL_SKILL_FILE.read_text(encoding="utf-8")
        proc = run_cmd(
            [sys.executable, str(AUDIT_SESSION), "--root", str(root), "finish", "--report"],
            expect=2,
        )
        assert "escapes audit store" in proc.stderr
        assert CANONICAL_SKILL_FILE.read_text(encoding="utf-8") == before  # untouched


def test_audit_session_status_refuses_traversal_marker():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        marker = root / ".brainer" / "brainer-audit" / "current.json"
        _write_marker(marker, "../../../../../../tmp/evil.jsonl")
        proc = run_cmd([sys.executable, str(AUDIT_SESSION), "--root", str(root), "status"], expect=2)
        assert "escapes audit store" in proc.stderr


def test_sidecar_refuses_marker_pointing_outside_store():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        marker = root / ".brainer" / "brainer-audit" / "current.json"
        evil = root / "evil-outside-store.jsonl"
        _write_marker(marker, str(evil))
        proc = run_cmd([sys.executable, str(SIDECAR), "--root", str(root), "snapshot"], expect=2)
        assert "escapes audit store" in proc.stderr
        assert not evil.exists()


def test_sidecar_refuses_explicit_events_outside_root():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        outside = Path(tmp + "-sibling-target.jsonl")
        proc = run_cmd(
            [sys.executable, str(SIDECAR), "--root", str(root), "snapshot", "--events", str(outside)],
            expect=2,
        )
        assert "escapes project root" in proc.stderr
        assert not outside.exists()


def test_task_audit_finish_refuses_marker_pointing_at_canonical_file():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        marker = root / ".brainer" / "task-retrospective" / "current.json"
        _write_marker(marker, str(CANONICAL_SKILL_FILE))
        before = CANONICAL_SKILL_FILE.read_text(encoding="utf-8")
        proc = run_cmd(
            [sys.executable, str(TASK_AUDIT), "--root", str(root), "finish", "--report"],
            expect=2,
        )
        assert "escapes task-retrospective store" in proc.stderr
        assert CANONICAL_SKILL_FILE.read_text(encoding="utf-8") == before


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
        print(f"test_path_confinement.py: {failures} failure(s)", file=sys.stderr)
        return 1
    print("test_path_confinement.py: all PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
