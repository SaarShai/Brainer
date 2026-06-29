#!/usr/bin/env python3
"""Tests for the 2026-06-29 paper-adoption additions:

  stale_citers — belief-update propagation: pages whose BODY cites a
                 superseded/contested page (the supersession didn't ripple to
                 citers). Report-only; never rewrites another page.
  quorum       — compile-on-ingest admission gate: auto-file (corroborated+) vs
                 quarantine a single-source candidate as an asserted draft.

No pytest — `python3 test_belief_propagation.py`."""
from __future__ import annotations

import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from wiki import WikiStore  # noqa: E402


def _v2(title: str, type_: str, body: str, superseded_by: str = "",
        supersedes: str = "", contradicts: str = "") -> str:
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
        f"supersedes: [{supersedes}]\n"
        f"superseded-by: {superseded_by}\n"
        f"contradicts: [{contradicts}]\n"
        "tags: [t]\n"
        "---\n\n"
        f"{body}\n"
    )


def _write(store: WikiStore, rel: str, text: str) -> None:
    p = store.root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


def make_store() -> tuple[WikiStore, Path]:
    tmp = Path(tempfile.mkdtemp(prefix="wiki_belief_"))
    store = WikiStore(tmp / "wiki")
    store.init()
    return store, tmp


# ------------------------------------------------------------ stale_citers

def test_cites_superseded_is_flagged():
    store, tmp = make_store()
    try:
        # b is superseded by bnew. a's BODY still links [[concepts/b]] -> stale citer.
        _write(store, "concepts/b.md", _v2("B", "concept", "old approach",
                                           superseded_by="[[concepts/bnew]]"))
        _write(store, "concepts/bnew.md", _v2("Bnew", "concept", "new approach",
                                              supersedes="[[concepts/b]]"))
        _write(store, "concepts/a.md", _v2("A", "concept", "follows [[concepts/b]] here"))
        store.index()
        res = store.stale_citers()
        rows = {(r["citer"], r["cites"]) for r in res["cites_superseded"]}
        assert ("concepts/a", "concepts/b") in rows, res["cites_superseded"]
        newer = res["cites_superseded"][0]["newer"]
        assert "concepts/bnew" in newer, newer
    finally:
        shutil.rmtree(tmp)


def test_superseding_page_not_flagged_for_citing_what_it_replaces():
    store, tmp = make_store()
    try:
        # bnew replaces b AND mentions [[concepts/b]] in its body. It is the NEWER
        # page, so it must NOT be reported as a stale citer of b.
        _write(store, "concepts/b.md", _v2("B", "concept", "old",
                                           superseded_by="[[concepts/bnew]]"))
        _write(store, "concepts/bnew.md", _v2("Bnew", "concept",
                                              "replaces [[concepts/b]] entirely",
                                              supersedes="[[concepts/b]]"))
        store.index()
        rows = {(r["citer"], r["cites"]) for r in store.stale_citers()["cites_superseded"]}
        assert ("concepts/bnew", "concepts/b") not in rows, rows
    finally:
        shutil.rmtree(tmp)


def test_current_target_citation_not_flagged():
    store, tmp = make_store()
    try:
        _write(store, "concepts/d.md", _v2("D", "concept", "current, not superseded"))
        _write(store, "concepts/c.md", _v2("C", "concept", "see [[concepts/d]]"))
        store.index()
        res = store.stale_citers()
        assert res["cites_superseded"] == [], res["cites_superseded"]
        assert res["count"] == 0, res
    finally:
        shutil.rmtree(tmp)


def test_bare_stem_citation_of_superseded_is_flagged():
    store, tmp = make_store()
    try:
        _write(store, "concepts/old.md", _v2("Old", "concept", "x",
                                             superseded_by="[[concepts/fresh]]"))
        _write(store, "concepts/fresh.md", _v2("Fresh", "concept", "y",
                                               supersedes="[[concepts/old]]"))
        # bare-stem citation [[old]] must resolve to concepts/old and flag.
        _write(store, "concepts/citer.md", _v2("Citer", "concept", "ref [[old]]"))
        store.index()
        rows = {(r["citer"], r["cites"]) for r in store.stale_citers()["cites_superseded"]}
        assert ("concepts/citer", "concepts/old") in rows, rows
    finally:
        shutil.rmtree(tmp)


