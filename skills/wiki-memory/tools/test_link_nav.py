#!/usr/bin/env python3
"""Tests for the 2026-06-28 wiki-memory hardening (three fixes):

  Fix 1 — link-aware retrieval: `timeline` returns a resolved `outbound` list
          (the page's own [[links]]) alongside backlinks/neighbors, so an agent
          can navigate the graph instead of only flat-searching.
  Fix 2 — docs↔reality: `index` now lists concepts/ + patterns/ in L1_index
          (they were silently excluded, hiding the bulk of curated knowledge).
  Fix 3 — lint + type vocab: `error`/`lesson` are valid v2 types (were rejected
          as invalid_type); strict lint flags error/lesson/sop pages whose
          retrieval cue (Trigger/symptom) is missing or frontmatter-only.

No pytest — `python3 test_link_nav.py`."""
from __future__ import annotations

import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from wiki import WikiStore  # noqa: E402


def _v2(title: str, type_: str, body: str, extra: str = "") -> str:
    """A complete v2-frontmatter page (recent dates so it isn't stale)."""
    return (
        "---\n"
        "schema_version: 2\n"
        f"title: {title}\n"
        f"type: {type_}\n"
        "domain: framework\n"
        "tier: semantic\n"
        "confidence: 0.5\n"
        "created: 2026-06-20\n"
        "updated: 2026-06-20\n"
        "verified: 2026-06-20\n"
        "sources: [x]\n"
        "supersedes: []\n"
        "superseded-by:\n"
        "tags: [t]\n"
        f"{extra}"
        "---\n\n"
        f"{body}\n"
    )


def _write(store: WikiStore, rel: str, text: str) -> None:
    p = store.root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


def make_store() -> tuple[WikiStore, Path]:
    tmp = Path(tempfile.mkdtemp(prefix="wiki_nav_"))
    store = WikiStore(tmp / "wiki")
    store.init()
    return store, tmp


def _warn_codes(store: WikiStore, page_id: str) -> set[str]:
    res = store.lint_pages(strict=True)
    return {w["code"] for w in res.get("warnings", []) if w.get("page") == page_id}


def _error_codes(store: WikiStore, page_id: str) -> set[str]:
    res = store.lint_pages(strict=True)
    return {e["code"] for e in res.get("errors", []) if e.get("page") == page_id}


# ---------------------------------------------------------------- Fix 1

def test_timeline_outbound_resolves_links_and_skips_stubs_and_danglers():
    store, tmp = make_store()
    try:
        # a -> b (real), -> d via bare stem (real), -> missing (dangling),
        #   -> ?future (intentional stub). c -> a (a backlink of a).
        _write(store, "concepts/a.md", _v2("A", "concept",
            "see [[concepts/b]] and [[d]] and [[concepts/missing]] and [[?concepts/future]]"))
        _write(store, "concepts/b.md", _v2("B", "concept", "b body"))
        _write(store, "concepts/d.md", _v2("D", "concept", "d body"))
        _write(store, "concepts/c.md", _v2("C", "concept", "points to [[concepts/a]]"))
        store.index()

        tl = store.timeline("concepts/a")
        assert "outbound" in tl, tl
        out_ids = {o["id"] for o in tl["outbound"]}
        assert "concepts/b" in out_ids, out_ids                 # explicit id link
        assert "concepts/d" in out_ids, out_ids                 # bare-stem resolution
        assert "concepts/missing" not in out_ids, out_ids       # dangling skipped
        assert not any("future" in i for i in out_ids), out_ids # ?stub skipped
        # shape: each outbound entry carries id/title/path
        for o in tl["outbound"]:
            assert set(o) >= {"id", "title", "path"}, o
        # backlinks still work (who points at a)
        back_ids = {b["id"] for b in tl["backlinks"]}
        assert "concepts/c" in back_ids, back_ids
    finally:
        shutil.rmtree(tmp)


def test_timeline_outbound_no_self_reference():
    store, tmp = make_store()
    try:
        _write(store, "concepts/selflink.md", _v2("Self", "concept",
            "I mention [[concepts/selflink]] and [[concepts/other]]"))
        _write(store, "concepts/other.md", _v2("Other", "concept", "other"))
        store.index()
        tl = store.timeline("concepts/selflink")
        out_ids = {o["id"] for o in tl["outbound"]}
        assert "concepts/selflink" not in out_ids, out_ids      # never self
        assert "concepts/other" in out_ids, out_ids
    finally:
        shutil.rmtree(tmp)


