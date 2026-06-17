#!/usr/bin/env python3
"""wiki-memory fuzz: frontmatter parser robustness + wiki.py CLI on weird trees.

Specifically targets the parser bugs the reviewer found mirroring memory-decay:
  - CRLF line endings
  - UTF-8 BOM prefix
  - Quoted scalar values
  - Block-list values (`tags:\n  - foo\n  - bar`)
  - Multi-line scalars  (intentionally not handled — documented limitation)
  - Empty / malformed / huge inputs
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _lib import REPO, Report, Timer, import_skill_module, print_report, write_report  # noqa: E402

wiki_mod = import_skill_module("wiki-memory", "wiki")
parse_frontmatter = wiki_mod.parse_frontmatter
strip_fenced_code = wiki_mod.strip_fenced_code
render_template = wiki_mod.render_template
WikiStore = wiki_mod.WikiStore


def _page(fm_lines: list[str], body: str = "# body\n", line_ending: str = "\n",
          bom: bool = False) -> str:
    parts = ["---"] + fm_lines + ["---", "", body.rstrip()]
    text = line_ending.join(parts) + line_ending
    return ("﻿" + text) if bom else text


def case(name: str, ok: bool, **extra) -> dict:
    return {"case": name, "ok": ok, **extra}


def t_lf_basic() -> dict:
    text = _page(["title: X", "type: fact", "confidence: 0.8"])
    fm, body = parse_frontmatter(text)
    return case("lf_basic",
                fm.get("title") == "X" and fm.get("confidence") == "0.8" and "body" in body,
                fm=fm)


def t_crlf() -> dict:
    """REGRESSION FOR C1: CRLF must parse."""
    text = _page(["title: X", "type: fact", "confidence: 0.8"], line_ending="\r\n")
    fm, _ = parse_frontmatter(text)
    return case("crlf_lines",
                fm.get("title") == "X" and fm.get("confidence") == "0.8",
                fm=fm)


def t_bom() -> dict:
    """REGRESSION FOR C1: BOM-prefixed must parse."""
    text = _page(["title: X", "type: fact", "confidence: 0.8"], bom=True)
    fm, _ = parse_frontmatter(text)
    return case("bom_utf8",
                fm.get("title") == "X",
                fm=fm)


def t_quoted_scalars() -> dict:
    text = _page(['title: "Hello: World"', "confidence: '0.9'", "tags: 'a, b'"])
    fm, _ = parse_frontmatter(text)
    return case("quoted_scalars",
                fm.get("title") == "Hello: World" and fm.get("confidence") == "0.9",
                fm=fm)


def t_block_list() -> dict:
    """REGRESSION FOR C1: tag lists in block form were silently lost."""
    text = "---\ntitle: X\ntags:\n  - foo\n  - bar\n  - baz\nconfidence: 0.5\n---\n# body\n"
    fm, _ = parse_frontmatter(text)
    return case("block_list_tags",
                fm.get("tags", "").startswith("[") and "foo" in fm.get("tags", "")
                and fm.get("confidence") == "0.5",
                fm=fm)


def t_empty() -> dict:
    fm, body = parse_frontmatter("")
    return case("empty_input", fm == {} and body == "")


def t_no_frontmatter() -> dict:
    fm, body = parse_frontmatter("# Just a heading\nNo frontmatter here.\n")
    return case("no_frontmatter", fm == {} and "Just a heading" in body)


def t_malformed_unclosed() -> dict:
    """Open fence with no close — should return empty dict + original body."""
    fm, body = parse_frontmatter("---\ntitle: X\nNo close here\n# stuff\n")
    return case("unclosed_frontmatter", fm == {})


def t_huge_body() -> dict:
    text = _page(["title: X", "confidence: 0.8"], body="x" * 500_000)
    import time
    t0 = time.time()
    fm, body = parse_frontmatter(text)
    elapsed = time.time() - t0
    return case("huge_body_under_1s",
                fm.get("title") == "X" and len(body) > 400_000 and elapsed < 1.0,
                elapsed_s=round(elapsed, 3))


def t_unicode_values() -> dict:
    text = _page(["title: テスト 中文 العربية", "confidence: 0.8"])
    fm, _ = parse_frontmatter(text)
    return case("unicode_values",
                "テスト" in fm.get("title", ""),
                fm=fm)


def t_value_contains_colon() -> dict:
    """`key: value: with: colons` — value is everything after the first `:`."""
    text = _page(["title: A: B: C", "confidence: 0.5"])
    fm, _ = parse_frontmatter(text)
    return case("value_with_colons",
                fm.get("title") == "A: B: C",
                fm=fm)


def _seed_wiki(root: Path, n: int = 12) -> None:
    """Drop a small set of v2 pages so search/context have something to find."""
    store = WikiStore(root)
    store.init()
    for i in range(n):
        body = (
            "---\n"
            "schema_version: 2\n"
            f"title: Page {i}\n"
            "type: concept\n"
            "domain: framework\n"
            "tier: semantic\n"
            "confidence: 0.7\n"
            "created: 2025-01-01\n"
            "updated: 2025-01-01\n"
            "verified: 2025-01-01\n"
            "sources: [\"https://example.com\"]\n"
            "supersedes: []\n"
            "superseded-by:\n"
            f"tags: [tag{i % 3}, alpha]\n"
            "---\n\n"
            f"# Page {i}\n\n"
            f"Body for alpha page {i}, links to [[Page {(i + 1) % n}]] and alpha topic.\n"
        )
        (root / "concepts" / f"page-{i}.md").write_text(body, encoding="utf-8")


def t_h2_context_reads_each_file_once() -> dict:
    """REGRESSION FOR H2: a single context() must read each markdown file
    at most once per Wiki instance. Old hot path re-read 6-17x per page."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp) / "wiki"
        _seed_wiki(root, n=12)
        # Count read_text on a fresh instance, with DB pre-built so we measure
        # the search/context path, not the initial index build.
        WikiStore(root).index()
        store = WikiStore(root)
        reads: dict[Path, int] = {}
        orig = Path.read_text
        def counted(self, *a, **k):
            reads[self] = reads.get(self, 0) + 1
            return orig(self, *a, **k)
        Path.read_text = counted
        try:
            store.context("alpha", max_pages=5, max_tokens=4000)
        finally:
            Path.read_text = orig
        # Each markdown file under the wiki: read 0 or 1 times.
        md_reads = {p: n for p, n in reads.items() if p.suffix == ".md"}
        over = {str(p): n for p, n in md_reads.items() if n > 1}
        return case(
            "h2_context_reads_each_file_once",
            not over,
            md_files_read=len(md_reads),
            over_read=over,
            total_md_reads=sum(md_reads.values()),
        )


