#!/usr/bin/env python3
"""Tests for schema_evolution.py — recurring write-defect classes -> PROPOSED
schema/template amendments (report-only, human-gated, never auto-applied).

No pytest — `python3 test_schema_evolution.py`."""
from __future__ import annotations

import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import schema_evolution as SE  # noqa: E402
from wiki import WikiStore  # noqa: E402


def _v2(title: str, type_: str, body: str) -> str:
    return (
        "---\nschema_version: 2\n"
        f"title: {title}\ntype: {type_}\n"
        "domain: framework\ntier: semantic\nconfidence: 0.5\n"
        "created: 2026-06-20\nupdated: 2026-06-20\nverified: 2026-06-20\n"
        "sources: [x]\nsupersedes: []\nsuperseded-by:\ntags: [t]\n---\n\n"
        f"{body}\n"
    )


def _write(store, rel, text):
    p = store.root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


# ---------------------------------------------------------- pure logic

def test_below_threshold_yields_nothing():
    assert SE.propose_amendments({"missing_provenance": 2}, threshold=3) == []


def test_at_threshold_known_code_proposes_rule():
    out = SE.propose_amendments({"missing_provenance": 3}, threshold=3)
    assert len(out) == 1, out
    p = out[0]
    assert p["defect_class"] == "missing_provenance"
    assert p["count"] == 3
    assert p["proposed_rule"] and p["target_section"], p  # a real amendment, not None


def test_unknown_code_surfaced_not_dropped():
    out = SE.propose_amendments({"some_new_code": 5}, threshold=3)
    assert len(out) == 1 and out[0]["proposed_rule"] is None, out
    assert "review manually" in out[0]["note"], out  # recurring but no canned fix -> still surfaced


def test_report_only_never_applies():
    # No proposal ever carries an apply/auto action; run() reports applied=False.
    out = SE.propose_amendments({"orphan": 4, "missing_backlinks": 3}, threshold=3)
    for p in out:
        assert "apply" not in {k.lower() for k in p}, p
        assert p.get("action") != "apply", p


def test_proposals_sorted_by_recurrence():
    out = SE.propose_amendments({"orphan": 3, "missing_provenance": 9}, threshold=3)
    assert [p["defect_class"] for p in out] == ["missing_provenance", "orphan"], out


# ---------------------------------------------------------- integration

def test_integration_recurring_defect_proposes_and_does_not_touch_schema():
    tmp = Path(tempfile.mkdtemp(prefix="wiki_se_"))
    try:
        store = WikiStore(tmp / "wiki")
        store.init()
        schema = store.root / "schema.md"
        before = schema.read_text(encoding="utf-8") if schema.exists() else None
        # 3 lesson pages with NO trigger/symptom cue -> recurring missing_trigger_cue.
        _write(store, "concepts/anchor.md", _v2("Anchor", "concept", "anchor page"))
        for i in range(3):
            _write(store, f"concepts/les{i}.md",
                   _v2(f"Lesson {i}", "lesson", "A failure mode with no symptom line. See [[concepts/anchor]]."))
        store.index()
        res = SE.run(store.root, threshold=3)
        assert res["applied"] is False, res
        classes = {p["defect_class"] for p in res["proposals"]}
        assert "missing_trigger_cue" in classes, res["signals_scanned"]
        # the canonical contract must be untouched by an analysis pass
        after = schema.read_text(encoding="utf-8") if schema.exists() else None
        assert after == before, "schema.md was modified by a report-only pass"
    finally:
        shutil.rmtree(tmp)


def test_cli_wiring():
    import subprocess, json
    tmp = Path(tempfile.mkdtemp(prefix="wiki_se_cli_"))
    try:
        store = WikiStore(tmp / "wiki")
        store.init()
        r = subprocess.run(
            [sys.executable, str(Path(__file__).parent / "wiki.py"),
             "--root", str(store.root), "schema-evolution", "--threshold", "3"],
            capture_output=True, text=True)
        assert r.returncode == 0, r.stderr
        d = json.loads(r.stdout)
        assert d["applied"] is False and "proposals" in d and d["threshold"] == 3, d
    finally:
        shutil.rmtree(tmp)


def main() -> None:
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"pass {fn.__name__}")
    print(f"OK ({len(fns)} tests)")


if __name__ == "__main__":
    main()