def test_cites_contested_is_flagged():
    store, tmp = make_store()
    try:
        # f carries a contradicts edge -> contested. e cites it.
        _write(store, "concepts/f.md", _v2("F", "concept", "claims X",
                                           contradicts="[[concepts/g]]"))
        _write(store, "concepts/g.md", _v2("G", "concept", "claims not-X",
                                           contradicts="[[concepts/f]]"))
        _write(store, "concepts/e.md", _v2("E", "concept", "relies on [[concepts/f]]"))
        store.index()
        rows = {(r["citer"], r["cites"]) for r in store.stale_citers()["cites_contested"]}
        assert ("concepts/e", "concepts/f") in rows, rows
    finally:
        shutil.rmtree(tmp)


def test_raw_pages_excluded():
    store, tmp = make_store()
    try:
        _write(store, "concepts/b.md", _v2("B", "concept", "x",
                                           superseded_by="[[concepts/bnew]]"))
        _write(store, "concepts/bnew.md", _v2("Bnew", "concept", "y",
                                              supersedes="[[concepts/b]]"))
        # a raw source citing b must NOT count as a stale citer (raw/ is frozen).
        _write(store, "raw/2026-06-29-src.md",
               _v2("Src", "raw", "quotes [[concepts/b]]"))
        store.index()
        rows = {r["citer"] for r in store.stale_citers()["cites_superseded"]}
        assert not any(c.startswith("raw/") for c in rows), rows
    finally:
        shutil.rmtree(tmp)


# ------------------------------------------------------------ quorum

def test_quorum_single_source_quarantines():
    store, tmp = make_store()
    try:
        r = store.quorum("A brand new isolated concept name", sources=1)
        assert r["action"] == "quarantine", r
        assert r["tier"] == "asserted", r
        assert r["recommended_target"] == "create-quarantined-draft", r
    finally:
        shutil.rmtree(tmp)


def test_quorum_two_sources_autofile():
    store, tmp = make_store()
    try:
        r = store.quorum("Another isolated novel concept title", sources=2)
        assert r["action"] == "autofile", r
        assert r["tier"] == "corroborated", r
        assert r["recommended_target"] == "create", r
    finally:
        shutil.rmtree(tmp)


def test_quorum_verified_and_user_autofile():
    store, tmp = make_store()
    try:
        assert store.quorum("Verified isolated fact title", sources=1, verified=True)["tier"] == "verified"
        assert store.quorum("Human confirmed isolated title", user_confirmed=True)["tier"] == "user_confirmed"
        assert store.quorum("Verified isolated fact title", sources=1, verified=True)["action"] == "autofile"
    finally:
        shutil.rmtree(tmp)


def test_quorum_existing_subject_routes_to_update():
    store, tmp = make_store()
    try:
        # Seed a strongly-overlapping page; a near-identical candidate should be
        # steered to update-existing even if the quorum would otherwise auto-file.
        body = "Retry budgets cap loop iterations. Bounded by max_iterations and a token ceiling."
        _write(store, "patterns/retry-budget-loops.md",
               _v2("Retry budget loops", "pattern", body))
        store.index()
        r = store.quorum("Retry budget loops", body=body, tags=["t"], sources=2)
        # overlap should be non-low; when high, target is update-existing.
        assert r["overlap"] in {"moderate", "high"}, r
        if r["overlap"] == "high":
            assert r["recommended_target"] == "update-existing", r
    finally:
        shutil.rmtree(tmp)


