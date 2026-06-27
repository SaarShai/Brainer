#!/usr/bin/env python3
"""Standalone tests for the three codebase-memory-mcp-inspired adoptions in
wiki.py (mirrors the assert+exit-1 style of scripts/check_*.py — no pytest).

Covers:
  (a) #2 DEGRADED-WRITE — index() reports status:"degraded" on a simulated
      under-persist, stays "ok" on a normal store (and on a tiny store below
      the floor).
  (b) #3 LOUD UNSUPPORTED-QUERY — a malformed/unsupported query raises and the
      CLI returns an explicit error (nonzero exit); a valid query with zero
      hits still returns a normal empty result.
  (c) #8 ADR — the decision template carries all four ADR fields
      (status/context/decision/consequences).
  (d) #8 ADR — ingesting a fixture docs/adr/0001-x.md creates a wiki decision
      page.

Uses an isolated temp wiki dir; never touches the real wiki/.
"""
from __future__ import annotations

import io
import os
import sqlite3
import sys
import tempfile
from contextlib import redirect_stdout
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import wiki  # noqa: E402
from wiki import WikiStore, WikiUnsupportedQueryError  # noqa: E402

FAILURES: list[str] = []


def check(cond: bool, msg: str) -> None:
    if not cond:
        FAILURES.append(msg)
        print(f"FAIL: {msg}")
    else:
        print(f"ok: {msg}")


def _seed_pages(store: WikiStore, n: int) -> None:
    """Create n minimal concept pages so the store has real content."""
    store.init()
    concepts = store.root / "concepts"
    concepts.mkdir(parents=True, exist_ok=True)
    for i in range(n):
        (concepts / f"page-{i}.md").write_text(
            "---\n"
            "schema_version: 2\n"
            f"title: \"Page {i}\"\n"
            "type: concept\n"
            "domain: framework\n"
            "tier: semantic\n"
            "confidence: 0.5\n"
            "tags: [alpha]\n"
            "---\n\n"
            f"# Page {i}\n\n"
            f"This page documents widget mechanism number {i}.\n",
            encoding="utf-8",
        )


# --- (a) #2 DEGRADED-WRITE --------------------------------------------------

def test_degraded_normal_is_ok() -> None:
    with tempfile.TemporaryDirectory() as td:
        store = WikiStore(Path(td) / "wiki")
        _seed_pages(store, 8)
        result = store.index()
        check(result.get("status") == "ok",
              f"(a) normal index reports status ok (got {result.get('status')!r})")
        check(result["indexed"] == result.get("persisted"),
              "(a) normal index: indexed == persisted")


def test_degraded_tiny_store_skips_floor() -> None:
    with tempfile.TemporaryDirectory() as td:
        store = WikiStore(Path(td) / "wiki")
        _seed_pages(store, 2)  # below default floor of 5
        result = store.index()
        # A tiny store must not be flagged degraded even if persistence is low.
        check(result.get("status") == "ok",
              f"(a) tiny store below floor stays ok (got {result.get('status')!r})")
        # Direct floor check: 1/2 persisted, but expected < floor => ok.
        report = store.verify_persistence(expected=2, persisted=1)
        check(report["status"] == "ok",
              f"(a) below-floor under-persist stays ok (got {report})")


def test_degraded_under_persist_triggers() -> None:
    with tempfile.TemporaryDirectory() as td:
        store = WikiStore(Path(td) / "wiki")
        _seed_pages(store, 10)
        store.index()
        # Simulate an under-persist: delete most rows from the docs table behind
        # the index's back, then re-run the persistence verification against the
        # known expected count.
        with sqlite3.connect(store.db_path) as conn:
            conn.execute("DELETE FROM docs WHERE id NOT IN (SELECT id FROM docs LIMIT 2)")
        report = store.verify_persistence(expected=10)
        check(report["status"] == "degraded",
              f"(a) 2/10 persisted => degraded (got {report['status']!r})")
        check(report["persisted"] == 2 and report["expected"] == 10,
              f"(a) degraded report carries counts (got {report})")


def test_degraded_ratio_env_tunable() -> None:
    with tempfile.TemporaryDirectory() as td:
        store = WikiStore(Path(td) / "wiki")
        _seed_pages(store, 10)
        store.index()
        with sqlite3.connect(store.db_path) as conn:
            conn.execute("DELETE FROM docs WHERE id NOT IN (SELECT id FROM docs LIMIT 6)")
        # 6/10 = 0.6 persisted. Default ratio 0.5 => ok. Ratio 0.7 => degraded.
        prev = os.environ.get("WIKI_DEGRADED_RATIO")
        try:
            os.environ.pop("WIKI_DEGRADED_RATIO", None)
            check(store.verify_persistence(expected=10)["status"] == "ok",
                  "(a) 6/10 with default ratio 0.5 stays ok")
            os.environ["WIKI_DEGRADED_RATIO"] = "0.7"
            check(store.verify_persistence(expected=10)["status"] == "degraded",
                  "(a) 6/10 with ratio 0.7 => degraded (env-tunable)")
        finally:
            if prev is None:
                os.environ.pop("WIKI_DEGRADED_RATIO", None)
            else:
                os.environ["WIKI_DEGRADED_RATIO"] = prev


