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
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from extract import PATH_RE, iter_events, regex_extract  # noqa: E402

_EXTRACT_PY = Path(__file__).parent.parent / "extract.py"


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


def test_same_minute_extractions_do_not_collide():
    # Two PreCompact events for one session in the same UTC minute must NOT
    # overwrite each other. Minute-granularity filenames silently dropped the
    # first checkpoint (data loss); seconds + trigger + numeric suffix fix it.
    transcript = _write_jsonl([
        _user("build the exporter"),
        {"type": "assistant", "message": {"role": "assistant", "content": [
            {"type": "tool_use", "name": "Bash",
             "input": {"command": "pytest tests/ -x"}}]}},
    ])
    workdir = tempfile.mkdtemp()
    env = dict(os.environ, TOKEN_ECONOMY_ROOT=workdir)
    sessions = Path(workdir) / ".brainer" / "sessions"
    try:
        for _ in range(2):
            r = subprocess.run(
                [sys.executable, str(_EXTRACT_PY), transcript,
                 "--pointer-only", "--session-id", "deadbeefcafef00d",
                 "--trigger", "manual"],
                env=env, capture_output=True, text=True,
            )
            assert r.returncode == 0, r.stderr
        written = sorted(sessions.glob("*.md"))
        # Both checkpoints survive — the first is not clobbered by the second.
        assert len(written) == 2, [p.name for p in written]
        assert written[0].name != written[1].name, [p.name for p in written]
    finally:
        os.remove(transcript)
        import shutil
        shutil.rmtree(workdir, ignore_errors=True)


def test_path_re_captures_bare_relative_path():
    # PATH_RE used to force a leading /, ~/, ./ or ../, dropping bare relative
    # multi-segment paths (api/auth.py, src/foo.ts) from files_touched.
    assert "api/auth.py" in PATH_RE.findall("touched api/auth.py today")
    assert "src/foo.ts" in PATH_RE.findall("edit src/foo.ts please")
    # Still captures the prefixed forms and absolute paths.
    assert "./local/x.md" in PATH_RE.findall("see ./local/x.md")
    assert "/Users/za/extract.py" in PATH_RE.findall("at /Users/za/extract.py")
    # Bare single-segment filenames are NOT paths (no internal slash) — unchanged.
    assert PATH_RE.findall("just foo.py here") == []
    # End-to-end: bare relative path lands in files_touched.
    out = regex_extract([_assistant("I edited api/auth.py to fix the bug")])
    assert "api/auth.py" in out.get("files_touched", []), out.get("files_touched")


def test_bash_command_captured_from_top_level_content():
    # Top-level-content events (no "message" key) put content at ev["content"].
    # The structural tool_use walk read the (None) message content, so the Bash
    # command — and files_created from Write — were silently lost for that shape.
    events = [
        {"type": "assistant",
         "content": [{"type": "tool_use", "name": "Bash",
                      "input": {"command": "ruff check src/ --fix"}},
                     {"type": "tool_use", "name": "Write",
                      "input": {"file_path": "out/report.md"}}]},
    ]
    out = regex_extract(events)
    assert "ruff check src/ --fix" in out.get("commands_run", []), out.get("commands_run")
    assert "out/report.md" in out.get("files_created", []), out.get("files_created")


def test_bom_prefixed_frontmatter_parses():
    # A UTF-8 BOM before the opening `---` must NOT defeat frontmatter parsing,
    # else a BOM'd SKILL.md silently drops from the output-style / pulse snapshot.
    # (wiki-memory's parsers already tolerated BOM; this one diverged until fixed.)
    from extract import _parse_frontmatter
    plain = "---\nname: caveman-ultra\noutput_style: true\n---\nbody\n"
    bom = "﻿" + plain
    assert _parse_frontmatter(plain).get("output_style") == "true"
    assert _parse_frontmatter(bom).get("output_style") == "true", "BOM defeated frontmatter parse"


def main():
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"pass {fn.__name__}")
    print(f"OK ({len(fns)} tests)")


if __name__ == "__main__":
    main()
