#!/usr/bin/env python3
"""Plain-python tests for disuse.py (no pytest dep). Exit code = verdict.

Cases (per brief):
  - 0-read old page (past grace window)      -> candidate
  - 0-read new page (inside grace window)     -> not candidate
  - read page (reads > threshold)             -> not candidate
  - missing usage.json                        -> empty usage, no crash
  - malformed usage.json                      -> empty usage, no crash
  - page with no created:/updated: frontmatter -> age unknown, not candidate
"""
from __future__ import annotations

import datetime as _dt
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import disuse as du

FAILS: list[str] = []


def check(name, got, want):
    if got != want:
        FAILS.append(f"{name}: got {got!r} want {want!r}")
        print(f"  [FAIL] {name}: got {got!r} want {want!r}")
    else:
        print(f"  [PASS] {name}")


def _write_page(root: Path, subdir: str, name: str, created: str) -> None:
    d = root / subdir
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{name}.md").write_text(
        f'---\nschema_version: 2\ntitle: "{name}"\ntype: concept\n'
        f'created: "{created}"\nupdated: "{created}"\n---\n\n# {name}\n\nbody\n'
    )


def main() -> int:
    import tempfile

    today = _dt.date(2026, 7, 6)
    old_date = (today - _dt.timedelta(days=90)).isoformat()
    new_date = (today - _dt.timedelta(days=5)).isoformat()

    with tempfile.TemporaryDirectory() as d:
        root = Path(d)

        print("== missing usage.json -> empty, no crash ==")
        check("load_usage empty on missing file", du.load_usage(root), {})

        _write_page(root, "concepts", "old-unread", old_date)
        _write_page(root, "concepts", "new-unread", new_date)
        _write_page(root, "concepts", "old-read", old_date)
        _write_page(root, "concepts", "no-date-page", "")
        (root / "concepts" / "no-date-page.md").write_text(
            "---\nschema_version: 2\ntitle: no-date-page\ntype: concept\n---\n\nbody\n"
        )

        usage_dir = root / ".brainer"
        usage_dir.mkdir(parents=True, exist_ok=True)
        (usage_dir / "usage.json").write_text(json.dumps({"concepts/old-read": 2}))

        rows = {r["page"]: r for r in du.report(root, today=today)}

        print("== 0-read old page (past grace window) -> candidate ==")
        check("old-unread candidate", rows["concepts/old-unread"]["candidate"], True)
        check("old-unread reads", rows["concepts/old-unread"]["reads"], 0)
        check("old-unread age_days", rows["concepts/old-unread"]["age_days"], 90)

        print("== 0-read new page (inside grace window) -> not candidate ==")
        check("new-unread not candidate", rows["concepts/new-unread"]["candidate"], False)
        check("new-unread age_days", rows["concepts/new-unread"]["age_days"], 5)

        print("== read page -> not candidate regardless of age ==")
        check("old-read not candidate", rows["concepts/old-read"]["candidate"], False)
        check("old-read reads", rows["concepts/old-read"]["reads"], 2)

        print("== page with no created:/updated: -> age unknown, never a candidate ==")
        check("no-date-page age unknown", rows["concepts/no-date-page"]["age_days"], None)
        check("no-date-page not candidate", rows["concepts/no-date-page"]["candidate"], False)

        print("== malformed usage.json -> empty usage, no crash ==")
        (usage_dir / "usage.json").write_text("{not json")
        check("load_usage empty on malformed JSON", du.load_usage(root), {})
        rows2 = du.report(root, today=today)  # must not raise
        check("report survives malformed usage.json", isinstance(rows2, list), True)

        print("== empty usage.json -> empty, no crash ==")
        (usage_dir / "usage.json").write_text("{}")
        check("load_usage empty on empty object", du.load_usage(root), {})

        print("== non-dict usage.json (list) -> empty, no crash ==")
        (usage_dir / "usage.json").write_text("[1, 2, 3]")
        check("load_usage empty on non-dict JSON", du.load_usage(root), {})

        print("== configurable grace-days / read-threshold ==")
        (usage_dir / "usage.json").write_text(json.dumps({"concepts/old-read": 2}))
        rows3 = {r["page"]: r for r in du.report(root, grace_days=200, today=today)}
        check("wider grace window exempts old-unread", rows3["concepts/old-unread"]["candidate"], False)
        rows4 = {r["page"]: r for r in du.report(root, read_threshold=2, today=today)}
        check("raised read-threshold flags old-read too", rows4["concepts/old-read"]["candidate"], True)

        print("== CLI: report subcommand runs clean against a real root ==")
        import subprocess

        out = subprocess.run(
            [sys.executable, str(Path(__file__).parent / "disuse.py"),
             "report", "--root", str(root)],
            capture_output=True, text=True,
        )
        check("CLI report exit 0", out.returncode, 0)
        try:
            parsed = json.loads(out.stdout)
            cli_ok = isinstance(parsed, list) and len(parsed) == 4
        except ValueError:
            cli_ok = False
        check("CLI report emits JSON list of all pages", cli_ok, True)

    print()
    if FAILS:
        print(f"FAILED: {len(FAILS)}")
        for x in FAILS:
            print("  -", x)
        return 1
    print("ALL PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
