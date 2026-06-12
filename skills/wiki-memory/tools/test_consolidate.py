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


def main():
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"pass {fn.__name__}")
    print(f"OK ({len(fns)} tests)")


if __name__ == "__main__":
    main()
