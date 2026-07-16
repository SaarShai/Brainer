#!/usr/bin/env python3
"""Tests for learn.py — run: python skills/learn-skill/tools/test_learn.py"""
from __future__ import annotations

import io
import shlex
import stat
import sys
import tempfile
import time
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

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
            "## When to Use\na\n## Procedure\nb\n## Pitfalls\nc\n## Verification\nd\n",
            encoding="utf-8")
        code, out = _run(["lint", "--file", str(f)])
        assert code == 0, out
        assert "PASS" in out
    print("ok test_lint_pass")


def test_lint_fails_without_pitfalls():
    with tempfile.TemporaryDirectory() as t:
        f = Path(t) / "SKILL.md"
        f.write_text(
            "---\nname: x\ndescription: short desc\nstatus: proposed\n---\n"
            "## When to Use\na\n## Procedure\nb\n## Verification\nc\n",
            encoding="utf-8")
        code, out = _run(["lint", "--file", str(f)])
        assert code == 1, out
        assert "missing required section: Pitfalls" in out, out
    print("ok test_lint_fails_without_pitfalls")


def test_lint_rejects_pitfalls_heading_inside_fence():
    for opener, closer in (("```markdown", "```"), ("~~~markdown", "~~~")):
        with tempfile.TemporaryDirectory() as t:
            f = Path(t) / "SKILL.md"
            f.write_text(
                "---\nname: x\ndescription: short desc\nstatus: proposed\n---\n"
                "## When to Use\na\n## Procedure\nb\n"
                f"{opener}\n## Pitfalls\nnot a real section\n{closer}\n"
                "## Verification\nd\n",
                encoding="utf-8")
            code, out = _run(["lint", "--file", str(f)])
            assert code == 1, out
            assert "missing required section: Pitfalls" in out, out
    print("ok test_lint_rejects_pitfalls_heading_inside_fence")


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
            "## When to Use\na\n## Procedure\nb\n## Pitfalls\nc\n## Verification\nd\n",
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
        # source contains '://' so it is now YAML-quoted; assert it round-trips
        # through the frontmatter reader rather than pinning the raw quoting.
        assert learn._frontmatter(text)["source"] == "https://example.com/doc"
        assert "learned_at: 2026-06-24" in text
        # scaffolded skill must itself pass lint
        code2, out2 = _run(["lint", "--file", str(out)])
        assert code2 == 0, out2
    print("ok test_scaffold_frontmatter")


def test_scaffold_yaml_safe_with_punctuation():
    """P1-1: a description/source carrying ': ' '#' '[' '\"' must scaffold to VALID
    YAML and round-trip — not the raw unquoted form that breaks a strict parser."""
    with tempfile.TemporaryDirectory() as t:
        out = Path(t) / "out.md"
        desc = 'Do X: then Y #hash [b] "q"'
        src = "https://x.com/a?b=1: c"
        code, _ = _run(["scaffold", "--name", "punct", "--desc", desc, "--source", src,
                        "--when", "w", "--proc", "p", "--verify", "v", "--out", str(out)])
        assert code == 0
        text = out.read_text()
        # quoted (not raw) so a strict host won't choke
        assert "description: Do X: then Y" not in text, text
        fm = learn._frontmatter(text)
        assert fm["description"] == desc, fm["description"]
        assert fm["source"] == src, fm["source"]
        try:
            import yaml  # type: ignore
            import re as _re
            blk = _re.match(r"^---\s*\n(.*?)\n---\s*\n", text, _re.DOTALL)
            d = yaml.safe_load(blk.group(1))
            assert d["description"] == desc and d["source"] == src
        except ImportError:
            pass
        # and it must lint clean
        code2, out2 = _run(["lint", "--file", str(out)])
        assert code2 == 0, out2
    print("ok test_scaffold_yaml_safe_with_punctuation")


def test_lint_fails_on_invalid_yaml_frontmatter():
    """The lenient _frontmatter reader tolerates malformed YAML; lint must not —
    a hand-edited unquoted ': ' has to be caught (requires PyYAML)."""
    try:
        import yaml  # noqa: F401
    except ImportError:
        print("ok test_lint_fails_on_invalid_yaml_frontmatter (skipped, no PyYAML)")
        return
    with tempfile.TemporaryDirectory() as t:
        out = Path(t) / "out.md"
        out.write_text(
            "---\nname: bad\ndescription: Do X: then Y\nstatus: proposed\n---\n"
            "# bad\n## When to Use\nx\n## Procedure\nx\n## Verification\nx\n",
            encoding="utf-8")
        code, msg = _run(["lint", "--file", str(out)])
        assert code == 1, msg
        assert "not valid YAML" in msg, msg
    print("ok test_lint_fails_on_invalid_yaml_frontmatter")


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
        # Simulate a previously-promoted (trusted, auto-invocable) skill that has
        # since gone stale — the dangerous case: marking stale must also re-disable
        # model invocation, else a drifted skill keeps auto-firing.
        learn._rewrite_frontmatter(sd / "stale-one" / "SKILL.md",
                                   {"status": "trusted", "disable-model-invocation": "false"})
        # --apply flips the stale one's status AND re-disables model invocation
        _run(["staleness", "--skills-dir", str(sd), "--root", t, "--apply"])
        stale_md = (sd / "stale-one" / "SKILL.md").read_text()
        assert "status: stale" in stale_md
        assert "disable-model-invocation: true" in stale_md, stale_md
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
        # Wayfinder-style YAML inline lists must not leave bracket characters on
        # harness tool names (the cross-host false-MISSING regression).
        learn._rewrite_frontmatter(sd / "needs-xyz" / "SKILL.md",
                                   {"requires_tools": "[Read, Edit]"})
        code3, out3 = _run(["check-tools", "--name", "needs-xyz",
                            "--skills-dir", str(sd)])
        assert code3 == 0, out3
    os.environ.pop("CLAUDE_PROJECT_DIR", None)
    print("ok test_check_tools")


_GOOD_RATIONALE = ("We chose to narrow the trigger rather than widen it, because it kept "
                   "aborting on unrelated prompts.\nSteps:\n1. tighten the regex\n2. add a guard")


def _contains_gate(path: Path, token: str, present: bool = True) -> str:
    script = ("from pathlib import Path; "
              f"found={token!r} in Path({str(path)!r}).read_text(encoding='utf-8'); "
              f"raise SystemExit(0 if found == {present!r} else 1)")
    return f"{shlex.quote(sys.executable)} -c {shlex.quote(script)}"


