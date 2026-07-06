#!/usr/bin/env python3
"""Tests for activation_trace.py — plain-python (no pytest dep), runnable
standalone. Shape mirrors test_orchestration_trace.py: a list of test_*
functions, a main() that runs them and returns the failure count (exit 0 ==
all pass).
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import activation_trace as at  # noqa: E402


def test_record_activation_appends_one_json_line():
    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / "activations.jsonl"
        ok = at.record_activation(str(path), {"skill": "compliance-canary", "phase": "trigger_matched"})
        rows = path.read_text(encoding="utf-8").splitlines()
        return ok is True and len(rows) == 1 and json.loads(rows[0])["skill"] == "compliance-canary"


def test_record_activation_appends_not_overwrites():
    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / "activations.jsonl"
        at.record_activation(str(path), {"skill": "loop-engineering", "phase": "trigger_matched"})
        at.record_activation(str(path), {"skill": "loop-engineering", "phase": "body_loaded"})
        rows = path.read_text(encoding="utf-8").splitlines()
        return (len(rows) == 2 and json.loads(rows[0])["phase"] == "trigger_matched"
                and json.loads(rows[1])["phase"] == "body_loaded")


def test_record_activation_creates_parent_dirs():
    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / "nested" / "deeper" / "activations.jsonl"
        ok = at.record_activation(str(path), {"skill": "wiki-memory", "phase": "tool_run"})
        return ok is True and path.exists()


def test_record_activation_default_path_is_dot_brainer_trace():
    return at.DEFAULT_TRACE_PATH.parts[-3:] == (".brainer", "trace", "activations.jsonl")


def test_record_activation_source_defaults_to_live():
    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / "activations.jsonl"
        event = {"skill": "learn-skill", "phase": "outcome"}
        ok = at.record_activation(str(path), event)
        row = json.loads(path.read_text(encoding="utf-8").splitlines()[0])
        return ok is True and row["source"] == at.DEFAULT_SOURCE == "live" and "source" not in event


def test_record_activation_source_fixture_passes_through():
    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / "activations.jsonl"
        ok = at.record_activation(str(path), {"skill": "eval-gate", "phase": "tool_run", "source": "fixture"})
        row = json.loads(path.read_text(encoding="utf-8").splitlines()[0])
        return ok is True and row["source"] == "fixture"


def test_record_activation_never_raises_on_unwritable_path():
    # Point at a path whose parent cannot be created (a FILE in the way, not a
    # dir) — mkdir(parents=True) must fail, and record_activation must
    # swallow it and return False rather than propagate.
    with tempfile.TemporaryDirectory() as td:
        blocker = Path(td) / "not_a_dir"
        blocker.write_text("i am a file, not a directory", encoding="utf-8")
        bad_path = blocker / "sub" / "activations.jsonl"
        ok = at.record_activation(str(bad_path), {"skill": "x", "phase": "trigger_matched"})
        return ok is False


def test_record_activation_circular_ref_never_raises():
    # A circular reference is broken by the imported id-based `seen` set
    # (emits [CIRCULAR]) rather than making json.dumps raise — the event is
    # still written with other fields intact, and nothing propagates.
    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / "activations.jsonl"
        event: dict[str, Any] = {"skill": "team-lead", "phase": "outcome"}
        event["self"] = event
        ok = at.record_activation(str(path), event)
        raw = path.read_text(encoding="utf-8") if path.exists() else ""
        return ok is True and "[CIRCULAR]" in raw and '"skill": "team-lead"' in raw


def test_record_activation_bytes_field_decoded_not_dropped():
    # bytes are DECODED (not repr-ed) so a token inside keeps its exact
    # characters for the regex — inherited from the imported walk.
    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / "activations.jsonl"
        ok = at.record_activation(str(path), {"skill": "output-filter", "phase": "tool_run", "raw": b"hello"})
        rows = path.read_text(encoding="utf-8").splitlines()
        row = json.loads(rows[0]) if rows else {}
        return ok is True and len(rows) == 1 and row["raw"] == "hello"


def test_record_activation_str_raises_never_propagates():
    # __str__ raising is caught by the imported coercion guard → stored as a
    # placeholder, event still written, exception never propagates.
    class _Evil:
        def __str__(self):
            raise RuntimeError("str() itself blows up")

    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / "activations.jsonl"
        ok = at.record_activation(str(path), {"skill": "x", "phase": "outcome", "evil": _Evil()})
        raw = path.read_text(encoding="utf-8") if path.exists() else ""
        return ok is True and "[UNSERIALIZABLE]" in raw


def test_record_activation_drops_entirely_when_redactor_missing():
    # With no redactor available (the imported _coerce_and_redact/
    # _redact_secrets), there is no way to guarantee a clean line, so the
    # event must be dropped ENTIRELY (return False, nothing written) — the
    # exact fail-closed contract orchestration_trace.record_lane_event has.
    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / "activations.jsonl"
        orig_coerce = at._coerce_and_redact
        orig_redact = at._redact_secrets
        at._coerce_and_redact = None
        at._redact_secrets = None
        try:
            ok = at.record_activation(str(path), {"skill": "x", "phase": "trigger_matched", "note": "some raw text"})
        finally:
            at._coerce_and_redact = orig_coerce
            at._redact_secrets = orig_redact
        return ok is False and not path.exists()


def test_record_activation_redacts_secret_in_skill_field():
    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / "activations.jsonl"
        at.record_activation(str(path), {"skill": "sk-proj-abcdef0123456789abcdef", "phase": "trigger_matched"})
        raw = path.read_text(encoding="utf-8")
        return "sk-proj-abcdef" not in raw and "[REDACTED]" in raw


def test_record_activation_redacts_secret_in_phase_field():
    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / "activations.jsonl"
        at.record_activation(str(path), {"skill": "x", "phase": "ghp_AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"})
        raw = path.read_text(encoding="utf-8")
        return "ghp_AAAA" not in raw and "[REDACTED]" in raw


def test_record_activation_redacts_secret_in_freeform_field():
    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / "activations.jsonl"
        at.record_activation(str(path), {
            "skill": "x", "phase": "outcome",
            "note": "token=sk-ant-SECRETSECRETSECRET",
        })
        raw = path.read_text(encoding="utf-8")
        row = json.loads(raw.splitlines()[0])
        return "sk-ant-SECRET" not in raw and row["note"] == "token=[REDACTED]"


def test_record_activation_redacts_secret_in_dict_key():
    # 2026-07-05 T1 leak repro (orchestration_trace history) reused here: a
    # secret used as a dict KEY (not a value) must be scrubbed too — the
    # imported walk redacts keys, not just leaves.
    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / "activations.jsonl"
        at.record_activation(str(path), {
            "skill": "x", "phase": "outcome",
            "sk-ant-SECRETSECRETSECRET": "y",
        })
        raw = path.read_text(encoding="utf-8")
        return "sk-ant-" not in raw


def test_record_activation_redacts_secret_with_embedded_quote_and_newline():
    # Escaped-secret leak class (3rd-pass 5a in orchestration_trace history):
    # redacting the RAW string leaf BEFORE serialization means an embedded
    # quote/newline is a clean token boundary, not an inserted backslash.
    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / "activations.jsonl"
        ok = at.record_activation(str(path), {
            "skill": "x", "phase": "outcome",
            "q": 'sk-proj-AAAAAAAAAAAAAAAAAAAA"tail',
        })
        raw = path.read_text(encoding="utf-8")
        return ok is True and "sk-proj-AAAA" not in raw and "[REDACTED]" in raw


def test_record_activation_redacts_secret_with_non_ascii_char():
    # Non-ASCII leak class (3rd-pass 5b in orchestration_trace history):
    # ensure_ascii=True would turn a non-ASCII secret byte into \uXXXX, which
    # the regex misses. The imported walk redacts the raw string first, and
    # the final dump uses ensure_ascii=False so nothing is re-hidden.
    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / "activations.jsonl"
        ok = at.record_activation(str(path), {
            "skill": "x", "phase": "outcome",
            "s": "sk-proj-AAAAAAAAAAAAAAAAé-BBBB",
        })
        raw = path.read_text(encoding="utf-8")
        return (ok is True and "sk-proj-AAAA" not in raw
                and "\\u" not in raw and "[REDACTED]" in raw)


def test_record_activation_none_path_uses_default():
    # Never actually write to the real repo root from a test: redirect the
    # module-level default and confirm None resolves to *some* default path,
    # not a crash, without touching the real .brainer/trace.
    orig_default = at.DEFAULT_TRACE_PATH
    with tempfile.TemporaryDirectory() as td:
        at.DEFAULT_TRACE_PATH = Path(td) / ".brainer" / "trace" / "activations.jsonl"
        try:
            ok = at.record_activation(None, {"skill": "x", "phase": "trigger_matched"})
            return ok is True and at.DEFAULT_TRACE_PATH.exists()
        finally:
            at.DEFAULT_TRACE_PATH = orig_default


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