# --- (b) #3 LOUD UNSUPPORTED-QUERY ------------------------------------------

def test_unsupported_query_raises() -> None:
    with tempfile.TemporaryDirectory() as td:
        store = WikiStore(Path(td) / "wiki")
        _seed_pages(store, 6)
        store.index()
        for bad in ["", "   ", "the and for", "!!!"]:
            try:
                store.search(bad)
                check(False, f"(b) unsupported query {bad!r} should raise")
            except WikiUnsupportedQueryError:
                check(True, f"(b) unsupported query {bad!r} raises WikiUnsupportedQueryError")


def test_valid_zero_match_is_empty() -> None:
    with tempfile.TemporaryDirectory() as td:
        store = WikiStore(Path(td) / "wiki")
        _seed_pages(store, 6)
        store.index()
        # A valid, well-formed query token that simply matches nothing.
        results = store.search("nonexistentxyzzy")
        check(results == [],
              f"(b) valid zero-match query returns normal empty list (got {results!r})")


def test_cli_unsupported_query_nonzero_exit() -> None:
    with tempfile.TemporaryDirectory() as td:
        root = str(Path(td) / "wiki")
        store = WikiStore(root)
        _seed_pages(store, 6)
        store.index()
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = wiki._cli_main(["--root", root, "search", "the and for"])
        out = buf.getvalue()
        check(rc != 0, f"(b) CLI unsupported query exits nonzero (got rc={rc})")
        check("unsupported query" in out,
              f"(b) CLI emits explicit 'unsupported query' error (got {out!r})")


def test_cli_valid_zero_match_zero_exit() -> None:
    with tempfile.TemporaryDirectory() as td:
        root = str(Path(td) / "wiki")
        store = WikiStore(root)
        _seed_pages(store, 6)
        store.index()
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = wiki._cli_main(["--root", root, "search", "nonexistentxyzzy"])
        check(rc == 0, f"(b) CLI valid zero-match exits 0 (got rc={rc})")
        check("unsupported query" not in buf.getvalue(),
              "(b) CLI valid zero-match has no error")


# --- (c) #8 ADR template fields ---------------------------------------------

def test_decision_template_has_adr_fields() -> None:
    tmpl = (HERE.parent / "templates" / "decision.template.md").read_text(encoding="utf-8").lower()
    for field in ("status", "context", "decision", "consequences"):
        check(f"## {field}" in tmpl,
              f"(c) decision template has '## {field}' ADR section")


# --- (d) #8 ADR ingest ------------------------------------------------------

def test_ingest_adr_creates_decision_page() -> None:
    with tempfile.TemporaryDirectory() as td:
        repo = Path(td) / "repo"
        adr_dir = repo / "docs" / "adr"
        adr_dir.mkdir(parents=True, exist_ok=True)
        (adr_dir / "0001-use-sqlite.md").write_text(
            "# Use SQLite for the index\n\n"
            "## Status\n\nAccepted\n\n"
            "## Context\n\nWe need a fast local index.\n\n"
            "## Decision\n\nUse SQLite FTS5 because it ships with Python.\n\n"
            "## Consequences\n\nNo external DB dependency.\n",
            encoding="utf-8",
        )
        store = WikiStore(repo / "wiki")
        result = store.ingest_decisions(repo_root=repo)
        check(bool(result["created"]), f"(d) ingest_decisions created pages (got {result})")
        # The created decision page must exist on disk and be a decision type.
        created_rel = result["created"][0]
        page_path = store.root / created_rel
        check(page_path.exists(), f"(d) ADR ingest wrote a page at {created_rel}")
        text = page_path.read_text(encoding="utf-8")
        check("type: decision" in text, "(d) ingested ADR page is type: decision")
        check("sqlite" in text.lower(), "(d) ingested ADR page preserves source content")


def test_ingest_decisions_md() -> None:
    with tempfile.TemporaryDirectory() as td:
        repo = Path(td) / "repo"
        repo.mkdir(parents=True, exist_ok=True)
        (repo / "DECISIONS.md").write_text(
            "# Project Decisions\n\nWe chose monorepo layout to avoid sync drift.\n",
            encoding="utf-8",
        )
        store = WikiStore(repo / "wiki")
        result = store.ingest_decisions(repo_root=repo)
        check(len(result["created"]) >= 1, f"(d) DECISIONS.md ingested (got {result})")


def main() -> int:
    tests = [
        test_degraded_normal_is_ok,
        test_degraded_tiny_store_skips_floor,
        test_degraded_under_persist_triggers,
        test_degraded_ratio_env_tunable,
        test_unsupported_query_raises,
        test_valid_zero_match_is_empty,
        test_cli_unsupported_query_nonzero_exit,
        test_cli_valid_zero_match_zero_exit,
        test_decision_template_has_adr_fields,
        test_ingest_adr_creates_decision_page,
        test_ingest_decisions_md,
    ]
    for t in tests:
        t()
    print()
    if FAILURES:
        print(f"test_wiki_adoption: {len(FAILURES)} FAILURE(S)")
        return 1
    print("test_wiki_adoption: ALL PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