def _exit_gate(code: int) -> str:
    script = f"raise SystemExit({code})"
    return f"{shlex.quote(sys.executable)} -c {shlex.quote(script)}"


def _behavior_args(path: Path, fixed_token: str) -> list[str]:
    return ["--held-in-cmd", _contains_gate(path, fixed_token),
            "--held-out-cmd", _exit_gate(0)]


def _hidden_registry(path: Path, target: Path, *, secret: str = "") -> list[str]:
    held_in = [sys.executable, "-c",
               ("from pathlib import Path; import sys; "
                f"sys.exit(0 if {str(target)!r} and "
                f"'FIXED steps' in Path({str(target)!r}).read_text() else 1)")]
    held_out = [sys.executable, "-c", f"print({secret!r}); raise SystemExit(0)"]
    path.write_text(json.dumps({"held-in-v1": held_in, "held-out-v1": held_out}),
                    encoding="utf-8")
    return ["--gate-registry", str(path),
            "--held-in-id", "held-in-v1", "--held-out-id", "held-out-v1"]


def test_hidden_gate_registry_success_and_no_command_leakage():
    with tempfile.TemporaryDirectory() as t:
        os.environ["CLAUDE_PROJECT_DIR"] = t
        sd = Path(t) / "skills"
        target = _scaffold_into(sd, "p-hidden", "session:x")
        registry = Path(t) / "frozen-gates.json"
        secret = "NEVER_SURFACE_HIDDEN_COMMAND_7d2f"
        args = _hidden_registry(registry, target, secret=secret)
        code, out = _run(["patch", "--name", "p-hidden", "--skills-dir", str(sd),
                          "--old", "## Procedure\ny",
                          "--new", "## Procedure\nFIXED steps",
                          "--rationale", _GOOD_RATIONALE, *args])
        assert code == 0 and "PATCHED" in out, out
        assert secret not in out and str(registry) not in out, out
    os.environ.pop("CLAUDE_PROJECT_DIR", None)
    print("ok test_hidden_gate_registry_success_and_no_command_leakage")


def test_hidden_gate_registry_rejects_symlink_and_hardlink():
    for kind in ("symlink", "hardlink"):
        with tempfile.TemporaryDirectory() as t:
            os.environ["CLAUDE_PROJECT_DIR"] = t
            sd = Path(t) / "skills"
            target = _scaffold_into(sd, f"p-reg-{kind}", "session:x")
            real = Path(t) / "real-registry.json"
            _hidden_registry(real, target)
            supplied = Path(t) / "supplied-registry.json"
            if kind == "symlink":
                supplied.symlink_to(real)
            else:
                os.link(real, supplied)
            code, out = _run(["patch", "--name", f"p-reg-{kind}",
                              "--skills-dir", str(sd),
                              "--old", "## Procedure\ny",
                              "--new", "## Procedure\nFIXED steps",
                              "--rationale", _GOOD_RATIONALE,
                              "--gate-registry", str(supplied),
                              "--held-in-id", "held-in-v1",
                              "--held-out-id", "held-out-v1"])
            assert code == 1 and "invalid hidden gate registry" in out, out
    os.environ.pop("CLAUDE_PROJECT_DIR", None)
    print("ok test_hidden_gate_registry_rejects_symlink_and_hardlink")


def test_hidden_gate_registry_rejects_invalid_or_equal_ids():
    with tempfile.TemporaryDirectory() as t:
        os.environ["CLAUDE_PROJECT_DIR"] = t
        sd = Path(t) / "skills"
        target = _scaffold_into(sd, "p-reg-ids", "session:x")
        registry = Path(t) / "gates.json"
        _hidden_registry(registry, target)
        base = ["patch", "--name", "p-reg-ids", "--skills-dir", str(sd),
                "--old", "## Procedure\ny", "--new", "## Procedure\nFIXED steps",
                "--rationale", _GOOD_RATIONALE, "--gate-registry", str(registry)]
        for held_in, held_out in (("held-in-v1", "held-in-v1"),
                                  ("missing", "held-out-v1"),
                                  ("not an opaque id", "held-out-v1")):
            code, out = _run([*base, "--held-in-id", held_in,
                              "--held-out-id", held_out])
            assert code == 1 and "invalid hidden gate registry" in out, out
    os.environ.pop("CLAUDE_PROJECT_DIR", None)
    print("ok test_hidden_gate_registry_rejects_invalid_or_equal_ids")


def test_hidden_gate_registry_rejects_duplicate_keys_and_nonfinite_constants():
    with tempfile.TemporaryDirectory() as t:
        os.environ["CLAUDE_PROJECT_DIR"] = t
        sd = Path(t) / "skills"
        target = _scaffold_into(sd, "p-reg-json", "session:x")
        registry = Path(t) / "gates.json"
        base = ["patch", "--name", "p-reg-json", "--skills-dir", str(sd),
                "--old", "## Procedure\ny", "--new", "## Procedure\nFIXED steps",
                "--rationale", _GOOD_RATIONALE, "--gate-registry", str(registry),
                "--held-in-id", "held-in-v1", "--held-out-id", "held-out-v1"]
        cases = (
            '{"held-in-v1":["/usr/bin/false"],"held-in-v1":["/usr/bin/true"],'
            '"held-out-v1":["/usr/bin/true"]}',
            '{"held-in-v1":["/usr/bin/false",NaN],'
            '"held-out-v1":["/usr/bin/true"]}',
        )
        for payload in cases:
            registry.write_text(payload, encoding="utf-8")
            code, out = _run(base)
            assert code == 1 and "invalid hidden gate registry" in out, out
        assert "FIXED steps" not in target.read_text(encoding="utf-8")
    os.environ.pop("CLAUDE_PROJECT_DIR", None)
    print("ok test_hidden_gate_registry_rejects_duplicate_keys_and_nonfinite_constants")


