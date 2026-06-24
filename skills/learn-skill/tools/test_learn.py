#!/usr/bin/env python3
"""Tests for learn.py — run: python skills/learn-skill/tools/test_learn.py"""
from __future__ import annotations

import io
import sys
import tempfile
from contextlib import redirect_stdout
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import learn  # noqa: E402


def _mk_skill(skills_dir: Path, name: str, desc: str, body: str = "") -> None:
    d = skills_dir / name
    d.mkdir(parents=True)
    (d / "SKILL.md").write_text(
        f"---\nname: {name}\ndescription: {desc}\n---\n\n# {name}\n{body}\n",
        encoding="utf-8",
    )


def _run(argv) -> tuple[int, str]:
    buf = io.StringIO()
    with redirect_stdout(buf):
        code = learn.main(argv)
    return code, buf.getvalue()


def test_dedup_desc_hit():
    with tempfile.TemporaryDirectory() as t:
        sd = Path(t)
        _mk_skill(sd, "cache-lint", "Audit a project for prompt-cache hygiene rules")
        code, out = _run(["dedup", "--desc",
                          "Audit a project for prompt cache hygiene against rules",
                          "--skills-dir", str(sd)])
        assert "LIKELY_PATCH" in out, out
        assert code == 3, code
        assert "cache-lint" in out
    print("ok test_dedup_desc_hit")


def test_dedup_create():
    with tempfile.TemporaryDirectory() as t:
        sd = Path(t)
        _mk_skill(sd, "cache-lint", "Audit a project for prompt-cache hygiene rules")
        code, out = _run(["dedup", "--desc",
                          "Render animated SVG mascots that float on the desktop",
                          "--skills-dir", str(sd)])
        assert "CREATE" in out, out
        assert code == 0, code
    print("ok test_dedup_create")


def test_dedup_body_match():
    with tempfile.TemporaryDirectory() as t:
        sd = Path(t)
        _mk_skill(sd, "existing", "totally unrelated description words here",
                  body="```\npython tools/special_unique_command.py --flag value\n```")
        cand = Path(t) / "cand.md"
        cand.write_text(
            "# new\n```\npython tools/special_unique_command.py --flag value\n```\n",
            encoding="utf-8")
        code, out = _run(["dedup", "--desc", "some brand new orthogonal thing",
                          "--body-file", str(cand), "--skills-dir", str(sd)])
        assert "POSSIBLE_PATCH" in out, out
        assert code == 3, code
        assert "existing" in out
    print("ok test_dedup_body_match")


def test_lint_pass():
    with tempfile.TemporaryDirectory() as t:
        f = Path(t) / "SKILL.md"
        f.write_text(
            "---\nname: x\ndescription: short desc\nstatus: proposed\n---\n"
            "## When to Use\na\n## Procedure\nb\n## Verification\nc\n",
            encoding="utf-8")
        code, out = _run(["lint", "--file", str(f)])
        assert code == 0, out
        assert "PASS" in out
    print("ok test_lint_pass")


def test_lint_fail_missing_section_and_key():
    with tempfile.TemporaryDirectory() as t:
        f = Path(t) / "SKILL.md"
        f.write_text(
            "---\nname: x\ndescription: short\n---\n## When to Use\na\n",
            encoding="utf-8")
        code, out = _run(["lint", "--file", str(f)])
        assert code == 1, out
        assert "missing frontmatter key: status" in out
        assert "missing required section: Procedure" in out
        assert "missing required section: Verification" in out
    print("ok test_lint_fail_missing_section_and_key")


def test_lint_warn_long_desc():
    with tempfile.TemporaryDirectory() as t:
        f = Path(t) / "SKILL.md"
        long_desc = "x" * 80
        f.write_text(
            f"---\nname: x\ndescription: {long_desc}\nstatus: proposed\n---\n"
            "## When to Use\na\n## Procedure\nb\n## Verification\nc\n",
            encoding="utf-8")
        code, out = _run(["lint", "--file", str(f)])
        assert code == 0, out  # advisory only
        assert "WARN" in out and "80 chars" in out
    print("ok test_lint_warn_long_desc")


def test_scaffold_frontmatter():
    with tempfile.TemporaryDirectory() as t:
        out = Path(t) / "out.md"
        code, _ = _run(["scaffold", "--name", "My New Skill", "--desc", "does a thing",
                        "--source", "https://example.com/doc", "--learned-at", "2026-06-24",
                        "--out", str(out)])
        assert code == 0
        text = out.read_text()
        assert "name: my-new-skill" in text
        assert "status: proposed" in text
        assert "disable-model-invocation: true" in text
        assert "auto-install: false" in text
        assert "source: https://example.com/doc" in text
        assert "learned_at: 2026-06-24" in text
        # scaffolded skill must itself pass lint
        code2, out2 = _run(["lint", "--file", str(out)])
        assert code2 == 0, out2
    print("ok test_scaffold_frontmatter")


