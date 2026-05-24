#!/usr/bin/env python3
"""Smoke tests for memory-decay/tools/decay.py."""
from __future__ import annotations

import datetime as dt
import math
import re
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from decay import (  # noqa: E402
    DEFAULT_HALFLIFE_DAYS,
    EVIDENCE_PROTECT_THRESHOLD,
    PROTECTED_DIRS,
    PROTECTED_TYPES,
    decay_all,
    parse_frontmatter,
    rewrite_confidence,
)


def _page(title: str, conf: float, updated: str, type_: str = "fact",
          extra: dict[str, str] | None = None) -> str:
    fm = [
        "---",
        "schema_version: 2",
        f"title: {title}",
        f"type: {type_}",
        f"confidence: {conf:.2f}",
        f"updated: {updated}",
        f"created: {updated}",
    ]
    for k, v in (extra or {}).items():
        fm.append(f"{k}: {v}")
    fm.append("---")
    fm.append(f"\n# {title}\nbody.\n")
    return "\n".join(fm)


def _setup(root: Path, pages: dict[str, str]) -> None:
    for rel, content in pages.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content)


def test_parse_frontmatter_basic() -> None:
    text = _page("X", 0.8, "2026-01-01")
    fm, body, span = parse_frontmatter(text)
    assert fm.get("confidence") == "0.80", fm
    assert "# X" in body
    assert span is not None


def test_rewrite_confidence() -> None:
    text = _page("X", 0.8, "2026-01-01")
    new = rewrite_confidence(text, 0.42)
    assert new is not None
    assert "confidence: 0.42" in new
    assert "confidence: 0.80" not in new


def test_decay_dry_run_does_not_write() -> None:
    with tempfile.TemporaryDirectory() as td:
        root = Path(td) / "wiki"
        root.mkdir()
        (root / "schema.md").write_text("schema\n")
        _setup(root, {"L2_facts/old.md": _page("Old", 0.9, "2024-01-01")})
        report = decay_all(
            wiki_root=root, halflife_days=DEFAULT_HALFLIFE_DAYS,
            today=dt.date(2026, 1, 1), apply=False, archive_threshold=0.0,
            protected_types=PROTECTED_TYPES, protected_dirs=PROTECTED_DIRS,
            evidence_threshold=EVIDENCE_PROTECT_THRESHOLD,
        )
        changed = [p for p in report.pages if p.changed]
        assert changed, "should report decay in dry-run"
        # file should not have been mutated
        assert "confidence: 0.90" in (root / "L2_facts/old.md").read_text()


def test_decay_apply_writes_new_confidence() -> None:
    with tempfile.TemporaryDirectory() as td:
        root = Path(td) / "wiki"
        root.mkdir()
        (root / "schema.md").write_text("schema\n")
        _setup(root, {"L2_facts/old.md": _page("Old", 0.9, "2024-01-01")})
        before = (root / "L2_facts/old.md").read_text()
        report = decay_all(
            wiki_root=root, halflife_days=DEFAULT_HALFLIFE_DAYS,
            today=dt.date(2026, 1, 1), apply=True, archive_threshold=0.0,
            protected_types=PROTECTED_TYPES, protected_dirs=PROTECTED_DIRS,
            evidence_threshold=EVIDENCE_PROTECT_THRESHOLD,
        )
        after = (root / "L2_facts/old.md").read_text()
        assert before != after
        assert "confidence: 0.9" not in after.replace("0.90", "0.9_keep")
        # ~ 2 years idle → exp(-ln2/405 * 730) ≈ 0.286
        expected = round(0.9 * math.exp(-math.log(2) / DEFAULT_HALFLIFE_DAYS * 730), 2)
        assert f"confidence: {expected:.2f}" in after, after


def test_protected_error_type_does_not_decay() -> None:
    with tempfile.TemporaryDirectory() as td:
        root = Path(td) / "wiki"
        root.mkdir()
        (root / "schema.md").write_text("schema\n")
        _setup(root, {"L2_facts/lesson.md": _page("Lesson", 0.9, "2024-01-01", type_="error")})
        report = decay_all(
            wiki_root=root, halflife_days=DEFAULT_HALFLIFE_DAYS,
            today=dt.date(2026, 1, 1), apply=True, archive_threshold=0.0,
            protected_types=PROTECTED_TYPES, protected_dirs=PROTECTED_DIRS,
            evidence_threshold=EVIDENCE_PROTECT_THRESHOLD,
        )
        # File should be unchanged
        assert "confidence: 0.90" in (root / "L2_facts/lesson.md").read_text()
        page = next(p for p in report.pages if "lesson" in p.path)
        assert page.protected
        assert "type=error" in page.protection_reason