# ---------------------------------------------------------------- Fix 2

def test_l1_index_lists_concepts_and_patterns():
    store, tmp = make_store()
    try:
        _write(store, "concepts/my-technique.md", _v2("My technique", "concept", "body"))
        _write(store, "patterns/my-workflow.md", _v2("My workflow", "pattern", "body"))
        _write(store, "projects/my-proj.md", _v2("My proj", "project", "body"))
        store.index()
        l1 = (store.root / "L1_index.md").read_text(encoding="utf-8")
        assert "concepts/my-technique" in l1, l1   # was silently excluded before
        assert "patterns/my-workflow" in l1, l1
        assert "projects/my-proj" in l1, l1        # regression guard (already worked)
    finally:
        shutil.rmtree(tmp)


# ---------------------------------------------------------------- Fix 3 (vocab)

def test_error_and_lesson_are_valid_v2_types():
    store, tmp = make_store()
    try:
        _write(store, "concepts/err.md", _v2("Err", "error",
            "**Trigger / symptom:** boom\nlesson body"))
        _write(store, "concepts/les.md", _v2("Les", "lesson",
            "**Symptom:** off-by-hours\nlesson body"))
        store.index()
        assert "invalid_type" not in _error_codes(store, "concepts/err"), "error type rejected"
        assert "invalid_type" not in _error_codes(store, "concepts/les"), "lesson type rejected"
    finally:
        shutil.rmtree(tmp)


# ---------------------------------------------------------------- Fix 3 (cue lint)

def test_missing_trigger_cue_flagged():
    store, tmp = make_store()
    try:
        _write(store, "concepts/nocue.md", _v2("No cue", "lesson",
            "This lesson explains a failure mode but never names the observable signal."))
        store.index()
        codes = _warn_codes(store, "concepts/nocue")
        assert "missing_trigger_cue" in codes, codes
        assert "trigger_in_frontmatter_only" not in codes, codes
    finally:
        shutil.rmtree(tmp)


def test_body_cue_satisfies_lint():
    store, tmp = make_store()
    try:
        _write(store, "concepts/withcue.md", _v2("With cue", "lesson",
            "**Trigger / symptom:** tests fail by exactly the local UTC offset\nFix: use UTC."))
        store.index()
        codes = _warn_codes(store, "concepts/withcue")
        assert "missing_trigger_cue" not in codes, codes
        assert "trigger_in_frontmatter_only" not in codes, codes
    finally:
        shutil.rmtree(tmp)


def test_frontmatter_only_trigger_flagged_specifically():
    store, tmp = make_store()
    try:
        # symptom lives ONLY in a frontmatter key -> a silent search no-op.
        _write(store, "concepts/fmonly.md", _v2("FM only", "lesson",
            "Body prose with no observable-signal line.",
            extra="trigger: off-by-hours in date tests\n"))
        store.index()
        codes = _warn_codes(store, "concepts/fmonly")
        assert "trigger_in_frontmatter_only" in codes, codes
        assert "missing_trigger_cue" not in codes, codes   # the specific code wins
    finally:
        shutil.rmtree(tmp)


def test_cue_only_applies_to_error_lesson_sop():
    store, tmp = make_store()
    try:
        # a plain concept page with no cue must NOT be flagged
        _write(store, "concepts/plain.md", _v2("Plain", "concept",
            "An ordinary concept page, no symptom line needed."))
        store.index()
        codes = _warn_codes(store, "concepts/plain")
        assert "missing_trigger_cue" not in codes, codes
    finally:
        shutil.rmtree(tmp)


# ----------------------------------------- Fix 1 hardening (adversarial review)