def t_h4_symlink_outside_root() -> dict:
    """REGRESSION FOR H4: a symlink resolving outside the wiki root must
    not crash iter_markdown / read_page with ValueError from relative_to."""
    with tempfile.TemporaryDirectory() as tmp:
        outside = Path(tmp) / "outside"
        outside.mkdir()
        outside_md = outside / "evil.md"
        outside_md.write_text("# outside file\n", encoding="utf-8")
        root = Path(tmp) / "wiki"
        _seed_wiki(root, n=3)
        # Create a symlink inside the wiki pointing outside the root.
        try:
            (root / "concepts" / "linked.md").symlink_to(outside_md)
        except (OSError, NotImplementedError):
            return case("h4_symlink_outside_root", True, note="symlink unsupported")
        store = WikiStore(root)
        try:
            store.index()
            store.search("alpha", k=5)
            ok = True
        except ValueError as e:
            ok = False
            return case("h4_symlink_outside_root", False, error=str(e))
        return case("h4_symlink_outside_root", ok)


def t_h5_concurrent_ingest_no_clobber() -> dict:
    """REGRESSION FOR H5: two concurrent ingests with the same slug must
    produce two distinct files, not silently overwrite one."""
    import threading
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp) / "wiki"
        WikiStore(root).init()
        src = Path(tmp) / "src.txt"
        src.write_text("source content\n", encoding="utf-8")
        results: list[dict] = []
        errors: list[str] = []
        barrier = threading.Barrier(4)
        def runner(idx: int) -> None:
            store = WikiStore(root)
            try:
                barrier.wait(timeout=5)
                r = store.ingest(str(src), title="same-title")
                results.append(r)
            except Exception as e:
                errors.append(f"{idx}: {e!r}")
        threads = [threading.Thread(target=runner, args=(i,)) for i in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)
        created_paths = {r["created"] for r in results}
        # All 4 ingests created distinct files (no clobber).
        ok = len(results) == 4 and len(created_paths) == 4 and not errors
        return case(
            "h5_concurrent_ingest_no_clobber",
            ok,
            n_results=len(results),
            n_unique=len(created_paths),
            errors=errors,
            paths=sorted(created_paths),
        )