def test_hidden_gate_registry_rejects_symlinked_parent_and_parent_substitution():
    with tempfile.TemporaryDirectory() as t:
        os.environ["CLAUDE_PROJECT_DIR"] = t
        sd = Path(t) / "skills"
        target = _scaffold_into(sd, "p-reg-parent", "session:x")
        real_parent = Path(t) / "real-parent"
        real_parent.mkdir()
        registry = real_parent / "gates.json"
        _hidden_registry(registry, target)
        linked_parent = Path(t) / "linked-parent"
        linked_parent.symlink_to(real_parent, target_is_directory=True)
        base = ["patch", "--name", "p-reg-parent", "--skills-dir", str(sd),
                "--old", "## Procedure\ny", "--new", "## Procedure\nFIXED steps",
                "--rationale", _GOOD_RATIONALE, "--held-in-id", "held-in-v1",
                "--held-out-id", "held-out-v1"]
        code, out = _run([*base, "--gate-registry", str(linked_parent / "gates.json")])
        assert code == 1 and "symlink component" in out, out

        replacement = Path(t) / "replacement"
        replacement.mkdir()
        (replacement / "gates.json").write_bytes(registry.read_bytes())

        def substitute_parent(*_args, **_kwargs):
            parked = Path(t) / "parked-parent"
            real_parent.rename(parked)
            real_parent.symlink_to(replacement, target_is_directory=True)
            return 1, ""

        with mock.patch.object(learn, "_run_behavior_gate", side_effect=substitute_parent):
            code2, out2 = _run([*base, "--gate-registry", str(registry)])
        assert code2 == 1 and "registry changed" in out2, out2
        assert "FIXED steps" not in target.read_text(encoding="utf-8")
    os.environ.pop("CLAUDE_PROJECT_DIR", None)
    print("ok test_hidden_gate_registry_rejects_symlinked_parent_and_parent_substitution")


def test_hidden_gate_registry_mutation_fails_closed():
    with tempfile.TemporaryDirectory() as t:
        os.environ["CLAUDE_PROJECT_DIR"] = t
        sd = Path(t) / "skills"
        target = _scaffold_into(sd, "p-reg-mutate", "session:x")
        registry = Path(t) / "gates.json"
        args = _hidden_registry(registry, target)

        def mutate_then_fail(*_args, **_kwargs):
            registry.write_text("{}", encoding="utf-8")
            return 1, ""

        with mock.patch.object(learn, "_run_behavior_gate", side_effect=mutate_then_fail):
            code, out = _run(["patch", "--name", "p-reg-mutate",
                              "--skills-dir", str(sd), "--old", "## Procedure\ny",
                              "--new", "## Procedure\nFIXED steps",
                              "--rationale", _GOOD_RATIONALE, *args])
        assert code == 1 and "registry changed" in out, out
        assert "FIXED steps" not in target.read_text(encoding="utf-8")
    os.environ.pop("CLAUDE_PROJECT_DIR", None)
    print("ok test_hidden_gate_registry_mutation_fails_closed")


def test_hidden_gate_sandbox_denies_registry_fork_network_and_outside_write():
    if learn._gate_process_backend() is None:
        print("ok test_hidden_gate_sandbox_denies_registry_fork_network_and_outside_write (backend unavailable)")
        return
    with tempfile.TemporaryDirectory() as t:
        registry = Path(t) / "secret.json"
        registry.write_text('{"secret":"x"}', encoding="utf-8")
        outside = Path(t) / "outside.txt"
        scripts = [
            f"open({str(registry)!r}).read()",
            "import os; os.fork()",
            "import socket; socket.create_connection(('127.0.0.1', 9), timeout=.1)",
            f"open({str(outside)!r},'w').write('x')",
        ]
        for script in scripts:
            code, out = learn._run_behavior_gate(
                [sys.executable, "-c", script], timeout_seconds=1,
                output_limit_bytes=256, denied_read_paths=(registry,), hide_output=True)
            assert code != 0, (script, code, out)
            assert str(registry) not in out and script not in out, out
        assert not outside.exists()
    print("ok test_hidden_gate_sandbox_denies_registry_fork_network_and_outside_write")


def test_hidden_gate_timeout_and_output_are_bounded_without_leakage():
    secret = "HIDDEN_GATE_OUTPUT_SECRET_99"
    for script, expected in (("import time; time.sleep(1)", "timed out"),
                             (f"print({secret!r}*1000)", "output exceeded")):
        code, out = learn._run_behavior_gate(
            [sys.executable, "-c", script], timeout_seconds=.05,
            output_limit_bytes=64, hide_output=True)
        assert code is None and expected in out, out
        assert secret not in out and script not in out, out
    print("ok test_hidden_gate_timeout_and_output_are_bounded_without_leakage")


def test_gate_timeout_rejects_nonfinite_and_above_hard_max_before_spawn():
    with mock.patch.object(learn.subprocess, "Popen") as popen:
        for timeout in (float("nan"), float("inf"), float("-inf"), 0,
                        learn.MAX_GATE_TIMEOUT_SECONDS + 1):
            code, out = learn._run_behavior_gate(
                [sys.executable, "-c", "raise SystemExit(0)"],
                timeout_seconds=timeout, output_limit_bytes=64)
            assert code is None and "finite" in out and "maximum" in out, (timeout, out)
        popen.assert_not_called()
    with tempfile.TemporaryDirectory() as t:
        os.environ["CLAUDE_PROJECT_DIR"] = t
        sd = Path(t) / "skills"
        target = _scaffold_into(sd, "p-timeout-cli", "session:x")
        for text in ("nan", "inf"):
            code, out = _run([
                "patch", "--name", "p-timeout-cli", "--skills-dir", str(sd),
                "--old", "## Procedure\ny", "--new", "## Procedure\nFIXED steps",
                "--rationale", _GOOD_RATIONALE, *_behavior_args(target, "FIXED steps"),
                "--gate-timeout-seconds", text])
            assert code == 1 and "gate timeout must be finite" in out, out
            assert "FIXED steps" not in target.read_text(encoding="utf-8")
    os.environ.pop("CLAUDE_PROJECT_DIR", None)
    print("ok test_gate_timeout_rejects_nonfinite_and_above_hard_max_before_spawn")


def _checkpoint_outcomes(telemetry) -> list[str]:
    return [record["outcome"] for record in telemetry._records(False)]