def test_evidence_count_protects() -> None:
    with tempfile.TemporaryDirectory() as td:
        root = Path(td) / "wiki"
        root.mkdir()
        (root / "schema.md").write_text("schema\n")
        _setup(root, {
            "L2_facts/cited.md": _page("Cited", 0.9, "2024-01-01",
                                         extra={"evidence_count": "5"}),
        })
        report = decay_all(
            wiki_root=root, halflife_days=DEFAULT_HALFLIFE_DAYS,
            today=dt.date(2026, 1, 1), apply=True, archive_threshold=0.0,
            protected_types=PROTECTED_TYPES, protected_dirs=PROTECTED_DIRS,
            evidence_threshold=EVIDENCE_PROTECT_THRESHOLD,
        )
        page = next(p for p in report.pages if "cited" in p.path)
        assert page.protected
        assert "evidence_count" in page.protection_reason


def test_l3_sops_dir_protected() -> None:
    with tempfile.TemporaryDirectory() as td:
        root = Path(td) / "wiki"
        root.mkdir()
        (root / "schema.md").write_text("schema\n")
        _setup(root, {
            "L3_sops/recipe.md": _page("Recipe", 0.9, "2024-01-01", type_="fact"),
        })
        report = decay_all(
            wiki_root=root, halflife_days=DEFAULT_HALFLIFE_DAYS,
            today=dt.date(2026, 1, 1), apply=True, archive_threshold=0.0,
            protected_types=PROTECTED_TYPES, protected_dirs=PROTECTED_DIRS,
            evidence_threshold=EVIDENCE_PROTECT_THRESHOLD,
        )
        page = next(p for p in report.pages if "recipe" in p.path)
        assert page.protected, page
        assert "L3_sops" in page.protection_reason


def test_quoted_confidence_rewrite() -> None:
    """REGRESSION: PyYAML-style quoted scalar broke --apply silently."""
    text = (
        '---\nschema_version: 2\ntitle: X\ntype: fact\n'
        'confidence: "0.80"\nupdated: 2024-01-01\ncreated: 2024-01-01\n---\n# X\n'
    )
    fm, _, _ = parse_frontmatter(text)
    assert fm.get("confidence") == "0.80", "quoted value should be unquoted on parse"
    from decay import rewrite_confidence
    new = rewrite_confidence(text, 0.42)
    assert new is not None, "rewrite should not return None for quoted confidence"
    assert ('confidence: "0.42"' in new) or ("confidence: 0.42" in new), new


def test_crlf_and_bom_frontmatter() -> None:
    """REGRESSION: BOM-prefixed or CRLF-line-ended pages were silently skipped."""
    crlf = (
        "---\r\nschema_version: 2\r\ntitle: X\r\nconfidence: 0.9\r\n"
        "updated: 2024-01-01\r\ncreated: 2024-01-01\r\n---\r\n# body\r\n"
    )
    fm, _, _ = parse_frontmatter(crlf)
    assert fm.get("confidence") == "0.9", f"CRLF should parse: {fm}"

    bom = "﻿" + (
        "---\nschema_version: 2\ntitle: X\nconfidence: 0.9\n"
        "updated: 2024-01-01\ncreated: 2024-01-01\n---\n# body\n"
    )
    fm2, _, _ = parse_frontmatter(bom)
    assert fm2.get("confidence") == "0.9", f"BOM should parse: {fm2}"


def test_fallback_config_no_pyyaml_safe() -> None:
    """REGRESSION: fallback parser used to corrupt nested values into strings."""
    import sys as _sys
    saved = _sys.modules.get("yaml")
    _sys.modules["yaml"] = None  # type: ignore
    try:
        # Re-import load_config so it picks up the simulated missing yaml
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "memory_decay_config.yaml").write_text(
                "halflife_days: 365\n"
                "protected_types:\n"
                "  - error\n"
                "  - lesson\n"
                "evidence_count_threshold: 5\n"
            )
            from decay import load_config
            cfg = load_config(root)
            # Nested list MUST be skipped (None or absent), not stringified
            assert cfg.get("halflife_days") == "365", f"scalar should remain: {cfg}"
            # Nested key either absent OR ignored — must not be a string we'd
            # iterate per-character
            v = cfg.get("protected_types")
            assert v is None or isinstance(v, (list, dict)), \
                f"nested key must not be a raw string: {v!r}"
            # scalar after nested key still parsed
            assert cfg.get("evidence_count_threshold") == "5", cfg
    finally:
        if saved is not None:
            _sys.modules["yaml"] = saved
        else:
            del _sys.modules["yaml"]


