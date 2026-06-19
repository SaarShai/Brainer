#!/usr/bin/env python3
"""Golden redaction fixtures for the shared audit_redact module + tool wiring.

Feeds a broad secret corpus through:
  - the shared redact()/redact_obj() helpers,
  - normalize.normalize_event (hook path),
  - ingest_event.py (offline path),
  - the full task_audit.py lifecycle (start -> note -> status -> finish -> report),

and asserts NO raw secret string appears in any JSONL line, marker file, status
stdout, or rendered report.
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
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import audit_redact  # noqa: E402
import normalize  # noqa: E402

INGEST = HERE / "ingest_event.py"
TASK_AUDIT = HERE.parents[1] / "task-retrospective" / "tools" / "task_audit.py"

# (label, raw secret string, distinctive substring that must NOT survive)
SECRETS = [
    ("openai", "sk-proj-ABCDEFGH1234567890abcdEFGHijkl", "ABCDEFGH1234567890abcdEFGHijkl"),
    ("openai_classic", "sk-ABCDEFGH1234567890abcdEFGH", "ABCDEFGH1234567890abcdEFGH"),
    ("ghp", "ghp_ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789", "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"),
    ("github_pat", "github_pat_11ABCDEF0_abcdefghij1234567890klmnop", "abcdefghij1234567890klmnop"),
    ("aws_id", "AKIAIOSFODNN7EXAMPLE", "AKIAIOSFODNN7EXAMPLE"),
    ("aws_secret", "aws_secret_access_key=wJalrXUtnFEMIK7MDENGbPxRfiCYEXAMPLEKEY", "wJalrXUtnFEMIK7MDENG"),
    ("jwt", "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJV", "SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJV"),
    ("bearer", "Authorization: Bearer abcdEFGHsecrettoken123456", "abcdEFGHsecrettoken123456"),
    ("env_pw", "DATABASE_PASSWORD=hunter2supersecret", "hunter2supersecret"),
    ("url_cred", "https://alice:s3cr3tPassw0rd@example.com/repo.git", "s3cr3tPassw0rd"),
    ("pem", "-----BEGIN RSA PRIVATE KEY-----\nMIIEowIBAAKCAQEAprivatekeydata\n-----END RSA PRIVATE KEY-----", "MIIEowIBAAKCAQEAprivatekeydata"),
    ("json_pk", '"private_key": "-----BEGIN PRIVATE KEY-----abcsecretkeymaterial-----END PRIVATE KEY-----"', "abcsecretkeymaterial"),
]
HOMEPATH = ("/Users/saarsecretname/proj/file", "saarsecretname")


def run_cmd(cmd, *, expect=0, env=None):
    merged = os.environ.copy()
    merged["PYTHONDONTWRITEBYTECODE"] = "1"
    if env:
        merged.update(env)
    proc = subprocess.run(cmd, text=True, capture_output=True, env=merged)
    assert proc.returncode == expect, (cmd, proc.returncode, proc.stdout, proc.stderr)
    return proc


def _assert_clean(blob: str, where: str):
    for label, _raw, leak in SECRETS:
        assert leak not in blob, f"{where}: leaked {label} ({leak!r})"
    assert HOMEPATH[1] not in blob, f"{where}: leaked local username"


def test_shared_helper_scrubs_full_corpus():
    obj = {label: raw for label, raw, _ in SECRETS}
    obj["homepath"] = HOMEPATH[0]
    obj["nested"] = {"list": [raw for _, raw, _ in SECRETS]}
    _assert_clean(json.dumps(audit_redact.redact_obj(obj)), "redact_obj")


def test_normalize_event_redacts_every_field():
    blob = " ".join(raw for _, raw, _ in SECRETS) + " " + HOMEPATH[0]
    event = normalize.normalize_event(
        {"prompt": blob, "command": blob, "transcript_path": HOMEPATH[0], "cwd": HOMEPATH[0]},
        host="claude",
        event_name="UserPromptSubmit",
    )
    _assert_clean(json.dumps(event), "normalize_event")
    retro = normalize.normalize_task_retro_event({"content_summary": blob, "host": "claude"})
    _assert_clean(json.dumps(retro), "normalize_task_retro_event")


def test_ingest_event_jsonl_has_no_secret():
    with tempfile.TemporaryDirectory() as tmp:
        events = Path(tmp) / "events.jsonl"
        blob = " ".join(raw for _, raw, _ in SECRETS)
        proc = run_cmd([
            sys.executable, str(INGEST),
            "--events", str(events),
            "--event", "user_prompt",
            "--host", "codex",
            "--content-summary", blob,
            "--command", blob,
            "--field", f"secret={json.dumps(blob)}",
        ])
        _assert_clean(proc.stdout, "ingest stdout")
        _assert_clean(events.read_text(encoding="utf-8"), "ingest jsonl")


def test_task_audit_lifecycle_redacts_all_surfaces():
    blob = " ".join(raw for _, raw, _ in SECRETS)
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        # start: pack secrets into EVERY metadata field (title/task, goal,
        # constraint, repeat-trigger, definition-of-done).
        start = run_cmd([
            sys.executable, str(TASK_AUDIT), "--root", str(root), "start",
            "--task", f"task {blob}",
            "--goal", f"goal {blob}",
            "--repeat-trigger", f"trigger {blob}",
            "--definition-of-done", f"dod {blob}",
            "--constraint", f"constraint {blob}",
            "--task-id", "redact-fixture",
        ])
        _assert_clean(start.stdout, "task start stdout")

        note = run_cmd([
            sys.executable, str(TASK_AUDIT), "--root", str(root), "note",
            "--type", "evidence", "--text", f"evidence {blob}",
            "--implication", f"impl {blob}", "--evidence-ref", f"ref {blob}",
        ])
        _assert_clean(note.stdout, "task note stdout")

        status = run_cmd([sys.executable, str(TASK_AUDIT), "--root", str(root), "status"])
        _assert_clean(status.stdout, "task status stdout")

        finish = run_cmd([
            sys.executable, str(TASK_AUDIT), "--root", str(root), "finish", "--report",
        ])
        _assert_clean(finish.stdout, "task finish stdout")

        store = root / ".brainer" / "task-retrospective"
        sdir = store / "sessions" / "redact-fixture"
        # The marker is unlinked on finish; check the events JSONL + report.
        _assert_clean((sdir / "events.jsonl").read_text(encoding="utf-8"), "task events.jsonl")
        _assert_clean((sdir / "report.md").read_text(encoding="utf-8"), "task report.md")
        # Sweep every file left under the store for good measure.
        for path in store.rglob("*"):
            if path.is_file():
                _assert_clean(path.read_text(encoding="utf-8", errors="replace"), f"store file {path.name}")


def test_task_audit_marker_redacted_while_active():
    """The on-disk marker must be scrubbed even while the session is still active."""
    blob = " ".join(raw for _, raw, _ in SECRETS)
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        run_cmd([
            sys.executable, str(TASK_AUDIT), "--root", str(root), "start",
            "--task", f"task {blob}", "--repeat-trigger", f"trigger {blob}",
            "--goal", f"goal {blob}", "--task-id", "active-marker",
        ])
        marker = root / ".brainer" / "task-retrospective" / "current.json"
        _assert_clean(marker.read_text(encoding="utf-8"), "active marker")


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
        print(f"test_redaction.py: {failures} failure(s)", file=sys.stderr)
        return 1
    print("test_redaction.py: all PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