import json  # noqa: E402
import os  # noqa: E402
import subprocess  # noqa: E402


def _scaffold_into(skills_dir: Path, name: str, source: str, learned_at: str = "2026-06-24"):
    out = skills_dir / learn._slug(name) / "SKILL.md"
    _run(["scaffold", "--name", name, "--desc", "does a thing", "--source", source,
          "--learned-at", learned_at, "--when", "x", "--proc", "y", "--verify", "z",
          "--out", str(out)])
    return out


def test_promote_refused_without_telemetry():
    with tempfile.TemporaryDirectory() as t:
        os.environ["CLAUDE_PROJECT_DIR"] = t
        sd = Path(t) / "skills"
        _scaffold_into(sd, "demo-a", "session:x")
        code, out = _run(["promote", "--name", "demo-a", "--skills-dir", str(sd)])
        assert code == 1, out
        assert "REFUSED" in out
    os.environ.pop("CLAUDE_PROJECT_DIR", None)
    print("ok test_promote_refused_without_telemetry")


def test_promote_succeeds_with_telemetry():
    with tempfile.TemporaryDirectory() as t:
        os.environ["CLAUDE_PROJECT_DIR"] = t
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        import telemetry
        sd = Path(t) / "skills"
        path = _scaffold_into(sd, "demo-b", "session:x")
        for _ in range(3):
            telemetry.main(["record", "--skill", "demo-b", "--outcome", "hit"])
        code, out = _run(["promote", "--name", "demo-b", "--skills-dir", str(sd)])
        assert code == 0, out
        assert "PROMOTED" in out
        text = path.read_text()
        assert "status: trusted" in text
        assert "disable-model-invocation: false" in text
        assert "promoted_after_hits: 3" in text
    os.environ.pop("CLAUDE_PROJECT_DIR", None)
    print("ok test_promote_succeeds_with_telemetry")


def test_promote_blocked_by_trailing_abort():
    with tempfile.TemporaryDirectory() as t:
        os.environ["CLAUDE_PROJECT_DIR"] = t
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        import telemetry
        sd = Path(t) / "skills"
        _scaffold_into(sd, "demo-c", "session:x")
        for _ in range(5):
            telemetry.main(["record", "--skill", "demo-c", "--outcome", "hit"])
        telemetry.main(["record", "--skill", "demo-c", "--outcome", "abort"])  # trailing abort
        code, out = _run(["promote", "--name", "demo-c", "--skills-dir", str(sd)])
        assert code == 1, out
        assert "REFUSED" in out and "trailing abort" in out
    os.environ.pop("CLAUDE_PROJECT_DIR", None)
    print("ok test_promote_blocked_by_trailing_abort")


def test_demote_roundtrip():
    with tempfile.TemporaryDirectory() as t:
        os.environ["CLAUDE_PROJECT_DIR"] = t
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        import telemetry
        sd = Path(t) / "skills"
        path = _scaffold_into(sd, "demo-d", "session:x")
        for _ in range(3):
            telemetry.main(["record", "--skill", "demo-d", "--outcome", "hit"])
        _run(["promote", "--name", "demo-d", "--skills-dir", str(sd)])
        assert "status: trusted" in path.read_text()
        code, out = _run(["demote", "--name", "demo-d", "--skills-dir", str(sd), "--reason", "flagged"])
        assert code == 0, out
        text = path.read_text()
        assert "status: proposed" in text
        assert "disable-model-invocation: true" in text
        assert "demote_reason: flagged" in text
    os.environ.pop("CLAUDE_PROJECT_DIR", None)
    print("ok test_demote_roundtrip")


