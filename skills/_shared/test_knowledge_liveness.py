#!/usr/bin/env python3
"""Tests for knowledge_liveness.py — plain-python (no pytest dep), runnable
standalone. Shape mirrors skills/loop-engineering/tools/test_loop_lint.py: a
list of test_* functions, a main() that runs them and returns the failure
count (exit 0 == all pass), registered in scripts/run_all_tests.sh.

LEARNING_CONTRACT.md §3: "a gate that has never tripped is unproven." Every
check ships a KNOWN-BAD fixture (built in a temp dir, never touching the real
repo) that the corresponding check must demonstrably reject. A positive-only
suite (only proving the clean repo passes) would not prove any single check
actually fires — these are that missing negative half.
"""
from __future__ import annotations

import os
import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import knowledge_liveness as kl  # noqa: E402


def _make_min_repo(root: Path) -> None:
    """Smallest repo skeleton the checks need: skills/ dir, scripts/ dir with
    the two delegate scripts knowledge_liveness imports (check_wiki_hygiene,
    gen_hooks_map) so those checks don't fail merely for being absent, plus a
    stand-in compliance-canary/tools/hook.py exposing a DETECTORS dict so the
    [gate-schema] kind-liveness check has a set to validate against instead
    of failing merely because the fixture has no real canary hook."""
    (root / "skills").mkdir(parents=True)
    (root / "scripts").mkdir(parents=True)
    # Minimal stand-in check_wiki_hygiene.py: no wiki dir in these fixtures,
    # so a trivial always-pass main() is faithful (nothing to hygiene-check).
    (root / "scripts" / "check_wiki_hygiene.py").write_text(
        "def main() -> int:\n    return 0\n", encoding="utf-8"
    )
    # Minimal stand-in gen_hooks_map.py exposing the one function
    # knowledge_liveness reuses, with an empty inventory (no hook skills in
    # these fixtures).
    (root / "scripts" / "gen_hooks_map.py").write_text(
        "def skill_hook_inventory():\n    return []\n", encoding="utf-8"
    )
    # Minimal stand-in compliance-canary hook.py exposing the same DETECTORS
    # shape the real hook.py builds (dict[str, callable]), covering every
    # kind used by the real repo's drift_probes.json fixtures below.
    canary_tools = root / "skills" / "compliance-canary" / "tools"
    canary_tools.mkdir(parents=True)
    (canary_tools / "hook.py").write_text(
        "def _noop(*a, **k):\n    return None\n\n"
        "DETECTORS = {\n"
        "    'forbidden_regex': _noop,\n"
        "    'word_count_per_message': _noop,\n"
        "    'claim_without_evidence': _noop,\n"
        "}\n",
        encoding="utf-8",
    )


def _run(root: Path):
    return kl.run(repo_root=root)


# --- (a) gate JSON parse-ability -------------------------------------------

def test_broken_drift_probes_json_trips():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        _make_min_repo(root)
        skill = root / "skills" / "broken-skill"
        skill.mkdir()
        (skill / "drift_probes.json").write_text("{not valid json,,,", encoding="utf-8")
        code, errors, _warnings = _run(root)
        assert code == 2, (code, errors)
        assert any("[gate-json]" in e and "drift_probes.json" in e for e in errors), errors
        print("ok test_broken_drift_probes_json_trips")


def test_clean_drift_probes_json_does_not_trip():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        _make_min_repo(root)
        skill = root / "skills" / "clean-skill"
        skill.mkdir()
        (skill / "drift_probes.json").write_text("[]", encoding="utf-8")
        code, errors, _warnings = _run(root)
        assert not any("[gate-json]" in e for e in errors), errors
        assert code == 0, (code, errors)
        print("ok test_clean_drift_probes_json_does_not_trip")


# --- (a2) [gate-schema] probe-kind liveness (MED HOLE fix) ------------------
# hook.py's run_probes() does `if kind not in DETECTORS: continue` — a probe
# with an unknown/typo'd kind parses as valid JSON but is silently skipped at
# runtime. This is the exact attack that broke the gate: prove it trips.

