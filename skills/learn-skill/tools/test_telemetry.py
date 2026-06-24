#!/usr/bin/env python3
"""Tests for telemetry.py — run: python skills/learn-skill/tools/test_telemetry.py"""
from __future__ import annotations

import io
import json
import os
import sys
import tempfile
from contextlib import redirect_stdout
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import telemetry  # noqa: E402


def _run(argv) -> tuple[int, str]:
    buf = io.StringIO()
    with redirect_stdout(buf):
        code = telemetry.main(argv)
    return code, buf.getvalue()


def test_record_and_stats():
    with tempfile.TemporaryDirectory() as t:
        os.environ["CLAUDE_PROJECT_DIR"] = t
        _run(["record", "--skill", "foo", "--outcome", "hit"])
        _run(["record", "--skill", "foo", "--outcome", "hit"])
        _run(["record", "--skill", "foo", "--outcome", "abort"])
        stats = telemetry.compute_stats()
        assert stats["foo"]["total"] == 3
        assert stats["foo"]["hits"] == 2
        assert stats["foo"]["aborts"] == 1
        assert stats["foo"]["consecutive_aborts"] == 1
        assert stats["foo"]["consecutive_hits"] == 0
    print("ok test_record_and_stats")


def test_consecutive_hits():
    with tempfile.TemporaryDirectory() as t:
        os.environ["CLAUDE_PROJECT_DIR"] = t
        for _ in range(4):
            _run(["record", "--skill", "bar", "--outcome", "hit"])
        s = telemetry.compute_stats()["bar"]
        assert s["consecutive_hits"] == 4, s
        assert s["consecutive_aborts"] == 0
    print("ok test_consecutive_hits")


def test_manual_only_filter():
    with tempfile.TemporaryDirectory() as t:
        os.environ["CLAUDE_PROJECT_DIR"] = t
        store = Path(t) / telemetry.STORE_REL
        store.parent.mkdir(parents=True)
        store.write_text(
            json.dumps({"skill": "baz", "ts": "1", "outcome": "hit", "source": "inferred"}) + "\n"
            + json.dumps({"skill": "baz", "ts": "2", "outcome": "hit", "source": "manual"}) + "\n",
            encoding="utf-8")
        assert telemetry.compute_stats()["baz"]["total"] == 2
        assert telemetry.compute_stats(manual_only=True)["baz"]["total"] == 1
    print("ok test_manual_only_filter")


def test_scan_infers_outcome():
    with tempfile.TemporaryDirectory() as t:
        os.environ["CLAUDE_PROJECT_DIR"] = t
        # transcript: skill invoked, then a user correction (=> abort); then another
        # skill invoked, then a neutral user turn (=> hit).
        tp = Path(t) / "transcript.jsonl"
        events = [
            {"type": "assistant", "timestamp": "T1", "message": {"content": [
                {"type": "tool_use", "name": "Skill", "input": {"skill": "alpha"}}]}},
            {"type": "user", "message": {"content": [{"type": "text", "text": "no, that's wrong"}]}},
            {"type": "assistant", "timestamp": "T2", "message": {"content": [
                {"type": "tool_use", "name": "Skill", "input": {"skill": "beta"}}]}},
            {"type": "user", "message": {"content": [{"type": "text", "text": "great, next step please"}]}},
        ]
        tp.write_text("\n".join(json.dumps(e) for e in events), encoding="utf-8")
        code, out = _run(["scan", "--transcript", str(tp)])
        assert code == 0, out
        assert json.loads(out)["added"] == 2
        stats = telemetry.compute_stats()
        assert stats["alpha"]["aborts"] == 1, stats
        assert stats["beta"]["hits"] == 1, stats
        # idempotent re-scan adds nothing
        _, out2 = _run(["scan", "--transcript", str(tp)])
        assert json.loads(out2)["added"] == 0
    print("ok test_scan_infers_outcome")