def test_apply_atomic_write_no_partial_files() -> None:
    """REGRESSION: write was non-atomic — a crash mid-write would leave a partial
    page. Now uses temp file + os.replace. Verify no .tmp file is left behind on
    successful run, and the page is intact."""
    import os as _os
    with tempfile.TemporaryDirectory() as td:
        root = Path(td) / "wiki"
        root.mkdir()
        (root / "schema.md").write_text("schema\n")
        p = root / "L2_facts" / "x.md"
        p.parent.mkdir()
        p.write_text(
            "---\nschema_version: 2\ntitle: X\ntype: fact\n"
            "confidence: 0.9\nupdated: 2024-01-01\ncreated: 2024-01-01\n---\n# body\n"
        )
        decay_all(
            wiki_root=root, halflife_days=DEFAULT_HALFLIFE_DAYS,
            today=dt.date(2026, 1, 1), apply=True, archive_threshold=0.0,
            protected_types=PROTECTED_TYPES, protected_dirs=PROTECTED_DIRS,
            evidence_threshold=EVIDENCE_PROTECT_THRESHOLD,
        )
        # No leftover .tmp files
        tmp_files = list(p.parent.glob("*.tmp"))
        assert not tmp_files, f"left behind tmp files: {tmp_files}"
        # Page intact (single confidence line + body present)
        text = p.read_text()
        assert text.count("confidence:") == 1
        assert "# body" in text


def test_apply_bumps_verified_to_avoid_compound_decay() -> None:
    """REGRESSION: weekly decay used to compound because verified: was not bumped.
    After --apply, verified: must be today so the next run measures only delta."""
    with tempfile.TemporaryDirectory() as td:
        root = Path(td) / "wiki"
        root.mkdir()
        (root / "schema.md").write_text("schema\n")
        page = (root / "L2_facts" / "x.md")
        page.parent.mkdir()
        page.write_text(
            "---\nschema_version: 2\ntitle: X\ntype: fact\n"
            "confidence: 0.90\nupdated: 2024-01-01\ncreated: 2024-01-01\n"
            "verified: 2024-01-01\n---\n# body\n"
        )
        # First run: large decay
        decay_all(
            wiki_root=root, halflife_days=DEFAULT_HALFLIFE_DAYS,
            today=dt.date(2026, 1, 1), apply=True, archive_threshold=0.0,
            protected_types=PROTECTED_TYPES, protected_dirs=PROTECTED_DIRS,
            evidence_threshold=EVIDENCE_PROTECT_THRESHOLD,
        )
        text_after_first = page.read_text()
        assert "verified: 2026-01-01" in text_after_first, \
            f"verified should be bumped to today, got:\n{text_after_first}"
        # Second run 1 week later: should be near-zero delta now, not another full decay
        decay_all(
            wiki_root=root, halflife_days=DEFAULT_HALFLIFE_DAYS,
            today=dt.date(2026, 1, 8), apply=True, archive_threshold=0.0,
            protected_types=PROTECTED_TYPES, protected_dirs=PROTECTED_DIRS,
            evidence_threshold=EVIDENCE_PROTECT_THRESHOLD,
        )
        text_after_second = page.read_text()
        # 7 days at 405d halflife → factor ≈ 0.988; confidence should drop ≈ 1%
        m = re.search(r"^confidence:\s*([\d.]+)", text_after_second, re.M)
        c = float(m.group(1))
        # Should still be near the post-first-run value (~0.26), NOT compound-decayed
        m2 = re.search(r"^confidence:\s*([\d.]+)", text_after_first, re.M)
        c_first = float(m2.group(1))
        # 7d → 1% drop, allow some rounding
        assert c >= c_first - 0.02, \
            f"second-week decay should be ~1%, got {c_first:.2f} → {c:.2f}"


def test_archive_candidates() -> None:
    with tempfile.TemporaryDirectory() as td:
        root = Path(td) / "wiki"
        root.mkdir()
        (root / "schema.md").write_text("schema\n")
        # 4-year-old confidence 0.5: decays to ~ 0.5 * 0.13 = 0.066
        _setup(root, {
            "L2_facts/ancient.md": _page("Ancient", 0.5, "2022-01-01"),
            "L2_facts/fresh.md":   _page("Fresh", 0.9, "2025-12-01"),
        })
        report = decay_all(
            wiki_root=root, halflife_days=DEFAULT_HALFLIFE_DAYS,
            today=dt.date(2026, 1, 1), apply=False, archive_threshold=0.3,
            protected_types=PROTECTED_TYPES, protected_dirs=PROTECTED_DIRS,
            evidence_threshold=EVIDENCE_PROTECT_THRESHOLD,
        )
        assert any("ancient" in c for c in report.archive_candidates)
        assert not any("fresh" in c for c in report.archive_candidates)


def main() -> int:
    tests = [
        test_parse_frontmatter_basic,
        test_rewrite_confidence,
        test_decay_dry_run_does_not_write,
        test_decay_apply_writes_new_confidence,
        test_protected_error_type_does_not_decay,
        test_evidence_count_protects,
        test_l3_sops_dir_protected,
        test_quoted_confidence_rewrite,
        test_crlf_and_bom_frontmatter,
        test_fallback_config_no_pyyaml_safe,
        test_apply_atomic_write_no_partial_files,
        test_apply_bumps_verified_to_avoid_compound_decay,
        test_archive_candidates,
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