def _assert_regular_restored(path: Path, expected_bytes: bytes, expected_mode: int) -> None:
    actual = path.lstat()
    assert stat.S_ISREG(actual.st_mode) and not path.is_symlink(), actual
    assert path.read_bytes() == expected_bytes
    assert stat.S_IMODE(actual.st_mode) == expected_mode


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
                          "--old", "UNIQUE_TOKEN_QQ here", "--new", "z", "--rationale", "stuff",
                          *_behavior_args(out_path, "z")])
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
                          "--rationale", _GOOD_RATIONALE,
                          *_behavior_args(out_path, "STEP_BETA runs first.")])
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
                          "--rationale", _GOOD_RATIONALE,
                          *_behavior_args(path, "## Gone")])
        assert code == 1 and "restored exact original bytes" in out.lower(), out
        assert path.read_text() == orig
    os.environ.pop("CLAUDE_PROJECT_DIR", None)
    print("ok test_patch_reverts_on_lint_break")


def test_patch_refuses_wrong_baseline_shape():
    with tempfile.TemporaryDirectory() as t:
        os.environ["CLAUDE_PROJECT_DIR"] = t
        sd = Path(t) / "skills"
        path = _scaffold_into(sd, "p4", "session:x")
        original = path.read_bytes()
        # Held-in passing before mutation means the claimed bug is not reproduced.
        code, out = _run(["patch", "--name", "p4", "--skills-dir", str(sd),
                          "--old", "## Procedure\ny", "--new", "## Procedure\nFIXED steps",
                          "--rationale", _GOOD_RATIONALE,
                          "--held-in-cmd", _contains_gate(path, "## Procedure\ny"),
                          "--held-out-cmd", _exit_gate(0)])
        assert code == 1 and "held-in baseline must fail" in out, out
        assert path.read_bytes() == original
        # Held-out failing before mutation means the regression baseline is invalid.
        code2, out2 = _run(["patch", "--name", "p4", "--skills-dir", str(sd),
                            "--old", "## Procedure\ny", "--new", "## Procedure\nFIXED steps",
                            "--rationale", _GOOD_RATIONALE,
                            "--held-in-cmd", _contains_gate(path, "FIXED steps"),
                            "--held-out-cmd", _exit_gate(1)])
        assert code2 == 1 and "held-out baseline must pass" in out2, out2
        assert path.read_bytes() == original
    os.environ.pop("CLAUDE_PROJECT_DIR", None)
    print("ok test_patch_refuses_wrong_baseline_shape")


def test_patch_reverts_when_held_in_still_fails():
    with tempfile.TemporaryDirectory() as t:
        os.environ["CLAUDE_PROJECT_DIR"] = t
        sd = Path(t) / "skills"
        path = _scaffold_into(sd, "p5", "session:x")
        original = path.read_bytes()
        code, out = _run(["patch", "--name", "p5", "--skills-dir", str(sd),
                          "--old", "## Procedure\ny", "--new", "## Procedure\nFIXED steps",
                          "--rationale", _GOOD_RATIONALE,
                          "--held-in-cmd", _exit_gate(1),
                          "--held-out-cmd", _exit_gate(0)])
        assert code == 1 and "held-in still fails" in out, out
        assert path.read_bytes() == original
    os.environ.pop("CLAUDE_PROJECT_DIR", None)
    print("ok test_patch_reverts_when_held_in_still_fails")


def test_patch_reverts_on_held_out_regression():
    with tempfile.TemporaryDirectory() as t:
        os.environ["CLAUDE_PROJECT_DIR"] = t
        sd = Path(t) / "skills"
        path = _scaffold_into(sd, "p6", "session:x")
        original = path.read_bytes()
        code, out = _run(["patch", "--name", "p6", "--skills-dir", str(sd),
                          "--old", "## Procedure\ny", "--new", "## Procedure\nFIXED steps",
                          "--rationale", _GOOD_RATIONALE,
                          "--held-in-cmd", _contains_gate(path, "FIXED steps"),
                          "--held-out-cmd", _contains_gate(path, "FIXED steps", present=False)])
        assert code == 1 and "held-out regressed" in out, out
        assert path.read_bytes() == original
    os.environ.pop("CLAUDE_PROJECT_DIR", None)
    print("ok test_patch_reverts_on_held_out_regression")


def test_patch_rollback_is_byte_exact():
    with tempfile.TemporaryDirectory() as t:
        os.environ["CLAUDE_PROJECT_DIR"] = t
        sd = Path(t) / "skills"
        path = _scaffold_into(sd, "p7", "session:x")
        path.write_bytes(path.read_bytes().replace(b"\n", b"\r\n"))
        original = path.read_bytes()
        code, out = _run(["patch", "--name", "p7", "--skills-dir", str(sd),
                          "--old", "## Procedure", "--new", "## Procedure changed",
                          "--rationale", _GOOD_RATIONALE,
                          "--held-in-cmd", _exit_gate(1),
                          "--held-out-cmd", _exit_gate(0)])
        assert code == 1 and "restored exact original bytes" in out, out
        assert path.read_bytes() == original
    os.environ.pop("CLAUDE_PROJECT_DIR", None)
    print("ok test_patch_rollback_is_byte_exact")


def test_patch_partial_initial_write_rolls_back_exactly():
    with tempfile.TemporaryDirectory() as t:
        os.environ["CLAUDE_PROJECT_DIR"] = t
        sd = Path(t) / "skills"
        path = _scaffold_into(sd, "p-partial", "session:x")
        original = path.read_bytes()
        path_type = type(path)
        real_write_text = path_type.write_text

        def partial_then_raise(self, data, *args, **kwargs):
            if self == path:
                self.write_bytes(data.encode("utf-8")[:23])
                raise OSError("injected partial candidate write")
            return real_write_text(self, data, *args, **kwargs)

        with mock.patch.object(path_type, "write_text", partial_then_raise):
            code, out = _run(["patch", "--name", "p-partial", "--skills-dir", str(sd),
                              "--old", "## Procedure\ny",
                              "--new", "## Procedure\nFIXED steps",
                              "--rationale", _GOOD_RATIONALE,
                              "--held-in-cmd", _contains_gate(path, "FIXED steps"),
                              "--held-out-cmd", _exit_gate(0)])
        assert code == 1 and "injected partial candidate write" in out, out
        assert path.read_bytes() == original
    os.environ.pop("CLAUDE_PROJECT_DIR", None)
    print("ok test_patch_partial_initial_write_rolls_back_exactly")


