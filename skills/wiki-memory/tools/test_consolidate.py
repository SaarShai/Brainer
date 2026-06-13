#!/usr/bin/env python3
"""Tests for wiki.py consolidate (reuse-driven trust promotion) + usage ledger.
No pytest. Policy under test (adopted 2026-06-12): fetch-reuse >= N promotes
asserted -> corroborated ONLY (never verified — that stays earned through
write-gate evidence); raw/ + L4_archive/ are immutable; deletes nothing."""
from __future__ import annotations

import json
import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from wiki import WikiStore  # noqa: E402


def make_store() -> tuple[WikiStore, Path]:
    tmp = Path(tempfile.mkdtemp(prefix="wiki_consol_"))
    root = tmp / "wiki"
    store = WikiStore(root)
    store.init()
    for rel, trust in [("concepts/reused.md", "asserted"),
                       ("concepts/once.md", "asserted"),
                       ("concepts/already-high.md", "verified"),
                       ("raw/source-dump.md", "asserted")]:
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(f"---\ntitle: {Path(rel).stem}\ntype: concept\ntrust: {trust}\n---\n\nbody of {rel}\n")
    store.index()
    return store, tmp


def test_fetch_bumps_usage_and_consolidate_promotes():
    store, tmp = make_store()
    try:
        for _ in range(2):
            store.fetch("concepts/reused")
            store.fetch("raw/source-dump")
        store.fetch("concepts/once")

        report = store.consolidate(min_fetches=2, apply=False)
        ids = [c["id"] for c in report["promote_candidates"]]
        assert ids == ["concepts/reused"], report          # raw/ excluded, once too few
        assert report["applied"] == []                      # dry-run default

        report = store.consolidate(min_fetches=2, apply=True)
        assert report["applied"] == ["concepts/reused"], report
        text = (store.root / "concepts/reused.md").read_text()
        assert "trust: corroborated" in text and "asserted" not in text
        # verified page untouched; promotion is one tier, never to verified
        assert "trust: verified" in (store.root / "concepts/already-high.md").read_text()
        # idempotent: second apply finds nothing
        report = store.consolidate(min_fetches=2, apply=True)
        assert report["promote_candidates"] == [] and report["applied"] == []
    finally:
        shutil.rmtree(tmp)


def test_usage_ledger_failure_never_breaks_fetch():
    store, tmp = make_store()
    try:
        store.state_dir.mkdir(exist_ok=True)
        store._usage_path().write_text("NOT JSON{{{")
        out = store.fetch("concepts/once")  # must not raise
        assert out["id"] == "concepts/once"
    finally:
        shutil.rmtree(tmp)


def _seed_page(store, rel, text):
    p = store.root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


def test_apply_promotes_quoted_no_frontmatter_and_spares_body_line():
    """consolidate --apply must edit FRONTMATTER ONLY (Bug 1).

    Before the fix the bare `^trust: asserted$` regex ran against the raw whole
    document, so: a quoted `trust: "asserted"` page got a *second* trust key
    prepended (duplicate -> asserted wins -> re-qualifies forever); a body line
    reading `trust: asserted` was rewritten while frontmatter never promoted;
    and a no-frontmatter page silently no-op'd. Each assertion below FAILS on
    the old code and passes on the scoped-frontmatter fix.
    """
    store, tmp = make_store()
    try:
        # Quoted frontmatter trust — parse_frontmatter strips quotes so it IS a
        # candidate, but the old unquoted regex missed it.
        _seed_page(store, "concepts/quoted.md",
                   '---\ntitle: quoted\ntype: concept\ntrust: "asserted"\n---\n\nbody of quoted\n')
        # Body line collision: frontmatter has NO trust key, but a body line
        # reads `trust: asserted` (e.g. quoting this very policy).
        _seed_page(store, "concepts/bodyline.md",
                   "---\ntitle: bodyline\ntype: concept\n---\n\nNote: trust: asserted is the default tier.\n")
        # No leading frontmatter at all.
        _seed_page(store, "concepts/nofm.md",
                   "# nofm\n\nbody with no frontmatter\n")
        store.index()

        for _ in range(2):
            store.fetch("concepts/quoted")
            store.fetch("concepts/bodyline")
            store.fetch("concepts/nofm")

        report = store.consolidate(min_fetches=2, apply=True)
        assert set(report["applied"]) >= {"concepts/quoted", "concepts/bodyline", "concepts/nofm"}, report

        # Quoted: exactly one trust key, promoted (no duplicate prepend).
        qtxt = (store.root / "concepts/quoted.md").read_text()
        assert qtxt.count("trust:") == 1, qtxt
        assert "trust: corroborated" in qtxt, qtxt
        assert "asserted" not in qtxt, qtxt

        # Body line: frontmatter gets a trust key; the BODY line is untouched.
        btxt = (store.root / "concepts/bodyline.md").read_text()
        assert "Note: trust: asserted is the default tier." in btxt, btxt
        bfm, _ = __import__("wiki").parse_frontmatter(btxt)
        assert bfm.get("trust") == "corroborated", btxt

        # No-frontmatter: a minimal frontmatter block is synthesized.
        ntxt = (store.root / "concepts/nofm.md").read_text()
        nfm, nbody = __import__("wiki").parse_frontmatter(ntxt)
        assert nfm.get("trust") == "corroborated", ntxt
        assert "body with no frontmatter" in nbody, ntxt

        # Idempotency: a second --apply finds nothing for any of them.
        store.index()
        report2 = store.consolidate(min_fetches=2, apply=True)
        assert report2["applied"] == [], report2
        assert report2["promote_candidates"] == [], report2
    finally:
        shutil.rmtree(tmp)


def test_timeline_does_not_bump_usage_ledger():
    """timeline is a metadata-only read — it must NOT inflate the fetch-reuse
    ledger consolidate() consumes (Bug 3). Old code routed timeline through
    fetch(), which bumped usage; calling timeline twice then promoted a page
    that was never explicitly fetched."""
    store, tmp = make_store()
    try:
        store.timeline("concepts/once")
        store.timeline("concepts/once")
        report = store.consolidate(min_fetches=2, apply=False)
        ids = [c["id"] for c in report["promote_candidates"]]
        assert "concepts/once" not in ids, report
        # An explicit fetch still counts.
        store.fetch("concepts/once")
        store.fetch("concepts/once")
        report = store.consolidate(min_fetches=2, apply=False)
        ids = [c["id"] for c in report["promote_candidates"]]
        assert "concepts/once" in ids, report
    finally:
        shutil.rmtree(tmp)


def main():
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"pass {fn.__name__}")
    print(f"OK ({len(fns)} tests)")


if __name__ == "__main__":
    main()
