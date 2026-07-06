#!/usr/bin/env python3
"""Tests for orchestration_trace.py — plain-python (no pytest dep), runnable
standalone. Shape mirrors test_model_roster.py: a list of test_* functions, a
main() that runs them and returns the failure count (exit 0 == all pass).
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import orchestration_trace as ot  # noqa: E402


def test_record_lane_event_appends_one_json_line():
    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / "lanes.jsonl"
        ok = ot.record_lane_event(str(path), {"role": "verifier", "lane": "gpt", "ok": True})
        rows = path.read_text(encoding="utf-8").splitlines()
        return ok is True and len(rows) == 1 and json.loads(rows[0])["lane"] == "gpt"


def test_record_lane_event_creates_parent_dirs():
    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / "nested" / "deeper" / "lanes.jsonl"
        ok = ot.record_lane_event(str(path), {"role": "advisor", "lane": "glm", "ok": False})
        return ok is True and path.exists()


def test_record_lane_event_appends_not_overwrites():
    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / "lanes.jsonl"
        ot.record_lane_event(str(path), {"lane": "gpt", "ok": True})
        ot.record_lane_event(str(path), {"lane": "gemini", "ok": True})
        rows = path.read_text(encoding="utf-8").splitlines()
        return len(rows) == 2 and json.loads(rows[0])["lane"] == "gpt" and json.loads(rows[1])["lane"] == "gemini"


def test_record_lane_event_carries_telemetry_fields():
    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / "lanes.jsonl"
        event = {"role": "verifier", "lane": "gpt", "vendor": "GPT via OpenRouter", "ok": True,
                 "usage": {"prompt_tokens": 12, "completion_tokens": 34}, "latency_ms": 456.7,
                 "served_model": "openai/gpt-5.4-mini"}
        ot.record_lane_event(str(path), event)
        row = json.loads(path.read_text(encoding="utf-8").splitlines()[0])
        return (row["usage"] == {"prompt_tokens": 12, "completion_tokens": 34}
                and row["latency_ms"] == 456.7 and row["served_model"] == "openai/gpt-5.4-mini")


def test_record_lane_event_never_raises_on_unwritable_path():
    # Point at a path whose parent cannot be created (a FILE in the way, not a
    # dir) — mkdir(parents=True) must fail, and record_lane_event must swallow
    # it and return False rather than propagate.
    with tempfile.TemporaryDirectory() as td:
        blocker = Path(td) / "not_a_dir"
        blocker.write_text("i am a file, not a directory", encoding="utf-8")
        bad_path = blocker / "sub" / "lanes.jsonl"
        ok = ot.record_lane_event(str(bad_path), {"lane": "gpt", "ok": True})
        return ok is False


def test_record_lane_event_default_path_is_dot_brainer_trace():
    return ot.DEFAULT_TRACE_PATH.parts[-3:] == (".brainer", "trace", "lanes.jsonl")


def test_record_lane_event_redacts_task_digest():
    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / "lanes.jsonl"
        ot.record_lane_event(str(path), {"lane": "gpt", "ok": True,
                                         "task_digest": "key=sk-proj-abcdef0123456789abcdef"})
        row = json.loads(path.read_text(encoding="utf-8").splitlines()[0])
        return "sk-proj-abcdef" not in (row["task_digest"] or "") and "[REDACTED]" in row["task_digest"]


def test_record_lane_event_task_digest_none_when_redactor_missing():
    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / "lanes.jsonl"
        orig = ot._redact_secrets
        ot._redact_secrets = None
        try:
            ot.record_lane_event(str(path), {"lane": "gpt", "ok": True, "task_digest": "some raw task text"})
        finally:
            ot._redact_secrets = orig
        row = json.loads(path.read_text(encoding="utf-8").splitlines()[0])
        return row["task_digest"] is None


def test_record_lane_event_none_path_uses_default():
    # Never actually write to the real repo root from a test: redirect the
    # module-level default and confirm None resolves to *some* default path,
    # not a crash, without touching the real .brainer/trace.
    orig_default = ot.DEFAULT_TRACE_PATH
    with tempfile.TemporaryDirectory() as td:
        ot.DEFAULT_TRACE_PATH = Path(td) / ".brainer" / "trace" / "lanes.jsonl"
        try:
            ok = ot.record_lane_event(None, {"lane": "gpt", "ok": True})
            return ok is True and ot.DEFAULT_TRACE_PATH.exists()
        finally:
            ot.DEFAULT_TRACE_PATH = orig_default


TESTS = [v for k, v in sorted(globals().items()) if k.startswith("test_")]


def main() -> int:
    failures = 0
    for t in TESTS:
        try:
            ok = t()
        except Exception as e:  # noqa: BLE001
            ok = False
            print(f"ERROR {t.__name__}: {e}")
        if ok:
            print(f"PASS {t.__name__}")
        else:
            failures += 1
            print(f"FAIL {t.__name__}")
    total = len(TESTS)
    print(f"\n{total - failures}/{total} passed")
    return failures


if __name__ == "__main__":
    sys.exit(main())