def test_partial_checkpoint_interleaving_preserves_concurrent_append():
    """A failed SQLite transaction rolls back only its checkpoint; a concurrent
    writer commits after the transaction releases. Cover empty and populated DBs."""
    for preexisting in (False, True):
        with tempfile.TemporaryDirectory() as t:
            os.environ["CLAUDE_PROJECT_DIR"] = t
            sys.path.insert(0, str(Path(__file__).resolve().parent))
            import telemetry
            sd = Path(t) / "skills"
            path = _scaffold_into(sd, "p-transaction", "session:x")
            if preexisting:
                telemetry.main(["record", "--skill", "original", "--outcome", "hit"])
            original_skill = path.read_bytes()
            marker = Path(t) / "child-ready"
            children = []

            def failed_insert_then_interleave(conn, record):
                child_script = (
                    "import sys; from pathlib import Path; "
                    f"sys.path.insert(0, {str(Path(__file__).resolve().parent)!r}); "
                    "import telemetry; "
                    f"Path({str(marker)!r}).write_text('ready'); "
                    "raise SystemExit(telemetry.main(['record','--skill','concurrent',"
                    "'--outcome','hit']))"
                )
                child = subprocess.Popen(
                    [sys.executable, "-c", child_script], stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE, text=True, env=os.environ.copy())
                children.append(child)
                deadline = time.monotonic() + 2
                while not marker.exists() and time.monotonic() < deadline:
                    time.sleep(0.01)
                assert marker.exists(), "concurrent writer did not start"
                time.sleep(0.05)
                assert child.poll() is None, "concurrent writer bypassed SQLite transaction"
                raise OSError("injected checkpoint transaction failure")

            with mock.patch.object(telemetry, "_insert_event", failed_insert_then_interleave):
                code, out = _run(["patch", "--name", "p-transaction",
                                  "--skills-dir", str(sd),
                                  "--old", "## Procedure\ny",
                                  "--new", "## Procedure\nFIXED steps",
                                  "--rationale", _GOOD_RATIONALE,
                                  "--held-in-cmd", _contains_gate(path, "FIXED steps"),
                                  "--held-out-cmd", _exit_gate(0)])
            assert len(children) == 1
            child_out, child_err = children[0].communicate(timeout=5)
            assert children[0].returncode == 0, (child_out, child_err)
            assert code == 1 and "injected checkpoint transaction failure" in out, out
            assert path.read_bytes() == original_skill
            records = telemetry._records(False)
            assert [record["skill"] for record in records] == (
                ["original", "concurrent"] if preexisting else ["concurrent"]), records
            assert all(record["outcome"] != "checkpoint" for record in records)
    os.environ.pop("CLAUDE_PROJECT_DIR", None)
    print("ok test_partial_checkpoint_interleaving_preserves_concurrent_append")


def test_patch_gate_timeout_is_controlled_and_bounded():
    with tempfile.TemporaryDirectory() as t:
        os.environ["CLAUDE_PROJECT_DIR"] = t
        sd = Path(t) / "skills"
        path = _scaffold_into(sd, "p-timeout", "session:x")
        original = path.read_bytes()
        sleeper = (f"{shlex.quote(sys.executable)} -c "
                   f"{shlex.quote('import time; time.sleep(2)')}")
        started = time.monotonic()
        code, out = _run(["patch", "--name", "p-timeout", "--skills-dir", str(sd),
                          "--old", "## Procedure\ny", "--new", "## Procedure\nFIXED steps",
                          "--rationale", _GOOD_RATIONALE,
                          "--held-in-cmd", sleeper, "--held-out-cmd", _exit_gate(0),
                          "--gate-timeout-seconds", "0.05"])
        elapsed = time.monotonic() - started
        assert code == 1 and "timed out after 0.05 seconds" in out, out
        assert elapsed < 1.5, elapsed
        assert "Traceback" not in out
        assert path.read_bytes() == original
    os.environ.pop("CLAUDE_PROJECT_DIR", None)
    print("ok test_patch_gate_timeout_is_controlled_and_bounded")


def test_patch_gate_output_is_capped():
    with tempfile.TemporaryDirectory() as t:
        os.environ["CLAUDE_PROJECT_DIR"] = t
        sd = Path(t) / "skills"
        path = _scaffold_into(sd, "p-output", "session:x")
        original = path.read_bytes()
        noisy_script = "import sys; print('X' * 100000); raise SystemExit(1)"
        noisy = f"{shlex.quote(sys.executable)} -c {shlex.quote(noisy_script)}"
        code, out = _run(["patch", "--name", "p-output", "--skills-dir", str(sd),
                          "--old", "## Procedure\ny", "--new", "## Procedure\nFIXED steps",
                          "--rationale", _GOOD_RATIONALE,
                          "--held-in-cmd", _contains_gate(path, "FIXED steps"),
                          "--held-out-cmd", noisy,
                          "--gate-output-limit-bytes", "64"])
        assert code == 1 and "output exceeded 64 bytes; process group terminated" in out, out
        assert len(out) < 512, len(out)
        assert path.read_bytes() == original
    os.environ.pop("CLAUDE_PROJECT_DIR", None)
    print("ok test_patch_gate_output_is_capped")


def test_gate_refuses_unsupported_process_backend_before_spawn():
    with mock.patch.object(learn, "_gate_process_backend", return_value=None), \
            mock.patch.object(learn.subprocess, "Popen") as popen:
        code, out = learn._run_behavior_gate(
            _exit_gate(0), timeout_seconds=1, output_limit_bytes=64)
    assert code is None and "unsupported gate isolation backend" in out, out
    popen.assert_not_called()
    print("ok test_gate_refuses_unsupported_process_backend_before_spawn")


def test_gate_clean_parent_exit_kills_posix_descendants():
    with tempfile.TemporaryDirectory() as t:
        marker = Path(t) / "descendant-survived"
        child = ("import time; from pathlib import Path; time.sleep(0.25); "
                 f"Path({str(marker)!r}).write_text('alive')")
        parent = ("import subprocess,sys,time; "
                  f"subprocess.Popen([sys.executable,'-c',{child!r}]); raise SystemExit(0)")
        command = f"{shlex.quote(sys.executable)} -c {shlex.quote(parent)}"
        # Bypass the write sandbox only to exercise the process-group cleanup
        # primitive against the exact direct-parent-exits regression.
        with mock.patch.object(learn, "_gate_process_backend", return_value="test"), \
                mock.patch.object(learn, "_sandbox_gate_argv",
                                  side_effect=lambda backend, argv, root: argv):
            code, out = learn._run_behavior_gate(
                command, timeout_seconds=1, output_limit_bytes=64)
        time.sleep(0.35)
        assert code == 0, out
        assert not marker.exists(), "gate descendant survived clean parent exit"
    print("ok test_gate_clean_parent_exit_kills_posix_descendants")