def test_scan_no_timestamp_collision():
    """HIGH regression: 3 distinct invocations of one skill in a transcript with NO
    per-event timestamps must record as 3, not collapse to 1 (idx in the dedup key)."""
    with tempfile.TemporaryDirectory() as t:
        os.environ["CLAUDE_PROJECT_DIR"] = t
        tp = Path(t) / "transcript.jsonl"
        events = []
        for _ in range(3):
            events.append({"type": "assistant", "message": {"content": [
                {"type": "tool_use", "name": "Skill", "input": {"skill": "gamma"}}]}})
            events.append({"type": "user", "message": {"content": [{"type": "text", "text": "ok"}]}})
        tp.write_text("\n".join(json.dumps(e) for e in events), encoding="utf-8")
        code, out = _run(["scan", "--transcript", str(tp)])
        assert json.loads(out)["added"] == 3, out
        assert telemetry.compute_stats()["gamma"]["total"] == 3
        # idempotent: re-scan adds nothing despite identical (skill, ts='')
        _, out2 = _run(["scan", "--transcript", str(tp)])
        assert json.loads(out2)["added"] == 0
    os.environ.pop("CLAUDE_PROJECT_DIR", None)
    print("ok test_scan_no_timestamp_collision")


def test_chronological_streak_not_file_order():
    """HIGH regression: streaks must be by event time, not file/append order. A recent
    abort written EARLIER in the file must still show as the trailing outcome."""
    with tempfile.TemporaryDirectory() as t:
        os.environ["CLAUDE_PROJECT_DIR"] = t
        store = Path(t) / telemetry.STORE_REL
        store.parent.mkdir(parents=True)
        # File order scrambled; chronological order is 01,02,03,04 hits then 05 abort.
        rows = [
            {"skill": "d", "ts": "2026-01-03T00:00:00", "outcome": "hit", "source": "manual"},
            {"skill": "d", "ts": "2026-01-05T00:00:00", "outcome": "abort", "source": "manual"},
            {"skill": "d", "ts": "2026-01-01T00:00:00", "outcome": "hit", "source": "manual"},
            {"skill": "d", "ts": "2026-01-04T00:00:00", "outcome": "hit", "source": "manual"},
            {"skill": "d", "ts": "2026-01-02T00:00:00", "outcome": "hit", "source": "manual"},
        ]
        store.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
        s = telemetry.compute_stats()["d"]
        assert s["last_outcome"] == "abort", s        # chronologically last = the 01-05 abort
        assert s["consecutive_aborts"] == 1, s
        assert s["consecutive_hits"] == 0, s
    os.environ.pop("CLAUDE_PROJECT_DIR", None)
    print("ok test_chronological_streak_not_file_order")


def test_streak_mixed_ts_formats():
    """HIGH regression (round-2 hole A): a non-ISO ts ('T1') must not sort AFTER a real
    ISO timestamp via lexical compare and mask a genuinely-recent abort."""
    with tempfile.TemporaryDirectory() as t:
        os.environ["CLAUDE_PROJECT_DIR"] = t
        store = Path(t) / telemetry.STORE_REL
        store.parent.mkdir(parents=True)
        rows = [
            # real-world newest is the ISO abort; the hit carries a junk non-ISO ts
            {"skill": "m", "ts": "2026-06-01T00:00:00", "outcome": "abort", "source": "inferred",
             "recorded_at": "2026-06-01T00:00:01"},
            {"skill": "m", "ts": "T1", "outcome": "hit", "source": "inferred",
             "recorded_at": "2020-01-01T00:00:00"},
        ]
        store.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
        s = telemetry.compute_stats()["m"]
        assert s["last_outcome"] == "abort", s
        assert s["consecutive_aborts"] == 1, s
    os.environ.pop("CLAUDE_PROJECT_DIR", None)
    print("ok test_streak_mixed_ts_formats")