def test_superseded_by_nonexistent_target_not_flagged():
    # Regression (adversarial review, MEDIUM): a page whose superseded-by points to a
    # page that does NOT exist has no actionable `newer` — flagging its citers with
    # newer=[] is an unactionable false positive. Such a citer must NOT be reported
    # (the broken link is lint's `broken_supersession`, a separate concern).
    store, tmp = make_store()
    try:
        _write(store, "concepts/p.md", _v2("P", "concept", "old",
                                           superseded_by="[[concepts/does-not-exist-999]]"))
        _write(store, "concepts/c.md", _v2("C", "concept", "cites [[concepts/p]]"))
        store.index()
        res = store.stale_citers()
        rows = {(r["citer"], r["cites"]) for r in res["cites_superseded"]}
        assert ("concepts/c", "concepts/p") not in rows, rows
        # and crucially: no finding is ever emitted with an empty `newer`
        for r in res["cites_superseded"]:
            assert r["newer"], r
    finally:
        shutil.rmtree(tmp)


def test_quorum_quarantine_never_recommends_update_existing():
    # Regression (adversarial review, HIGH): a quarantine-trust candidate that overlaps
    # an existing page must NOT be told to `update-existing` (that contradicts the
    # quarantine). It routes to reconcile-via-resolve (or, if overlap isn't high, to a
    # quarantined draft) — never update-existing.
    store, tmp = make_store()
    try:
        body = ("Retry budgets cap loop iterations; see [[concepts/loop-anchor]] and "
                "skills/wiki-memory/tools/wiki.py for the gate.")
        _write(store, "concepts/loop-anchor.md", _v2("Loop anchor", "concept", "x"))
        _write(store, "patterns/retry-budget-loops.md",
               _v2("Retry budget loops", "pattern", body))
        store.index()
        q1 = store.quorum("Retry budget loops", body=body, tags=["t"], sources=1)
        assert q1["action"] == "quarantine", q1
        # the invariant the bug violated: quarantine never yields update-existing
        assert q1["recommended_target"] != "update-existing", q1
        if q1["overlap"] == "high":
            assert q1["recommended_target"] == "reconcile-via-resolve", q1
        # an autofile-trust candidate on the SAME existing page may update it
        q2 = store.quorum("Retry budget loops", body=body, tags=["t"], sources=2)
        assert q2["action"] == "autofile", q2
        if q2["overlap"] == "high":
            assert q2["recommended_target"] == "update-existing", q2
    finally:
        shutil.rmtree(tmp)


def test_cli_wiring_for_new_verbs():
    # Locks the argparse + dispatch glue for the two new subcommands (the methods
    # are unit-tested above; this proves the CLI actually exposes them end-to-end).
    import subprocess
    import json
    store, tmp = make_store()
    try:
        wiki_py = str(Path(__file__).parent / "wiki.py")
        root = str(store.root)

        def cli(*args):
            return subprocess.run([sys.executable, wiki_py, "--root", root, *args],
                                  capture_output=True, text=True)

        r = cli("stale-citers")
        assert r.returncode == 0, r.stderr
        d = json.loads(r.stdout)
        assert {"cites_superseded", "cites_contested", "count"} <= set(d), d

        r1 = cli("quorum", "--title", "Some isolated novel concept", "--sources", "1")
        assert r1.returncode == 0, r1.stderr
        assert json.loads(r1.stdout)["action"] == "quarantine", r1.stdout

        r2 = cli("quorum", "--title", "Some isolated novel concept", "--sources", "2")
        assert r2.returncode == 0, r2.stderr
        assert json.loads(r2.stdout)["action"] == "autofile", r2.stdout

        # flags wired: --verified and --user-confirmed reach the method
        rv = cli("quorum", "--title", "Verified isolated concept", "--verified")
        assert json.loads(rv.stdout)["tier"] == "verified", rv.stdout
    finally:
        import shutil as _sh
        _sh.rmtree(tmp)


def main() -> None:
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"pass {fn.__name__}")
    print(f"OK ({len(fns)} tests)")


if __name__ == "__main__":
    main()