def test_gate_output_cap_kills_descendant_group():
    with tempfile.TemporaryDirectory() as t:
        marker = Path(t) / "noisy-descendant-survived"
        child = ("import os,time; from pathlib import Path; os.write(1,b'X'*100000); "
                 f"time.sleep(.25); Path({str(marker)!r}).write_text('alive')")
        parent = ("import subprocess,sys,time; "
                  f"subprocess.Popen([sys.executable,'-c',{child!r}]); time.sleep(2)")
        command = f"{shlex.quote(sys.executable)} -c {shlex.quote(parent)}"
        with mock.patch.object(learn, "_gate_process_backend", return_value="test"), \
                mock.patch.object(learn, "_sandbox_gate_argv",
                                  side_effect=lambda backend, argv, root: argv):
            code, out = learn._run_behavior_gate(
                command, timeout_seconds=1, output_limit_bytes=64)
        time.sleep(0.35)
        assert code is None and "output exceeded 64 bytes" in out, out
        assert not marker.exists(), "output-capped descendant survived group cleanup"
    print("ok test_gate_output_cap_kills_descendant_group")


def test_patch_refuses_initial_hardlink_target():
    with tempfile.TemporaryDirectory() as t:
        os.environ["CLAUDE_PROJECT_DIR"] = t
        sd = Path(t) / "skills"
        path = _scaffold_into(sd, "p-initial-hardlink", "session:x")
        alias = Path(t) / "skill-alias.md"
        os.link(path, alias)
        original = path.read_bytes()
        code, out = _run(["patch", "--name", "p-initial-hardlink",
                          "--skills-dir", str(sd),
                          "--old", "## Procedure\ny", "--new", "## Procedure\nFIXED steps",
                          "--rationale", _GOOD_RATIONALE,
                          *_behavior_args(path, "FIXED steps")])
        assert code == 1 and "must not be hardlinked" in out, out
        assert path.read_bytes() == alias.read_bytes() == original
    os.environ.pop("CLAUDE_PROJECT_DIR", None)
    print("ok test_patch_refuses_initial_hardlink_target")


def test_patch_sandbox_blocks_detached_hardlink_watcher():
    if learn._gate_process_backend() is None:
        print("ok test_patch_sandbox_blocks_detached_hardlink_watcher (backend unavailable)")
        return
    with tempfile.TemporaryDirectory() as t:
        os.environ["CLAUDE_PROJECT_DIR"] = t
        import telemetry
        sd = Path(t) / "skills"
        path = _scaffold_into(sd, "p-detached-watcher", "session:x")
        alias = Path(t) / "late-hardlink.md"
        child = ("import os,time; time.sleep(.2); "
                 f"os.link({str(path)!r},{str(alias)!r})")
        parent = (
            "import subprocess,sys; "
            "\ntry: subprocess.Popen([sys.executable,'-c'," + repr(child)
            + "],start_new_session=True)\nexcept Exception: pass\nraise SystemExit(0)"
        )
        watcher = f"{shlex.quote(sys.executable)} -c {shlex.quote(parent)}"
        code, out = _run(["patch", "--name", "p-detached-watcher",
                          "--skills-dir", str(sd),
                          "--old", "## Procedure\ny", "--new", "## Procedure\nFIXED steps",
                          "--rationale", _GOOD_RATIONALE,
                          "--held-in-cmd", _contains_gate(path, "FIXED steps"),
                          "--held-out-cmd", watcher])
        time.sleep(0.3)
        assert code == 0 and "PATCHED" in out, out
        assert not alias.exists(), "sandboxed gate created a detached hardlink"
        assert path.stat().st_nlink == 1
        assert "checkpoint" in _checkpoint_outcomes(telemetry)
    os.environ.pop("CLAUDE_PROJECT_DIR", None)
    print("ok test_patch_sandbox_blocks_detached_hardlink_watcher")


def test_patch_refuses_hardlink_during_metadata_rewrite_before_checkpoint():
    with tempfile.TemporaryDirectory() as t:
        os.environ["CLAUDE_PROJECT_DIR"] = t
        import telemetry
        sd = Path(t) / "skills"
        path = _scaffold_into(sd, "p-metadata-hardlink", "session:x")
        alias = Path(t) / "metadata-alias.md"
        original = path.read_bytes()
        original_mode = stat.S_IMODE(path.stat().st_mode)
        real_rewrite = learn._rewrite_frontmatter

        def link_then_rewrite(target, updates):
            os.link(target, alias)
            return real_rewrite(target, updates)

        with mock.patch.object(learn, "_rewrite_frontmatter", side_effect=link_then_rewrite):
            code, out = _run(["patch", "--name", "p-metadata-hardlink",
                              "--skills-dir", str(sd),
                              "--old", "## Procedure\ny",
                              "--new", "## Procedure\nFIXED steps",
                              "--rationale", _GOOD_RATIONALE,
                              *_behavior_args(path, "FIXED steps")])
        assert code == 1 and "hardlinked" in out, out
        _assert_regular_restored(path, original, original_mode)
        assert "checkpoint" not in _checkpoint_outcomes(telemetry)
    os.environ.pop("CLAUDE_PROJECT_DIR", None)
    print("ok test_patch_refuses_hardlink_during_metadata_rewrite_before_checkpoint")


def test_patch_rolls_back_checkpoint_if_hardlink_appears_during_append():
    with tempfile.TemporaryDirectory() as t:
        os.environ["CLAUDE_PROJECT_DIR"] = t
        import telemetry
        sd = Path(t) / "skills"
        path = _scaffold_into(sd, "p-checkpoint-hardlink", "session:x")
        alias = Path(t) / "checkpoint-alias.md"
        original = path.read_bytes()
        original_mode = stat.S_IMODE(path.stat().st_mode)
        real_append = telemetry._append

        def link_then_append(store, record):
            if record.get("outcome") == "checkpoint":
                os.link(path, alias)
            return real_append(store, record)

        with mock.patch.object(telemetry, "_append", side_effect=link_then_append):
            code, out = _run(["patch", "--name", "p-checkpoint-hardlink",
                              "--skills-dir", str(sd),
                              "--old", "## Procedure\ny",
                              "--new", "## Procedure\nFIXED steps",
                              "--rationale", _GOOD_RATIONALE,
                              *_behavior_args(path, "FIXED steps")])
        assert code == 1 and "across telemetry checkpoint" in out, out
        _assert_regular_restored(path, original, original_mode)
        assert "checkpoint" not in _checkpoint_outcomes(telemetry)
    os.environ.pop("CLAUDE_PROJECT_DIR", None)
    print("ok test_patch_rolls_back_checkpoint_if_hardlink_appears_during_append")


