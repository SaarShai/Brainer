#!/usr/bin/env python3
"""Smoke tests for cache_lint.py — runnable standalone."""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from cache_lint import audit  # noqa: E402


def _setup(root: Path, files: dict[str, str]) -> None:
    for rel, content in files.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content)


def test_clean_project_passes() -> None:
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        _setup(root, {
            "CLAUDE.md": ("# Project\n\n## Rules\n\nUse type hints. " * 100),
            ".claude/settings.json": json.dumps({"model": "claude-sonnet-4.6"}),
        })
        report = audit(root)
        fails = [f for f in report.findings if f.severity == "FAIL"]
        assert not fails, f"clean project should not FAIL, got: {fails}"


def test_dynamic_content_flagged() -> None:
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        _setup(root, {
            # $(...) substitution + env template are unambiguous; legacy
            # backticks are intentionally not checked (see DYNAMIC_PATTERNS).
            "CLAUDE.md": ("# Project\n\nCurrent date: $(date)\nUser: {{env.USER}}\n" * 20),
        })
        report = audit(root, rule_filter=2)
        flagged = [f for f in report.findings if f.rule == 2 and f.severity == "FAIL"]
        assert flagged, "should flag $(date) and {{env.USER}}"


def test_inline_code_typography_not_flagged() -> None:
    """Plain inline Markdown code is typography, not cache-busting."""
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        _setup(root, {
            "CLAUDE.md": ("# Project\n\n"
                          "See `CLAUDE.md` and `skills/wiki-memory/SKILL.md` for details. "
                          "The `name` field is required. "
                          "Run `./install.sh` to bootstrap.\n" * 30),
        })
        report = audit(root, rule_filter=2)
        rule2 = [f for f in report.findings if f.rule == 2]
        assert not rule2, f"prose inline-code should not be flagged, got: {rule2}"


def test_dynamic_in_code_fence_downgraded() -> None:
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        _setup(root, {
            "CLAUDE.md": "# Project\n\n```bash\necho $(date)\n```\nrest of content " * 50,
        })
        report = audit(root, rule_filter=2)
        fails = [f for f in report.findings if f.rule == 2 and f.severity == "FAIL"]
        warns = [f for f in report.findings if f.rule == 2 and f.severity == "WARN"]
        assert not fails, "dynamic inside fence should not FAIL"
        assert warns, "should still WARN about fenced dynamic content"


def test_tiny_prefix_warns() -> None:
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        _setup(root, {"CLAUDE.md": "# Tiny\n"})
        report = audit(root, rule_filter=5)
        warns = [f for f in report.findings if f.rule == 5]
        assert warns, "tiny CLAUDE.md should WARN about wasted cache slot"


def test_model_switching_warns() -> None:
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        _setup(root, {
            ".claude/settings.json": json.dumps({"model": "claude-haiku-4.6"}),
            ".claude/hooks/triage.json": json.dumps({"model": "claude-sonnet-4.6"}),
        })
        report = audit(root, rule_filter=4)
        warns = [f for f in report.findings if f.rule == 4]
        assert warns, "multi-model setup should WARN"


def test_fork_safety_fails_on_stop_hook_mutating_prefix() -> None:
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        _setup(root, {
            ".claude/settings.json": json.dumps({
                "hooks": {
                    "Stop": [{"command": "echo done >> CLAUDE.md"}],
                }
            })
        })
        report = audit(root, rule_filter=6)
        fails = [f for f in report.findings if f.rule == 6 and f.severity == "FAIL"]
        assert fails, "Stop hook writing CLAUDE.md should FAIL"


def test_rule6_read_only_is_not_flagged() -> None:
    """REGRESSION: any mention of CLAUDE.md (even `grep CLAUDE.md`) used to FAIL."""
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        _setup(root, {
            ".claude/settings.json": json.dumps({
                "hooks": {
                    "Stop": [{"command": "grep TODO CLAUDE.md || true"}],
                    "SessionEnd": [{"command": "cat AGENTS.md"}],
                }
            })
        })
        report = audit(root, rule_filter=6)
        fails = [f for f in report.findings if f.rule == 6 and f.severity == "FAIL"]
        assert not fails, f"read-only commands must not FAIL rule 6: {fails}"


def test_rule6_actual_write_still_flagged() -> None:
    """Companion to the read-only test: real writes must still fire."""
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        _setup(root, {
            ".claude/settings.json": json.dumps({
                "hooks": {
                    "Stop": [{"command": "echo done >> CLAUDE.md"}],
                }
            })
        })
        report = audit(root, rule_filter=6)
        fails = [f for f in report.findings if f.rule == 6 and f.severity == "FAIL"]
        assert fails, "actual `>> CLAUDE.md` write must still FAIL"