def test_staleness_git_path():
    with tempfile.TemporaryDirectory() as t:
        root = Path(t)
        # Pin the commit date to the past so realistic learned_at dates on either
        # side of it are unambiguous (git approxidate is unreliable on far-future
        # --since bounds, so the "fresh" date must also be in the past).
        env = {**os.environ, "GIT_AUTHOR_DATE": "2020-06-01T00:00:00",
               "GIT_COMMITTER_DATE": "2020-06-01T00:00:00"}
        subprocess.run(["git", "-C", t, "init", "-q"], check=True)
        subprocess.run(["git", "-C", t, "config", "user.email", "x@y.z"], check=True)
        subprocess.run(["git", "-C", t, "config", "user.name", "x"], check=True)
        (root / "src.py").write_text("print(1)\n")
        subprocess.run(["git", "-C", t, "add", "."], check=True)
        subprocess.run(["git", "-C", t, "commit", "-qm", "init"], check=True, env=env)
        sd = root / "skills"
        # learned BEFORE the 2020 commit -> stale; learned AFTER it -> fresh
        _scaffold_into(sd, "stale-one", "src.py", learned_at="2000-01-01")
        _scaffold_into(sd, "fresh-one", "src.py", learned_at="2021-01-01")
        code, out = _run(["staleness", "--skills-dir", str(sd), "--root", t])
        assert "STALE] stale-one" in out, out
        assert "ok ] fresh-one" in out, out
        # --apply flips the stale one's status
        _run(["staleness", "--skills-dir", str(sd), "--root", t, "--apply"])
        assert "status: stale" in (sd / "stale-one" / "SKILL.md").read_text()
    print("ok test_staleness_git_path")


def test_staleness_url_age():
    with tempfile.TemporaryDirectory() as t:
        sd = Path(t) / "skills"
        _scaffold_into(sd, "old-url", "https://example.com/doc", learned_at="2000-01-01")
        _scaffold_into(sd, "new-url", "https://example.com/doc", learned_at="2999-01-01")
        code, out = _run(["staleness", "--skills-dir", str(sd), "--root", t, "--max-age-days", "90"])
        assert "CHECK] old-url" in out, out
        assert "ok ] new-url" in out, out
    print("ok test_staleness_url_age")


def test_crlf_preserved_on_promote():
    """MED regression: promoting a CRLF file must not strip \\r from the body."""
    with tempfile.TemporaryDirectory() as t:
        os.environ["CLAUDE_PROJECT_DIR"] = t
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        import telemetry
        sd = Path(t) / "skills"
        path = _scaffold_into(sd, "crlf-skill", "session:x")
        # convert to CRLF
        path.write_bytes(path.read_text().replace("\n", "\r\n").encode("utf-8"))
        cr_before = path.read_bytes().count(b"\r")
        for _ in range(3):
            telemetry.main(["record", "--skill", "crlf-skill", "--outcome", "hit"])
        code, out = _run(["promote", "--name", "crlf-skill", "--skills-dir", str(sd)])
        assert code == 0, out
        cr_after = path.read_bytes().count(b"\r")
        assert cr_after >= cr_before, f"CRLF stripped: {cr_before} -> {cr_after}"
        text = path.read_text()
        assert "status: trusted" in text and "## Verification" in text
    os.environ.pop("CLAUDE_PROJECT_DIR", None)
    print("ok test_crlf_preserved_on_promote")


def test_stale_not_promotable():
    """MED regression: a stale skill must be refused (re-/learn first), not promoted
    on residual telemetry."""
    with tempfile.TemporaryDirectory() as t:
        os.environ["CLAUDE_PROJECT_DIR"] = t
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        import telemetry
        sd = Path(t) / "skills"
        path = _scaffold_into(sd, "stale-skill", "session:x")
        learn._rewrite_frontmatter(path, {"status": "stale"})
        for _ in range(5):
            telemetry.main(["record", "--skill", "stale-skill", "--outcome", "hit"])
        code, out = _run(["promote", "--name", "stale-skill", "--skills-dir", str(sd)])
        assert code == 1, out
        assert "Re-/learn" in out, out
        assert "status: stale" in path.read_text()  # untouched
    os.environ.pop("CLAUDE_PROJECT_DIR", None)
    print("ok test_stale_not_promotable")


def test_staleness_unknown_on_nongit():
    """MED regression: a failed git log (non-git root) must report 'unknown', never an
    authoritative 'fresh'."""
    with tempfile.TemporaryDirectory() as t:
        root = Path(t)  # NOT a git repo
        (root / "src.py").write_text("x\n")
        sd = root / "skills"
        _scaffold_into(sd, "ng", "src.py", learned_at="2020-01-01")
        code, out = _run(["staleness", "--skills-dir", str(sd), "--root", t])
        assert "??  ] ng" in out, out
        assert "git log failed" in out, out
    print("ok test_staleness_unknown_on_nongit")