def test_patch_refuses_and_restores_baseline_target_mutation():
    with tempfile.TemporaryDirectory() as t:
        os.environ["CLAUDE_PROJECT_DIR"] = t
        sd = Path(t) / "skills"
        path = _scaffold_into(sd, "p-baseline-mutate", "session:x")
        original = path.read_bytes()
        script = (f"from pathlib import Path; Path({str(path)!r}).write_bytes(b'MUTATED'); "
                  "raise SystemExit(0)")
        mutator = f"{shlex.quote(sys.executable)} -c {shlex.quote(script)}"
        code, out = _run(["patch", "--name", "p-baseline-mutate",
                          "--skills-dir", str(sd),
                          "--old", "## Procedure\ny", "--new", "## Procedure\nFIXED steps",
                          "--rationale", _GOOD_RATIONALE,
                          "--held-in-cmd", mutator, "--held-out-cmd", _exit_gate(0)])
        assert code == 1 and "held-in still fails" in out and "Operation not permitted" in out, out
        assert path.read_bytes() == original
    os.environ.pop("CLAUDE_PROJECT_DIR", None)
    print("ok test_patch_refuses_and_restores_baseline_target_mutation")


def test_patch_refuses_and_restores_post_gate_target_mutation():
    with tempfile.TemporaryDirectory() as t:
        os.environ["CLAUDE_PROJECT_DIR"] = t
        sd = Path(t) / "skills"
        path = _scaffold_into(sd, "p-post-mutate", "session:x")
        original = path.read_bytes()
        script = (
            f"from pathlib import Path; p=Path({str(path)!r}); "
            "text=p.read_text(encoding='utf-8'); fixed='FIXED steps' in text; "
            "p.write_text(text.replace('## Verification','## Gone'), encoding='utf-8') "
            "if fixed else None; raise SystemExit(0 if fixed else 1)"
        )
        mutator = f"{shlex.quote(sys.executable)} -c {shlex.quote(script)}"
        code, out = _run(["patch", "--name", "p-post-mutate", "--skills-dir", str(sd),
                          "--old", "## Procedure\ny", "--new", "## Procedure\nFIXED steps",
                          "--rationale", _GOOD_RATIONALE,
                          "--held-in-cmd", mutator, "--held-out-cmd", _exit_gate(0)])
        assert code == 1 and "held-in still fails" in out and "Operation not permitted" in out, out
        assert path.read_bytes() == original
        assert "## Verification" in path.read_text(encoding="utf-8")
    os.environ.pop("CLAUDE_PROJECT_DIR", None)
    print("ok test_patch_refuses_and_restores_post_gate_target_mutation")


def test_patch_refuses_initial_symlink_target():
    with tempfile.TemporaryDirectory() as t:
        os.environ["CLAUDE_PROJECT_DIR"] = t
        import telemetry
        sd = Path(t) / "skills"
        path = _scaffold_into(sd, "p-initial-symlink", "session:x")
        real_target = Path(t) / "real-skill.md"
        path.replace(real_target)
        original = real_target.read_bytes()
        original_mode = stat.S_IMODE(real_target.stat().st_mode)
        path.symlink_to(real_target)
        code, out = _run(["patch", "--name", "p-initial-symlink",
                          "--skills-dir", str(sd),
                          "--old", "## Procedure\ny", "--new", "## Procedure\nFIXED steps",
                          "--rationale", _GOOD_RATIONALE,
                          *_behavior_args(path, "FIXED steps")])
        assert code == 1 and "regular non-symlink file" in out, out
        assert path.is_symlink()
        assert real_target.read_bytes() == original
        assert stat.S_IMODE(real_target.stat().st_mode) == original_mode
        assert "checkpoint" not in _checkpoint_outcomes(telemetry)
    os.environ.pop("CLAUDE_PROJECT_DIR", None)
    print("ok test_patch_refuses_initial_symlink_target")


def test_patch_restores_baseline_different_byte_symlink_without_following():
    with tempfile.TemporaryDirectory() as t:
        os.environ["CLAUDE_PROJECT_DIR"] = t
        import telemetry
        sd = Path(t) / "skills"
        path = _scaffold_into(sd, "p-baseline-symlink", "session:x")
        path.chmod(0o640)
        original = path.read_bytes()
        original_mode = stat.S_IMODE(path.stat().st_mode)
        symlink_target = Path(t) / "outside.md"
        symlink_target.write_bytes(b"DIFFERENT OUTSIDE BYTES")
        outside_original = symlink_target.read_bytes()
        script = (f"from pathlib import Path; p=Path({str(path)!r}); p.unlink(); "
                  f"p.symlink_to(Path({str(symlink_target)!r})); raise SystemExit(1)")
        mutator = f"{shlex.quote(sys.executable)} -c {shlex.quote(script)}"
        code, out = _run(["patch", "--name", "p-baseline-symlink",
                          "--skills-dir", str(sd),
                          "--old", "## Procedure\ny", "--new", "## Procedure\nFIXED steps",
                          "--rationale", _GOOD_RATIONALE,
                          "--held-in-cmd", mutator, "--held-out-cmd", _exit_gate(0)])
        assert code == 1 and "held-in still fails" in out and "Operation not permitted" in out, out
        _assert_regular_restored(path, original, original_mode)
        assert symlink_target.read_bytes() == outside_original
        assert "checkpoint" not in _checkpoint_outcomes(telemetry)
    os.environ.pop("CLAUDE_PROJECT_DIR", None)
    print("ok test_patch_restores_baseline_different_byte_symlink_without_following")