def test_rule6_follows_invoked_script() -> None:
    """REGRESSION: external agent found Rule 6 missed `python scripts/foo.py` that writes inside."""
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        _setup(root, {
            ".claude/settings.json": json.dumps({
                "hooks": {
                    "UserPromptSubmit": [{"command": "python3 scripts/reflect.py"}],
                }
            }),
            "scripts/reflect.py": (
                "import pathlib\n"
                "p = pathlib.Path('CLAUDE.md')\n"
                "p.write_text('updated\\n')\n"
            ),
        })
        report = audit(root, rule_filter=6)
        fails = [f for f in report.findings if f.rule == 6 and f.severity == "FAIL"]
        assert fails, "Rule 6 should follow invoked scripts and find writes inside"
        assert any("reflect.py" in f.file for f in fails), \
            f"finding should cite the script, not the json: {fails}"


def test_discovery_finds_nested_hooks_and_plugins() -> None:
    """REGRESSION: external agent found discovery missed nested `hooks/hooks.json` etc."""
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        _setup(root, {
            "CLAUDE.md": "# Root project\n\n" + ("Content. " * 200),
            "plugins/myplugin/hooks/hooks.json": json.dumps({"hooks": {"Stop": []}}),
            "subproject/CLAUDE.md": "# Sub\n\n" + ("Content. " * 200),
            ".claude-plugin/plugin.json": json.dumps({"name": "x"}),
        })
        from cache_lint import discover
        targets = [str(p) for p in discover(root)]
        assert any("plugins/myplugin/hooks/hooks.json" in t for t in targets), f"nested hooks.json not discovered: {targets}"
        assert any("subproject/CLAUDE.md" in t for t in targets), f"nested CLAUDE.md not discovered: {targets}"
        assert any(".claude-plugin/plugin.json" in t for t in targets), f".claude-plugin not discovered: {targets}"


def test_discovery_skips_node_modules() -> None:
    """Recursive glob must not descend into node_modules / venv / etc."""
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        _setup(root, {
            "CLAUDE.md": "# Root\n\n" + ("X. " * 300),
            "node_modules/some-pkg/CLAUDE.md": "# nope\n",
            ".git/CLAUDE.md": "# nope\n",
        })
        from cache_lint import discover
        targets = [str(p) for p in discover(root)]
        assert not any("node_modules" in t for t in targets), targets
        assert not any("/.git/" in t for t in targets), targets


def test_sizing_thresholds_match_docs() -> None:
    """SKILL.md promises 1K / 4K cutoffs — code must match."""
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        # 1024 tokens × 4 chars ≈ 4096 bytes; pick something between the old
        # broken threshold (256) and the documented one (1024) to catch regression.
        body = "x" * (700 * 4)  # ~700 tokens — should WARN under documented 1024 cutoff
        _setup(root, {"CLAUDE.md": body})
        report = audit(root, rule_filter=5)
        warns = [f for f in report.findings if f.rule == 5]
        assert warns, f"700-token CLAUDE.md should WARN under documented 1K cutoff, got: {report.findings}"


def test_fingerprint_refused_in_non_claude_project() -> None:
    """REGRESSION: cache-lint used to write .cache-lint-fingerprint.json into
    any --root, even when it didn't look like a Claude Code project. Now refuses.

    Setup: dir with a `.claude-plugin/marketplace.json` (so discovery finds
    something) but NO Claude Code project markers (no CLAUDE.md / .claude/ /
    skills/). The fingerprint should NOT be written. We deliberately remove
    the .claude-plugin/ before checking the marker, leaving only the discovered
    file behind."""
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        # Setup: a CLAUDE.md buried in a subdir that discover() walks
        # via the **/CLAUDE.md glob. Discovery finds something, audit proceeds,
        # but root itself isn't Claude-shaped → check_ordering_and_tools must
        # refuse to write the fingerprint here.
        sub = root / "some_other_project"
        sub.mkdir(parents=True)
        (sub / "CLAUDE.md").write_text("# nested\n" + ("rules. " * 200))
        # No CLAUDE.md / AGENTS.md / GEMINI.md / .claude/ / .claude-plugin/ /
        # skills/ at ROOT — so _is_claude_code_project(root) is False.
        # NB: this exercises the case where --root is misaimed at a parent dir
        # of an actual project, or at a junk dir.

        # The discover walks recursively and finds the settings.json. Audit runs.
        # Rule 1 / 3 check_ordering_and_tools must refuse to write a fingerprint
        # into `root` because root itself isn't Claude-shaped.
        report = audit(root, rule_filter=1)
        assert not (root / ".cache-lint-fingerprint.json").exists(), \
            "must not write fingerprint into non-project root"
        warns = [f for f in report.findings if f.rule == 1 and f.severity == "WARN"]
        assert warns, f"should WARN about skipping fingerprint; got {report.findings}"