def test_unknown_probe_kind_trips_gate_schema():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        _make_min_repo(root)
        skill = root / "skills" / "typo-kind"
        skill.mkdir()
        (skill / "drift_probes.json").write_text(
            '[{"id": "oops", "kind": "no_such_detector", "pattern": "x"}]',
            encoding="utf-8",
        )
        code, errors, _warnings = _run(root)
        assert code == 2, (code, errors)
        assert any(
            "[gate-schema]" in e and "no_such_detector" in e and "oops" in e
            for e in errors
        ), errors
        print("ok test_unknown_probe_kind_trips_gate_schema")


def test_known_probe_kind_does_not_trip_gate_schema():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        _make_min_repo(root)
        skill = root / "skills" / "real-kind"
        skill.mkdir()
        (skill / "drift_probes.json").write_text(
            '[{"id": "fine", "kind": "forbidden_regex", "pattern": "x"}]',
            encoding="utf-8",
        )
        code, errors, _warnings = _run(root)
        assert not any("[gate-schema]" in e for e in errors), errors
        assert code == 0, (code, errors)
        print("ok test_known_probe_kind_does_not_trip_gate_schema")


def test_missing_canary_hook_trips_gate_schema():
    # If the canary hook itself is gone/unloadable, the schema check cannot
    # confirm any probe kind is live — must surface loudly, not silently
    # skip the check.
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        _make_min_repo(root)
        (root / "skills" / "compliance-canary" / "tools" / "hook.py").unlink()
        code, errors, _warnings = _run(root)
        assert code == 2, (code, errors)
        assert any(
            "[gate-schema]" in e and "could not derive detector kind set" in e
            for e in errors
        ), errors
        print("ok test_missing_canary_hook_trips_gate_schema")


# --- (f) broadened skills/*/tools/*.json parse-check ------------------------

def test_malformed_tools_json_trips_gate_json():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        _make_min_repo(root)
        tools_dir = root / "skills" / "some-gate" / "tools"
        tools_dir.mkdir(parents=True)
        (tools_dir / "criteria.json").write_text("{not valid json,,,", encoding="utf-8")
        code, errors, _warnings = _run(root)
        assert code == 2, (code, errors)
        assert any(
            "[gate-json]" in e and "criteria.json" in e for e in errors
        ), errors
        print("ok test_malformed_tools_json_trips_gate_json")


def test_clean_tools_json_does_not_trip():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        _make_min_repo(root)
        tools_dir = root / "skills" / "some-gate" / "tools"
        tools_dir.mkdir(parents=True)
        (tools_dir / "criteria.json").write_text('[{"id": "correct"}]', encoding="utf-8")
        code, errors, _warnings = _run(root)
        assert not any("[gate-json]" in e for e in errors), errors
        assert code == 0, (code, errors)
        print("ok test_clean_tools_json_does_not_trip")


def test_malformed_nested_tools_json_trips_gate_json():
    # CONFIRMED HOLE: skills/*/tools/*.json is a one-level glob — malformed
    # JSON at skills/<x>/tools/nested/criteria.json was silently skipped.
    # Same attack as test_malformed_tools_json_trips_gate_json above, one
    # directory deeper.
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        _make_min_repo(root)
        nested_dir = root / "skills" / "some-gate" / "tools" / "nested"
        nested_dir.mkdir(parents=True)
        (nested_dir / "criteria.json").write_text("{not valid json,,,", encoding="utf-8")
        code, errors, _warnings = _run(root)
        assert code == 2, (code, errors)
        assert any(
            "[gate-json]" in e and "nested" in e and "criteria.json" in e for e in errors
        ), errors
        print("ok test_malformed_nested_tools_json_trips_gate_json")


def test_clean_nested_tools_json_does_not_trip():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        _make_min_repo(root)
        nested_dir = root / "skills" / "some-gate" / "tools" / "nested"
        nested_dir.mkdir(parents=True)
        (nested_dir / "criteria.json").write_text('[{"id": "correct"}]', encoding="utf-8")
        code, errors, _warnings = _run(root)
        assert not any("[gate-json]" in e for e in errors), errors
        assert code == 0, (code, errors)
        print("ok test_clean_nested_tools_json_does_not_trip")


# --- (b) SKILL.md frontmatter + referenced tool paths ----------------------

def test_broken_skill_md_frontmatter_trips():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        _make_min_repo(root)
        skill = root / "skills" / "no-frontmatter"
        skill.mkdir()
        (skill / "SKILL.md").write_text("# just a heading, no frontmatter block\n", encoding="utf-8")
        code, errors, _warnings = _run(root)
        assert code == 2, (code, errors)
        assert any("[skill-md]" in e and "no parseable YAML frontmatter" in e for e in errors), errors
        print("ok test_broken_skill_md_frontmatter_trips")