def test_patch_restores_post_gate_same_byte_symlink_and_inode_replacement():
    for replacement_kind in ("symlink", "regular"):
        with tempfile.TemporaryDirectory() as t:
            os.environ["CLAUDE_PROJECT_DIR"] = t
            import telemetry
            sd = Path(t) / "skills"
            name = f"p-post-{replacement_kind}"
            path = _scaffold_into(sd, name, "session:x")
            path.chmod(0o640)
            original = path.read_bytes()
            original_mode = stat.S_IMODE(path.stat().st_mode)
            replacement = Path(t) / "same-bytes.md"
            action = (
                f"r=Path({str(replacement)!r}); "
                "(r.write_bytes(data), r.chmod(mode), p.unlink(), p.symlink_to(r)) "
                "if fixed else None"
                if replacement_kind == "symlink" else
                "(p.unlink(), p.write_bytes(data), p.chmod(mode)) if fixed else None"
            )
            script = (
                f"from pathlib import Path; p=Path({str(path)!r}); data=p.read_bytes(); "
                "text=data.decode('utf-8'); fixed='FIXED steps' in text; "
                "mode=p.stat().st_mode & 0o7777; "
                f"{action}; "
                "raise SystemExit(0 if fixed else 1)"
            )
            mutator = f"{shlex.quote(sys.executable)} -c {shlex.quote(script)}"
            code, out = _run(["patch", "--name", name, "--skills-dir", str(sd),
                              "--old", "## Procedure\ny",
                              "--new", "## Procedure\nFIXED steps",
                              "--rationale", _GOOD_RATIONALE,
                              "--held-in-cmd", mutator,
                              "--held-out-cmd", _exit_gate(0)])
            assert code == 1 and "held-in still fails" in out and "Operation not permitted" in out, out
            _assert_regular_restored(path, original, original_mode)
            if replacement_kind == "symlink":
                assert not replacement.exists(), "write-denying sandbox leaked replacement file"
            assert "checkpoint" not in _checkpoint_outcomes(telemetry)
    os.environ.pop("CLAUDE_PROJECT_DIR", None)
    print("ok test_patch_restores_post_gate_same_byte_symlink_and_inode_replacement")


def test_patch_restores_post_gate_permission_change():
    with tempfile.TemporaryDirectory() as t:
        os.environ["CLAUDE_PROJECT_DIR"] = t
        import telemetry
        sd = Path(t) / "skills"
        path = _scaffold_into(sd, "p-post-chmod", "session:x")
        path.chmod(0o640)
        original = path.read_bytes()
        original_mode = stat.S_IMODE(path.stat().st_mode)
        script = (
            f"from pathlib import Path; p=Path({str(path)!r}); "
            "fixed='FIXED steps' in p.read_text(encoding='utf-8'); "
            "p.chmod(0o600) if fixed else None; raise SystemExit(0 if fixed else 1)"
        )
        mutator = f"{shlex.quote(sys.executable)} -c {shlex.quote(script)}"
        code, out = _run(["patch", "--name", "p-post-chmod", "--skills-dir", str(sd),
                          "--old", "## Procedure\ny", "--new", "## Procedure\nFIXED steps",
                          "--rationale", _GOOD_RATIONALE,
                          "--held-in-cmd", mutator, "--held-out-cmd", _exit_gate(0)])
        assert code == 1 and "held-in still fails" in out and "Operation not permitted" in out, out
        _assert_regular_restored(path, original, original_mode)
        assert "checkpoint" not in _checkpoint_outcomes(telemetry)
    os.environ.pop("CLAUDE_PROJECT_DIR", None)
    print("ok test_patch_restores_post_gate_permission_change")


def test_refine_excludes_non_addressable_failures():
    with tempfile.TemporaryDirectory() as t:
        os.environ["CLAUDE_PROJECT_DIR"] = t
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        import telemetry
        sd = Path(t) / "skills"
        _scaffold_into(sd, "p8", "session:x")
        telemetry.main(["record", "--skill", "p8", "--outcome", "abort",
                        "--verifier-cause", "input exceeds task budget",
                        "--causal-status", "task-difficulty",
                        "--mechanism", "task is larger than the bounded route",
                        "--evidence-ref", "trace:17"])
        telemetry.main(["record", "--skill", "p8", "--outcome", "abort",
                        "--verifier-cause", "executor lacks required reasoning capacity",
                        "--causal-status", "model-capability",
                        "--evidence-ref", "eval:weak-model"])
        code, out = _run(["refine", "--name", "p8", "--skills-dir", str(sd)])
        assert code == 0 and "NON-ADDRESSABLE" in out, out
        assert "verifier_cause: input exceeds task budget" in out, out
        assert "learn.py patch --name" not in out, out

        _scaffold_into(sd, "p9", "session:x")
        telemetry.main(["record", "--skill", "p9", "--outcome", "abort",
                        "--note", "legacy unstructured abort"])
        code2, out2 = _run(["refine", "--name", "p9", "--skills-dir", str(sd)])
        assert code2 == 0 and "UNCONFIRMED" in out2, out2
        assert "causal_status: unknown" in out2, out2
        assert "learn.py patch --name" not in out2, out2
    os.environ.pop("CLAUDE_PROJECT_DIR", None)
    print("ok test_refine_excludes_non_addressable_failures")


def test_refine_ignores_precheckpoint_skill_caused_evidence():
    with tempfile.TemporaryDirectory() as t:
        os.environ["CLAUDE_PROJECT_DIR"] = t
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        import telemetry
        sd = Path(t) / "skills"
        _scaffold_into(sd, "p-clean-slate", "session:x")
        telemetry.main(["record", "--skill", "p-clean-slate", "--outcome", "abort",
                        "--verifier-cause", "PRECHECKPOINT_CAUSAL_BUG",
                        "--causal-status", "skill-caused"])
        telemetry.main(["record", "--skill", "p-clean-slate",
                        "--outcome", "checkpoint"])
        telemetry.main(["record", "--skill", "p-clean-slate", "--outcome", "abort",
                        "--verifier-cause", "task exceeds bounded route",
                        "--causal-status", "task-difficulty"])
        code, out = _run(["refine", "--name", "p-clean-slate",
                          "--skills-dir", str(sd)])
        assert code == 0 and "NON-ADDRESSABLE" in out, out
        assert "PRECHECKPOINT_CAUSAL_BUG" not in out, out
        assert "learn.py patch --name" not in out, out
    os.environ.pop("CLAUDE_PROJECT_DIR", None)
    print("ok test_refine_ignores_precheckpoint_skill_caused_evidence")


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
    print(f"\nALL {len(fns)} TESTS PASSED")