def test_fingerprint_baseline_creates_then_detects_change() -> None:
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        _setup(root, {
            "skills/foo/SKILL.md": "---\nname: foo\ndescription: First desc. Use when X.\n---\n# Foo\n",
        })
        # first run creates baseline
        report1 = audit(root, rule_filter=1)
        assert any(f.rule == 1 and "initialized" in f.title for f in report1.findings)
        # mutate description
        (root / "skills/foo/SKILL.md").write_text(
            "---\nname: foo\ndescription: Different desc entirely. Use when Y.\n---\n# Foo\n"
        )
        report2 = audit(root, rule_filter=1)
        warns = [f for f in report2.findings if f.rule == 3]
        assert warns, "changed skill description should WARN on rule 3"


def test_rule6_non_dict_settings_does_not_crash() -> None:
    """REGRESSION: a valid-JSON-but-non-dict settings.json (top-level list/
    string/number/null) used to raise AttributeError on `data.get("hooks")`
    and abort the ENTIRE audit. Must skip the file and finish cleanly."""
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        _setup(root, {
            "CLAUDE.md": "# Project\n\n" + ("Content. " * 300),
            # valid JSON, but the top level is a list — has no "hooks" key
            ".claude/settings.json": "[1, 2, 3]",
            # a real Stop-hook write elsewhere must still be caught after the
            # non-dict file is skipped (audit must not abort)
            ".claude/hooks/bad.json": json.dumps({
                "hooks": {"Stop": [{"command": "echo done >> CLAUDE.md"}]}
            }),
        })
        report = audit(root, rule_filter=6)  # must not raise
        fails = [f for f in report.findings if f.rule == 6 and f.severity == "FAIL"]
        assert fails, "audit must survive the non-dict file and still flag the real write"


def test_rule2_inline_triple_backtick_does_not_downgrade() -> None:
    """REGRESSION: a single stray INLINE ``` run used to flip global fence
    parity, downgrading a genuine top-level $(…) cache-bust from FAIL to WARN
    (and CI exit 2 -> 1, slipping past a fail-only gate). Only line-leading
    ``` markers may toggle fence state."""
    dollar = chr(36)
    triple = chr(96) * 3
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        _setup(root, {
            "CLAUDE.md": (
                "# Project\n\n"
                "Prose with an inline stray " + triple + " marker mid-sentence.\n\n"
                "Real top-level cache-bust: " + dollar + "(date)\n"
                + ("\nPadding line. " * 400)
            ),
        })
        report = audit(root, rule_filter=2)
        fails = [f for f in report.findings if f.rule == 2 and f.severity == "FAIL"]
        assert fails, "genuine top-level $(…) after an inline ``` must FAIL, not WARN"


def test_rule6_interpreter_flags_and_bare_relative_paths() -> None:
    """REGRESSION: SCRIPT_INVOKE_RE missed `python3 -u scripts/x.py` (flags
    between interpreter and script) and bare relative paths like
    `.claude/hooks/run.sh` — a prefix-writing hot-path hook went undetected."""
    # Variant A: interpreter with a flag before the script.
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        _setup(root, {
            ".claude/settings.json": json.dumps({
                "hooks": {"UserPromptSubmit": [{"command": "python3 -u scripts/reflect.py"}]},
            }),
            "scripts/reflect.py": (
                "import pathlib\n"
                "p = pathlib.Path('CLAUDE.md')\n"
                "p.write_text('updated\\n')\n"
            ),
        })
        report = audit(root, rule_filter=6)
        fails = [f for f in report.findings if f.rule == 6 and f.severity == "FAIL"]
        assert fails, "`python3 -u scripts/x.py` write must be detected"
        assert any("reflect.py" in f.file for f in fails), f"should cite the script: {fails}"

    # Variant B: bare relative direct-invocation path (no ./ prefix, no interpreter).
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        _setup(root, {
            ".claude/settings.json": json.dumps({
                "hooks": {"Stop": [{"command": ".claude/hooks/run.sh"}]},
            }),
            ".claude/hooks/run.sh": "#!/bin/bash\necho done >> CLAUDE.md\n",
        })
        report = audit(root, rule_filter=6)
        fails = [f for f in report.findings if f.rule == 6 and f.severity == "FAIL"]
        assert fails, "bare relative `.claude/hooks/run.sh` write must be detected"