def test_missing_tool_path_trips():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        _make_min_repo(root)
        skill = root / "skills" / "dangling-tool"
        skill.mkdir()
        (skill / "SKILL.md").write_text(
            "---\nname: dangling-tool\ndescription: test fixture\n---\n\n"
            "See `tools/does_not_exist.py` for the implementation.\n",
            encoding="utf-8",
        )
        code, errors, _warnings = _run(root)
        assert code == 2, (code, errors)
        assert any(
            "[skill-md]" in e and "tools/does_not_exist.py" in e for e in errors
        ), errors
        print("ok test_missing_tool_path_trips")


def test_existing_tool_path_does_not_trip():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        _make_min_repo(root)
        skill = root / "skills" / "real-tool"
        skill.mkdir()
        (skill / "tools").mkdir()
        (skill / "tools" / "real.py").write_text("# real\n", encoding="utf-8")
        (skill / "SKILL.md").write_text(
            "---\nname: real-tool\ndescription: test fixture\n---\n\n"
            "See `tools/real.py` for the implementation.\n",
            encoding="utf-8",
        )
        code, errors, _warnings = _run(root)
        assert not any("[skill-md]" in e and "real.py" in e for e in errors), errors
        assert code == 0, (code, errors)
        print("ok test_existing_tool_path_does_not_trip")


# --- (c) markdown link liveness --------------------------------------------

def test_dangling_markdown_link_in_skill_md_trips():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        _make_min_repo(root)
        skill = root / "skills" / "dangling-link"
        skill.mkdir()
        (skill / "SKILL.md").write_text(
            "---\nname: dangling-link\ndescription: test fixture\n---\n\n"
            "See [the other skill](../nonexistent-skill/SKILL.md) for details.\n",
            encoding="utf-8",
        )
        code, errors, _warnings = _run(root)
        assert code == 2, (code, errors)
        assert any("[md-link]" in e and "nonexistent-skill/SKILL.md" in e for e in errors), errors
        print("ok test_dangling_markdown_link_in_skill_md_trips")


def test_fenced_code_block_link_lookalike_not_flagged():
    # A dict/call construct or f-string inside a fenced code block can look
    # like a markdown link ([x](y)) to a naive regex — must NOT be flagged.
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        _make_min_repo(root)
        skill = root / "skills" / "code-lookalike"
        skill.mkdir()
        (skill / "SKILL.md").write_text(
            "---\nname: code-lookalike\ndescription: test fixture\n---\n\n"
            "```python\n"
            "index_content += f\"- [{filename}]({relative_path})\\n\"\n"
            "tool_runners['baseline'](data)\n"
            "```\n",
            encoding="utf-8",
        )
        code, errors, _warnings = _run(root)
        assert not any("[md-link]" in e for e in errors), errors
        assert code == 0, (code, errors)
        print("ok test_fenced_code_block_link_lookalike_not_flagged")


def test_dangling_link_in_shared_md_trips():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        _make_min_repo(root)
        shared = root / "skills" / "_shared"
        shared.mkdir()
        (shared / "SOME_DOC.md").write_text(
            "See [missing file](./NOPE.md) for more.\n", encoding="utf-8"
        )
        code, errors, _warnings = _run(root)
        assert code == 2, (code, errors)
        assert any("[md-link]" in e and "NOPE.md" in e for e in errors), errors
        print("ok test_dangling_link_in_shared_md_trips")


# --- (d) wiki liveness: hygiene delegation + link check ---------------------

def test_wiki_hygiene_delegate_failure_trips():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        _make_min_repo(root)
        # Override the stand-in hygiene script to report a failure, proving
        # knowledge_liveness surfaces a non-zero delegate exit as an error
        # rather than swallowing it.
        (root / "scripts" / "check_wiki_hygiene.py").write_text(
            "def main() -> int:\n    print('fixture: forced hygiene failure')\n    return 1\n",
            encoding="utf-8",
        )
        code, errors, _warnings = _run(root)
        assert code == 2, (code, errors)
        assert any("[wiki]" in e and "check_wiki_hygiene.py" in e for e in errors), errors
        print("ok test_wiki_hygiene_delegate_failure_trips")