def test_check_tools():
    """#1 conditional activation: a missing CLI dep is surfaced (exit 3); present deps
    and no-deps pass."""
    with tempfile.TemporaryDirectory() as t:
        os.environ["CLAUDE_PROJECT_DIR"] = t
        sd = Path(t) / "skills"
        _scaffold_into(sd, "needs-xyz", "session:x")
        learn._rewrite_frontmatter(sd / "needs-xyz" / "SKILL.md",
                                   {"requires_tools": "definitely-not-real-bin-xyz"})
        code, out = _run(["check-tools", "--name", "needs-xyz", "--skills-dir", str(sd)])
        assert code == 3 and "MISSING" in out, out
        # a tool that exists (python3) + harness tools → present
        learn._rewrite_frontmatter(sd / "needs-xyz" / "SKILL.md", {"requires_tools": "python3, Bash"})
        code2, out2 = _run(["check-tools", "--name", "needs-xyz", "--skills-dir", str(sd)])
        assert code2 == 0, out2
    os.environ.pop("CLAUDE_PROJECT_DIR", None)
    print("ok test_check_tools")


_GOOD_RATIONALE = ("We chose to narrow the trigger rather than widen it, because it kept "
                   "aborting on unrelated prompts.\nSteps:\n1. tighten the regex\n2. add a guard")


def test_patch_refuses_bad_rationale():
    with tempfile.TemporaryDirectory() as t:
        os.environ["CLAUDE_PROJECT_DIR"] = t
        sd = Path(t) / "skills"
        out_path = sd / "p1" / "SKILL.md"
        _run(["scaffold", "--name", "p1", "--desc", "d", "--source", "session:x",
              "--when", "a", "--proc", "UNIQUE_TOKEN_QQ here", "--verify", "c",
              "--out", str(out_path)])
        orig = out_path.read_text()
        # unique + present --old, but a thin rationale → write-gate refuses (gate before write)
        code, out = _run(["patch", "--name", "p1", "--skills-dir", str(sd),
                          "--old", "UNIQUE_TOKEN_QQ here", "--new", "z", "--rationale", "stuff"])
        assert code == 1 and "write-gate" in out, out
        assert out_path.read_text() == orig  # never written
    os.environ.pop("CLAUDE_PROJECT_DIR", None)
    print("ok test_patch_refuses_bad_rationale")


def test_patch_success_resets_and_checkpoints():
    with tempfile.TemporaryDirectory() as t:
        os.environ["CLAUDE_PROJECT_DIR"] = t
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        import telemetry
        sd = Path(t) / "skills"
        out_path = sd / "p2" / "SKILL.md"
        _run(["scaffold", "--name", "p2", "--desc", "d", "--source", "session:x",
              "--when", "a", "--proc", "STEP_ALPHA runs first.", "--verify", "c",
              "--out", str(out_path)])
        # promote it first so we can see the reset to proposed
        for _ in range(3):
            telemetry.main(["record", "--skill", "p2", "--outcome", "hit"])
        _run(["promote", "--name", "p2", "--skills-dir", str(sd)])
        telemetry.main(["record", "--skill", "p2", "--outcome", "abort"])  # then it fails
        assert telemetry.compute_stats()["p2"]["consecutive_aborts"] == 1
        code, out = _run(["patch", "--name", "p2", "--skills-dir", str(sd),
                          "--old", "STEP_ALPHA runs first.", "--new", "STEP_BETA runs first.",
                          "--rationale", _GOOD_RATIONALE])
        assert code == 0 and "PATCHED" in out, out
        text = out_path.read_text()
        assert "STEP_BETA runs first." in text
        assert "status: proposed" in text and "refined_at:" in text
        # telemetry checkpoint cleared the abort streak → clean slate
        st = telemetry.compute_stats().get("p2", {})
        assert st.get("aborts", 0) == 0 and st.get("hits", 0) == 0, st
    os.environ.pop("CLAUDE_PROJECT_DIR", None)
    print("ok test_patch_success_resets_and_checkpoints")


def test_patch_reverts_on_lint_break():
    with tempfile.TemporaryDirectory() as t:
        os.environ["CLAUDE_PROJECT_DIR"] = t
        sd = Path(t) / "skills"
        path = _scaffold_into(sd, "p3", "session:x")
        orig = path.read_text()
        # remove a required section heading → patched file fails lint → revert
        code, out = _run(["patch", "--name", "p3", "--skills-dir", str(sd),
                          "--old", "## Verification", "--new", "## Gone",
                          "--rationale", _GOOD_RATIONALE])
        assert code == 1 and "reverted" in out.lower(), out
        assert path.read_text() == orig
    os.environ.pop("CLAUDE_PROJECT_DIR", None)
    print("ok test_patch_reverts_on_lint_break")


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
    print(f"\nALL {len(fns)} TESTS PASSED")