def t_h8_manifest_size_cap() -> dict:
    """REGRESSION FOR H8: an oversized manifest must error cleanly, not
    blow memory trying to load and splitlines() the whole file."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp) / "wiki"
        store = WikiStore(root)
        store.init()
        # Write a >10MB junk file.
        big = root / "raw" / "huge-manifest.md"
        big.parent.mkdir(parents=True, exist_ok=True)
        with big.open("w", encoding="utf-8") as f:
            # ~12MB of valid-looking pipe-table lines
            line = "| " + ("x" * 100) + " | " + ("y" * 100) + " | " + ("z" * 100) + " |\n"
            n_lines = (12 * 1024 * 1024) // len(line) + 100
            for _ in range(n_lines):
                f.write(line)
        try:
            store._parse_import_manifest(big)
            return case("h8_manifest_size_cap", False,
                        note="did not raise on oversized manifest")
        except ValueError as e:
            return case("h8_manifest_size_cap", "too large" in str(e),
                        error=str(e))


def t_m1_unbalanced_fence_drops_link() -> dict:
    """REGRESSION FOR M1: with an odd number of ``` fences, wikilinks inside
    the unclosed fence must NOT be indexed (was leaking through)."""
    text = (
        "Real text [[real-link]] outside.\n"
        "```\n"
        "code line [[fake-link-1]]\n"
        "```\n"
        "More prose [[real-link-2]].\n"
        "```python\n"
        "still in code [[fake-link-2]]\n"
        # no closing fence — odd count
    )
    out = strip_fenced_code(text)
    return case(
        "m1_unbalanced_fence_drops_link",
        "real-link" in out and "real-link-2" in out
        and "fake-link-1" not in out and "fake-link-2" not in out,
        stripped=out,
    )


def t_m4_new_page_does_not_full_reindex() -> dict:
    """REGRESSION FOR M4: new_page() must not call index() on the steady path."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp) / "wiki"
        _seed_wiki(root, n=8)
        store = WikiStore(root)
        store.index()  # build DB once
        calls = [0]
        orig = store.index
        def counting_index(*a, **k):
            calls[0] += 1
            return orig(*a, **k)
        store.index = counting_index  # type: ignore
        # force=True: this case exercises the M4 incremental-reindex path, not
        # the content gate — bypass the write-gate/overlap refusal that now
        # guards new_page (a bare-title scaffold is intentionally low-signal).
        store.new_page("page", "Brand New Page", domain="framework", force=True)
        # New page must be findable via search (incremental insert worked)
        hits = store.search("brand new page", k=5)
        found = any(h["title"] == "Brand New Page" for h in hits)
        return case(
            "m4_new_page_does_not_full_reindex",
            calls[0] == 0 and found,
            full_index_calls=calls[0],
            found_via_search=found,
        )


def t_l2_template_no_double_substitute() -> dict:
    """REGRESSION FOR L2: title containing `{{date}}` must NOT get substituted
    in a second pass — sequential .replace() had this bug."""
    out = render_template(
        "title: {{title}}\ncreated: {{date}}\n",
        {"title": "Released on {{date}}", "date": "2026-05-24"},
    )
    # title field should still contain literal "{{date}}", only the date field
    # should be substituted.
    return case(
        "l2_template_no_double_substitute",
        "title: Released on {{date}}" in out and "created: 2026-05-24" in out,
        output=out,
    )


def t_l4_audit_ignores_paths_in_code_fence() -> dict:
    """REGRESSION FOR L4: paths inside ```code``` fences must not trigger
    `index_points_outside_workspace` errors (was matching `/usr/bin/env` etc)."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp) / "wiki"
        store = WikiStore(root)
        store.init()
        (root / "L1_index.md").write_text(
            "# L1\n\n"
            "Real pointers:\n\n"
            "- start -> `start.md`\n\n"
            "Example shebang in a code block (should NOT flag):\n\n"
            "```bash\n"
            "#!/usr/bin/env bash\n"
            "cat /etc/hosts /var/log/syslog\n"
            "```\n",
            encoding="utf-8",
        )
        errors = store._audit_local_indexes()
        flagged_paths = [e.get("path", "") for e in errors]
        # None of the /usr/bin or /etc paths should appear.
        leaked = [p for p in flagged_paths
                  if p.startswith(("/usr/", "/etc/", "/var/"))]
        return case(
            "l4_audit_ignores_paths_in_code_fence",
            not leaked,
            n_errors=len(errors),
            leaked_paths=leaked,
        )


