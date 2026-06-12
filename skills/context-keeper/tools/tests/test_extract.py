#!/usr/bin/env python3
"""Regression tests for context-keeper extract.py. No pytest, no network.

The failure mode that motivated this file (round-4 stress, 2026-06-12): a
parseable-but-non-dict transcript line (`123`, `["a"]`) crashed regex_extract,
hook.sh swallowed the crash via `|| true`, and the ENTIRE compaction snapshot
was silently lost — the worst possible failure for a memory-preservation hook.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from extract import iter_events, regex_extract  # noqa: E402


def _write_jsonl(lines: list) -> str:
    fd, path = tempfile.mkstemp(suffix=".jsonl")
    with os.fdopen(fd, "w") as f:
        for ln in lines:
            f.write(ln if isinstance(ln, str) else json.dumps(ln))
            f.write("\n")
    return path


def _assistant(text: str) -> dict:
    return {"type": "assistant",
            "message": {"role": "assistant",
                        "content": [{"type": "text", "text": text}]}}


def _user(text: str) -> dict:
    return {"type": "user", "message": {"role": "user", "content": text}}


def test_malformed_lines_do_not_crash_or_block_extraction():
    path = _write_jsonl([
        "123",                                       # parseable non-dict
        '["a","b"]',                                 # parseable list
        '{"type":"assistant","message":"bad"}',      # message-as-string
        '{"type":"user","message":42}',              # message-as-int
        "NOT JSON {{{",                              # unparseable
        _user("fix the flaky auth test in api/auth_test.py"),
        _assistant("Working on it. Error was:\n`TimeoutError: deadline exceeded`"),
    ])
    try:
        events = list(iter_events(path))
        # garbage filtered, real events normalized through
        assert all(isinstance(e, dict) for e in events), events
        assert all(isinstance(e.get("message", {}), dict) for e in events)
        out = regex_extract(events)  # must not raise
        assert isinstance(out, dict)
    finally:
        os.remove(path)


def test_basic_extraction_still_works():
    path = _write_jsonl([
        _user("build the exporter and run the tests"),
        {"type": "assistant", "message": {"role": "assistant", "content": [
            {"type": "tool_use", "name": "Bash",
             "input": {"command": "pytest tests/ -x"}}]}},
        _assistant("Done. See https://example.com/run/42 — 17 tests passed."),
    ])
    try:
        out = regex_extract(list(iter_events(path)))
        flat = json.dumps(out)
        assert "pytest tests/ -x" in flat, flat[:300]
        assert "https://example.com/run/42" in flat, flat[:300]
    finally:
        os.remove(path)


def test_long_unbroken_lines_extract_in_linear_time():
    # round-4 profile: a backtracking {10,150} prefix before the failure-word
    # alternation went quadratic on long lines — 23s for 10k events. Keyword-
    # first windowing made it ~0.5s. Generous 10s bound (slow CI) still
    # catches a quadratic regression (which lands at minutes, not seconds).
    import time
    events = []
    for i in range(2000):
        events.append({"type": "assistant", "message": {"role": "assistant",
                       "content": [{"type": "tool_use", "name": "Bash",
                                    "input": {"command": "echo " + "x" * 4000}},
                                   {"type": "text",
                                    "text": "y" * 4000 + " that didn't work"}]}})
    t = time.perf_counter()
    out = regex_extract(events)
    elapsed = time.perf_counter() - t
    assert elapsed < 10, f"extract took {elapsed:.1f}s on 2k events — quadratic regression?"
    assert out.get("failed_attempts"), "failure sentences should still be captured"


def main():
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"pass {fn.__name__}")
    print(f"OK ({len(fns)} tests)")


if __name__ == "__main__":
    main()
