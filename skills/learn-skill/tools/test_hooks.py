#!/usr/bin/env python3
"""Tests for the learn-skill session hooks — run: python skills/learn-skill/tools/test_hooks.py"""
from __future__ import annotations

import io
import json
import os
import sys
import tempfile
from contextlib import redirect_stdout
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import hooks  # noqa: E402
import telemetry  # noqa: E402
import learn  # noqa: E402


def _run(argv, stdin=""):
    buf = io.StringIO()
    old = sys.stdin
    sys.stdin = io.StringIO(stdin)
    try:
        with redirect_stdout(buf):
            code = hooks.main(argv)
    finally:
        sys.stdin = old
    return code, buf.getvalue()


def _scaffold(skills_dir, name, status="proposed", source="session:x"):
    out = skills_dir / name / "SKILL.md"
    learn.main(["scaffold", "--name", name, "--desc", "d", "--source", source,
                "--when", "a", "--proc", "b", "--verify", "c", "--out", str(out)])
    if status != "proposed":
        learn._rewrite_frontmatter(out, {"status": status})
    return out


def test_session_end_scans_transcript():
    with tempfile.TemporaryDirectory() as t:
        os.environ["CLAUDE_PROJECT_DIR"] = t
        tp = Path(t) / "tx.jsonl"
        ev = [
            {"type": "assistant", "timestamp": "2026-06-01T00:00:00", "message": {"content": [
                {"type": "tool_use", "name": "Skill", "input": {"skill": "foo"}}]}},
            {"type": "user", "message": {"content": [{"type": "text", "text": "ok"}]}},
        ]
        tp.write_text("\n".join(json.dumps(e) for e in ev), encoding="utf-8")
        code, _ = _run(["session-end"], stdin=json.dumps(
            {"session_id": "s1", "transcript_path": str(tp)}))
        assert code == 0
        assert telemetry.compute_stats()["foo"]["hits"] == 1
    os.environ.pop("CLAUDE_PROJECT_DIR", None)
    print("ok test_session_end_scans_transcript")


def test_session_end_safe_on_garbage():
    with tempfile.TemporaryDirectory() as t:
        os.environ["CLAUDE_PROJECT_DIR"] = t
        for bad in ("", "not json", "[1,2,3]", json.dumps({"transcript_path": "/no/such"})):
            code, out = _run(["session-end"], stdin=bad)
            assert code == 0, bad
            assert out == ""
    os.environ.pop("CLAUDE_PROJECT_DIR", None)
    print("ok test_session_end_safe_on_garbage")


def test_session_start_silent_when_nothing():
    with tempfile.TemporaryDirectory() as t:
        os.environ["CLAUDE_PROJECT_DIR"] = t
        sd = Path(t) / "skills"
        os.environ["LEARN_SKILL_SKILLS_DIR"] = str(sd)
        _scaffold(sd, "fresh-proposed")  # no telemetry -> not promote-ready
        code, out = _run(["session-start"])
        assert code == 0 and out == "", repr(out)
    os.environ.pop("CLAUDE_PROJECT_DIR", None)
    os.environ.pop("LEARN_SKILL_SKILLS_DIR", None)
    print("ok test_session_start_silent_when_nothing")


def test_session_start_surfaces_promote_ready():
    with tempfile.TemporaryDirectory() as t:
        os.environ["CLAUDE_PROJECT_DIR"] = t
        sd = Path(t) / "skills"
        os.environ["LEARN_SKILL_SKILLS_DIR"] = str(sd)
        _scaffold(sd, "ready-one")
        for _ in range(3):
            telemetry.main(["record", "--skill", "ready-one", "--outcome", "hit"])
        code, out = _run(["session-start"])
        assert "PROMOTE-ready" in out and "ready-one" in out, out
        assert "stay agent-run" in out  # honesty line present
    os.environ.pop("CLAUDE_PROJECT_DIR", None)
    os.environ.pop("LEARN_SKILL_SKILLS_DIR", None)
    print("ok test_session_start_surfaces_promote_ready")


def test_session_start_surfaces_demote():
    with tempfile.TemporaryDirectory() as t:
        os.environ["CLAUDE_PROJECT_DIR"] = t
        sd = Path(t) / "skills"
        os.environ["LEARN_SKILL_SKILLS_DIR"] = str(sd)
        _scaffold(sd, "bad-one", status="trusted")
        for _ in range(3):
            telemetry.main(["record", "--skill", "bad-one", "--outcome", "abort"])
        code, out = _run(["session-start"])
        assert "FAILING" in out and "bad-one" in out and "refine" in out, out
    os.environ.pop("CLAUDE_PROJECT_DIR", None)
    os.environ.pop("LEARN_SKILL_SKILLS_DIR", None)
    print("ok test_session_start_surfaces_demote")


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
    print(f"ALL {len(fns)} TESTS PASSED")