def test_scan_idempotent_under_prepend():
    """HIGH regression (round-2 hole D): re-scanning the same logical transcript after a
    leading non-invocation event is inserted must NOT double-count (dedup by
    (skill, ts, dup_ord), not absolute event index)."""
    with tempfile.TemporaryDirectory() as t:
        os.environ["CLAUDE_PROJECT_DIR"] = t
        inv = {"type": "assistant", "timestamp": "2026-06-01T00:00:00", "message": {"content": [
            {"type": "tool_use", "name": "Skill", "input": {"skill": "delta"}}]}}
        usr = {"type": "user", "message": {"content": [{"type": "text", "text": "ok"}]}}
        base = Path(t) / "base.jsonl"
        base.write_text("\n".join(json.dumps(e) for e in [inv, usr]), encoding="utf-8")
        _run(["scan", "--transcript", str(base)])
        assert telemetry.compute_stats()["delta"]["total"] == 1
        # prepend a leading system event and re-scan the SAME logical invocation
        shifted = Path(t) / "shifted.jsonl"
        sysline = {"type": "system", "message": {"content": []}}
        shifted.write_text("\n".join(json.dumps(e) for e in [sysline, inv, usr]), encoding="utf-8")
        _run(["scan", "--transcript", str(shifted)])
        assert telemetry.compute_stats()["delta"]["total"] == 1, "double-counted after prepend"
    os.environ.pop("CLAUDE_PROJECT_DIR", None)
    print("ok test_scan_idempotent_under_prepend")


def test_abort_regex_precision():
    """Regression: benign 'no problem' stays a hit; real 'that didn't work' is an abort."""
    with tempfile.TemporaryDirectory() as t:
        os.environ["CLAUDE_PROJECT_DIR"] = t
        tp = Path(t) / "tx.jsonl"
        events = [
            {"type": "assistant", "timestamp": "A", "message": {"content": [
                {"type": "tool_use", "name": "Skill", "input": {"skill": "benign"}}]}},
            {"type": "user", "message": {"content": [{"type": "text", "text": "no problem, looks good — thanks!"}]}},
            {"type": "assistant", "timestamp": "B", "message": {"content": [
                {"type": "tool_use", "name": "Skill", "input": {"skill": "broke"}}]}},
            {"type": "user", "message": {"content": [{"type": "text", "text": "that didn't work, still broken"}]}},
        ]
        tp.write_text("\n".join(json.dumps(e) for e in events), encoding="utf-8")
        _run(["scan", "--transcript", str(tp)])
        stats = telemetry.compute_stats()
        assert stats["benign"]["hits"] == 1 and stats["benign"]["aborts"] == 0, stats
        assert stats["broke"]["aborts"] == 1, stats
    os.environ.pop("CLAUDE_PROJECT_DIR", None)
    print("ok test_abort_regex_precision")


def test_checkpoint_clean_slate():
    """A checkpoint (written on refine) resets the counted slate: pre-checkpoint
    hits/aborts are ignored, only post-checkpoint usage counts."""
    with tempfile.TemporaryDirectory() as t:
        os.environ["CLAUDE_PROJECT_DIR"] = t
        _run(["record", "--skill", "r", "--outcome", "hit"])
        _run(["record", "--skill", "r", "--outcome", "abort"])
        _run(["record", "--skill", "r", "--outcome", "abort"])
        assert telemetry.compute_stats()["r"]["aborts"] == 2
        _run(["record", "--skill", "r", "--outcome", "checkpoint"])  # refine point
        s = telemetry.compute_stats().get("r", {})
        assert s.get("total", 0) == 0, s  # clean slate
        _run(["record", "--skill", "r", "--outcome", "hit"])
        s2 = telemetry.compute_stats()["r"]
        assert s2["hits"] == 1 and s2["aborts"] == 0, s2  # only post-checkpoint counts
    os.environ.pop("CLAUDE_PROJECT_DIR", None)
    print("ok test_checkpoint_clean_slate")


def test_flag():
    with tempfile.TemporaryDirectory() as t:
        os.environ["CLAUDE_PROJECT_DIR"] = t
        for _ in range(3):
            _run(["record", "--skill", "bad", "--outcome", "abort"])
        code, out = _run(["flag", "--min-aborts", "3"])
        assert "FLAG bad" in out, out
        code2, out2 = _run(["flag", "--min-aborts", "5"])
        assert "no skills" in out2
    print("ok test_flag")


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    try:
        for fn in fns:
            fn()
        print(f"\nALL {len(fns)} TESTS PASSED")
    finally:
        os.environ.pop("CLAUDE_PROJECT_DIR", None)