def test_outbound_full_path_dangler_not_rerouted_by_stem():
    """A dangling FULL-PATH link [[oldarchive/widget]] must NOT silently resolve
    onto an unrelated same-basename page (concepts/widget). Only bare names use
    the stem fallback; a full-path miss is a true dangler -> skipped."""
    store, tmp = make_store()
    try:
        _write(store, "concepts/a.md", _v2("A", "concept",
            "links [[oldarchive/widget]] and [[concepts/real]]"))
        _write(store, "concepts/widget.md", _v2("Widget", "concept", "unrelated same-stem page"))
        _write(store, "concepts/real.md", _v2("Real", "concept", "real target"))
        store.index()
        out_ids = {o["id"] for o in store.timeline("concepts/a")["outbound"]}
        assert "concepts/widget" not in out_ids, out_ids   # full-path dangler not rerouted
        assert "concepts/real" in out_ids, out_ids
    finally:
        shutil.rmtree(tmp)


def test_backlinks_resolve_bare_stem_citation():
    """backlinks must catch a bare-stem citation [[a]] of concepts/a (symmetry
    with outbound + with lint's inbound counting), while a dangling full-path
    citation [[old/a]] must NOT create a false backlink."""
    store, tmp = make_store()
    try:
        _write(store, "concepts/a.md", _v2("A", "concept", "target"))
        _write(store, "concepts/citer.md", _v2("Citer", "concept", "see [[a]]"))      # bare stem
        _write(store, "concepts/falsep.md", _v2("FalseP", "concept", "see [[old/a]]")) # full-path dangler
        store.index()
        back_ids = {b["id"] for b in store.timeline("concepts/a")["backlinks"]}
        assert "concepts/citer" in back_ids, back_ids     # bare-stem citer found
        assert "concepts/falsep" not in back_ids, back_ids # dangling full-path != backlink
    finally:
        shutil.rmtree(tmp)


# ----------------------------------------- Fix 3 hardening (cue regex)

def test_cue_accepted_in_heading_bullet_numbered_plural_styles():
    store, tmp = make_store()
    try:
        cases = {
            "concepts/h.md": "## Symptom\nthe build hangs forever",
            "concepts/b.md": "- Symptom: tests fail by the UTC offset",
            "concepts/n.md": "1. Trigger: stale cache after rename",
            "concepts/p.md": "Symptoms: flaky retries on CI",
            "concepts/bold.md": "**Trigger / symptom:** classic bold form",
        }
        for rel, body in cases.items():
            _write(store, rel, _v2(Path(rel).stem, "lesson", body))
        store.index()
        for rel in cases:
            pid = rel[:-3]
            assert "missing_trigger_cue" not in _warn_codes(store, pid), (pid, "wrongly flagged")
    finally:
        shutil.rmtree(tmp)


def test_cue_inside_code_fence_does_not_satisfy():
    """A trigger:/symptom: line that only appears inside a ``` code fence is not a
    real prose cue (matches the has_falsifier/content_tokens fence-strip convention)."""
    store, tmp = make_store()
    try:
        _write(store, "concepts/fenced.md", _v2("Fenced", "lesson",
            "Body has no real cue.\n\n```\ntrigger: this is only an example\nsymptom: also example\n```\n"))
        store.index()
        assert "missing_trigger_cue" in _warn_codes(store, "concepts/fenced"), "fenced cue wrongly counted"
    finally:
        shutil.rmtree(tmp)


# ----------------------------------------- Fix 2 hardening (L1 truncation)

def test_l1_truncation_is_surfaced_and_small_tiers_survive():
    """Past the cap, L1 must (a) keep projects/queries (tier-ordered ahead of the
    bulky concepts/) and (b) SURFACE the truncation instead of silently dropping."""
    store, tmp = make_store()
    try:
        for i in range(150):
            _write(store, f"concepts/c{i:03d}.md", _v2(f"C{i}", "concept", "body"))
        _write(store, "projects/keystone.md", _v2("Keystone", "project", "body"))
        _write(store, "queries/keyquery.md", _v2("Keyquery", "query", "body"))
        store.index()
        l1 = (store.root / "L1_index.md").read_text(encoding="utf-8")
        assert "projects/keystone" in l1, "small high-value tier dropped by truncation"
        assert "queries/keyquery" in l1, "small high-value tier dropped by truncation"
        assert "more page(s) not listed" in l1, "truncation was silent"
        assert "concepts/c149" not in l1, "expected tail concepts to be truncated"
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