def test_rule2_cap_is_per_pattern_and_skips_typography() -> None:
    """REGRESSION: the per-file cap was shared across all 9 patterns AND ran
    before the inline-code skip. Result: once $(…) hit the cap, distinct
    classes (wall-clock, ${ENV}, RNG) were wholly suppressed, and backticked
    typography after the cap was miscounted as suppressed real findings."""
    dollar = chr(36)
    bt = chr(96)
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        lines = ["# Project", ""]
        for i in range(6):  # 6 genuine $(…) — one over the cap of 5
            lines.append(f"Bust {i}: {dollar}(date)")
        for i in range(20):  # backticked typography — must be SKIPPED, not suppressed
            lines.append(f"Example: {bt}{dollar}(date){bt}")
        # distinct classes that must still emit despite $(…) hitting the cap
        lines.append("Wall clock: datetime.now()")
        lines.append("Env: " + dollar + "{HOME}")
        lines.append("RNG: " + dollar + "RANDOM")
        _setup(root, {"CLAUDE.md": "\n".join(lines) + "\n" + ("Padding. " * 400)})
        report = audit(root, rule_filter=2)
        titles = {f.title for f in report.findings if f.rule == 2 and f.severity == "FAIL"}
        assert any("wall-clock" in t for t in titles), f"wall-clock must still emit: {titles}"
        assert any("braced env" in t for t in titles), f"${{ENV}} must still emit: {titles}"
        assert any("RNG" in t for t in titles), f"RNG must still emit: {titles}"
        # suppressed summary must count only the 1 over-cap genuine match, not the 20 typography
        supp = [f for f in report.findings if f.rule == 2 and "suppressed" in f.title]
        assert len(supp) == 1, f"exactly one pattern over cap: {[f.title for f in supp]}"
        assert " +1 " in (" " + supp[0].title + " "), \
            f"only the 6th genuine $(…) is suppressed, not typography: {supp[0].title}"


def test_rule3_detects_block_scalar_description_drift() -> None:
    """REGRESSION: for a YAML block scalar (`description: >` / `|`) the old
    `^description:\\s*(.+)$` capture was just ">"/"|" (constant), so multi-line
    description edits never re-keyed the cache. Continuation lines must be
    folded into the fingerprint."""
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        _setup(root, {
            "skills/foo/SKILL.md": (
                "---\nname: foo\ndescription: >\n"
                "  First multiline description.\n  Use when X happens.\n---\n# Foo\n"
            ),
        })
        report1 = audit(root, rule_filter=1)
        assert any(f.rule == 1 and "initialized" in f.title for f in report1.findings)
        # mutate only the indented continuation; the `>` marker line is unchanged
        (root / "skills/foo/SKILL.md").write_text(
            "---\nname: foo\ndescription: >\n"
            "  Completely different multiline text.\n  Use when Y happens.\n---\n# Foo\n"
        )
        report2 = audit(root, rule_filter=1)
        warns = [f for f in report2.findings if f.rule == 3]
        assert warns, "changed block-scalar description must WARN on rule 3"


def main() -> int:
    tests = [
        test_clean_project_passes,
        test_dynamic_content_flagged,
        test_inline_code_typography_not_flagged,
        test_dynamic_in_code_fence_downgraded,
        test_tiny_prefix_warns,
        test_model_switching_warns,
        test_fork_safety_fails_on_stop_hook_mutating_prefix,
        test_rule6_read_only_is_not_flagged,
        test_rule6_actual_write_still_flagged,
        test_rule6_follows_invoked_script,
        test_discovery_finds_nested_hooks_and_plugins,
        test_discovery_skips_node_modules,
        test_sizing_thresholds_match_docs,
        test_fingerprint_refused_in_non_claude_project,
        test_fingerprint_baseline_creates_then_detects_change,
        test_rule6_non_dict_settings_does_not_crash,
        test_rule2_inline_triple_backtick_does_not_downgrade,
        test_rule6_interpreter_flags_and_bare_relative_paths,
        test_rule2_cap_is_per_pattern_and_skips_typography,
        test_rule3_detects_block_scalar_description_drift,
    ]
    failed = 0
    for t in tests:
        try:
            t()
            print(f"  ok  {t.__name__}")
        except AssertionError as e:
            failed += 1
            print(f"FAIL  {t.__name__}: {e}")
        except Exception as e:
            failed += 1
            print(f"ERR   {t.__name__}: {type(e).__name__}: {e}")
    if failed:
        print(f"\n{failed}/{len(tests)} failed")
        return 1
    print(f"\nall {len(tests)} passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