def t_legacy_v1_pages_still_parse() -> dict:
    """Make sure our fixes don't break the existing wiki's v1 pages."""
    wiki_dir = REPO / "wiki"
    if not wiki_dir.exists():
        return case("legacy_v1_pages", ok=True, note="no wiki in repo")
    n_pages = 0
    n_parsed = 0
    n_no_fm = 0
    for p in wiki_dir.rglob("*.md"):
        n_pages += 1
        try:
            text = p.read_text(errors="ignore")
            fm, _ = parse_frontmatter(text)
            if fm:
                n_parsed += 1
            else:
                n_no_fm += 1
        except Exception:
            return case("legacy_v1_pages", False, error=f"failed at {p}")
    return case("legacy_v1_pages", ok=True,
                n_pages=n_pages, n_parsed=n_parsed, n_no_fm=n_no_fm)


CASES = [
    t_lf_basic,
    t_crlf,
    t_bom,
    t_quoted_scalars,
    t_block_list,
    t_empty,
    t_no_frontmatter,
    t_malformed_unclosed,
    t_huge_body,
    t_unicode_values,
    t_value_contains_colon,
    # H/M/L bug regressions (this round)
    t_h2_context_reads_each_file_once,
    t_h4_symlink_outside_root,
    t_h5_concurrent_ingest_no_clobber,
    t_h8_manifest_size_cap,
    t_m1_unbalanced_fence_drops_link,
    t_m4_new_page_does_not_full_reindex,
    t_l2_template_no_double_substitute,
    t_l4_audit_ignores_paths_in_code_fence,
    t_legacy_v1_pages_still_parse,
]


def main() -> int:
    t = Timer()
    results = [c() for c in CASES]
    failed = [r for r in results if not r["ok"]]
    report = Report(
        skill="wiki_memory", shape="fuzz", elapsed_s=t.elapsed(),
        summary={"n_cases": len(CASES), "failed": len(failed)},
        findings=failed,
    )
    report.passed = not failed
    print_report(report)
    for r in results:
        mark = "ok" if r["ok"] else "FAIL"
        extra = ""
        if "fm" in r and isinstance(r["fm"], dict):
            extra = f"  fm_keys={list(r['fm'].keys())}"
        elif "n_pages" in r:
            extra = f"  pages={r['n_pages']} parsed={r['n_parsed']} no_fm={r['n_no_fm']}"
        elif "elapsed_s" in r:
            extra = f"  elapsed={r['elapsed_s']}s"
        print(f"  [{mark}] {r['case']:<40}{extra}")
    path = write_report(report)
    print(f"\nfull JSON: {path}")
    return 0 if report.passed else 1


if __name__ == "__main__":
    sys.exit(main())