def test_dangling_wiki_markdown_link_trips():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        _make_min_repo(root)
        wiki = root / "wiki"
        wiki.mkdir()
        (wiki / "page.md").write_text(
            "See [gone](./ghost.md) for the missing page.\n", encoding="utf-8"
        )
        code, errors, _warnings = _run(root)
        assert code == 2, (code, errors)
        assert any("[wiki-md-link]" in e and "ghost.md" in e for e in errors), errors
        print("ok test_dangling_wiki_markdown_link_trips")


def test_no_wiki_dir_is_not_an_error():
    # Repos without an adopted wiki (like these fixtures by default) must not
    # be penalized for lacking one.
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        _make_min_repo(root)
        code, errors, _warnings = _run(root)
        assert not any("[wiki" in e for e in errors), errors
        print("ok test_no_wiki_dir_is_not_an_error")


# --- (e) hooks-map liveness --------------------------------------------------

def test_missing_hooks_map_script_trips():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        _make_min_repo(root)
        (root / "scripts" / "gen_hooks_map.py").unlink()
        code, errors, _warnings = _run(root)
        assert code == 2, (code, errors)
        assert any("[hooks-map]" in e and "gen_hooks_map.py" in e for e in errors), errors
        print("ok test_missing_hooks_map_script_trips")


def test_dangling_hook_entry_path_trips():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        _make_min_repo(root)
        # gen_hooks_map stand-in reports an inventory row pointing at a hook
        # script + installer that do NOT exist on disk.
        (root / "scripts" / "gen_hooks_map.py").write_text(
            "def skill_hook_inventory():\n"
            "    return [{'skill': 'ghost-skill', "
            "'entry': ['skills/ghost-skill/tools/hook.py'], "
            "'installer': 'skills/ghost-skill/tools/install.sh'}]\n",
            encoding="utf-8",
        )
        code, errors, _warnings = _run(root)
        assert code == 2, (code, errors)
        assert any(
            "[hooks-map]" in e and "skills/ghost-skill/tools/hook.py" in e for e in errors
        ), errors
        assert any(
            "[hooks-map]" in e and "skills/ghost-skill/tools/install.sh" in e for e in errors
        ), errors
        print("ok test_dangling_hook_entry_path_trips")


def test_real_hook_entry_path_does_not_trip():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        _make_min_repo(root)
        skill_tools = root / "skills" / "real-hook-skill" / "tools"
        skill_tools.mkdir(parents=True)
        (skill_tools / "hook.py").write_text("# hook\n", encoding="utf-8")
        (skill_tools / "install.sh").write_text("#!/usr/bin/env bash\n", encoding="utf-8")
        (root / "scripts" / "gen_hooks_map.py").write_text(
            "def skill_hook_inventory():\n"
            "    return [{'skill': 'real-hook-skill', "
            "'entry': ['skills/real-hook-skill/tools/hook.py'], "
            "'installer': 'skills/real-hook-skill/tools/install.sh'}]\n",
            encoding="utf-8",
        )
        code, errors, _warnings = _run(root)
        assert not any("[hooks-map]" in e for e in errors), errors
        assert code == 0, (code, errors)
        print("ok test_real_hook_entry_path_does_not_trip")


# --- clean repo sanity: the real repo itself passes ------------------------

def test_real_repo_is_clean():
    """Cold-run against the actual live checkout (read-only). If this ever
    trips, it is a real finding, not a fixture — report, don't silence."""
    repo_root = Path(__file__).resolve().parents[2]
    code, errors, warnings = kl.run(repo_root=repo_root)
    assert code == 0, (errors, warnings)
    print("ok test_real_repo_is_clean")


# --- runner ---------------------------------------------------------------

def main() -> int:
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    failed = 0
    for t in tests:
        try:
            t()
            print(f"PASS {t.__name__}")
        except AssertionError as e:
            failed += 1
            print(f"FAIL {t.__name__}: {e}")
        except Exception as e:  # noqa: BLE001
            failed += 1
            print(f"ERROR {t.__name__}: {type(e).__name__}: {e}")
    print(f"\n{len(tests) - failed}/{len(tests)} passed")
    return failed


if __name__ == "__main__":
    sys.exit(main())
