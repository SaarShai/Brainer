#!/usr/bin/env python3
"""Plain-python tests for staleness.py (no pytest dep). Exit code = verdict."""
from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import staleness as st

FAILS: list[str] = []


def check(name, got, want):
    if got != want:
        FAILS.append(f"{name}: got {got!r} want {want!r}")
        print(f"  [FAIL] {name}: got {got!r} want {want!r}")
    else:
        print(f"  [PASS] {name}")


def _git(root, *a):
    subprocess.run(["git", "-C", str(root), *a], capture_output=True, text=True, check=False)


def _commit(root, fname, content):
    (root / fname).write_text(content)
    _git(root, "add", "-A")
    _git(root, "commit", "-qm", f"edit {fname}")


def main() -> int:
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        _git(root, "init", "-q")
        _git(root, "config", "user.email", "t@t")
        _git(root, "config", "user.name", "t")
        _commit(root, "a.py", "def f():\n    return 1\n")

        print("== no marker -> not stale (don't nag before first reconcile) ==")
        check("no-marker not stale", st.is_stale(root)["stale"], False)

        print("== mark-refreshed then fresh ==")
        m = st.mark_refreshed(root)
        check("mark ok", m["ok"], True)
        check("fresh after mark", st.is_stale(root)["stale"], False)

        print("== nudge silent on fresh (cache-safe) ==")
        out = subprocess.run([sys.executable, str(Path(__file__).parent / "staleness.py"),
                              "nudge", "--root", str(root)], capture_output=True, text=True)
        check("nudge fresh exit 0", out.returncode, 0)
        check("nudge fresh empty", out.stdout.strip(), "")

        print("== commit advances HEAD -> stale ==")
        _commit(root, "a.py", "def f():\n    return 2\n")
        r = st.is_stale(root)
        check("stale after commit", r["stale"], True)
        check("counts code change", r["code_changed"] >= 1, True)

        print("== nudge fires when stale ==")
        out = subprocess.run([sys.executable, str(Path(__file__).parent / "staleness.py"),
                              "nudge", "--root", str(root)], capture_output=True, text=True)
        check("nudge stale exit 0", out.returncode, 0)
        check("nudge stale non-empty", bool(out.stdout.strip()), True)
        check("nudge mentions wiki-refresh", "wiki-refresh" in out.stdout, True)

        print("== re-mark clears staleness ==")
        st.mark_refreshed(root)
        check("fresh after re-mark", st.is_stale(root)["stale"], False)

        print("== corrupt markers must NOT crash (edge-hunter regressions) ==")
        marker = root / "wiki" / ".refresh-state.json"
        for bad in ('[1,2,3]', 'null', '123', '"abc"', '{not json', '{"gitCommitHash": 123}'):
            marker.write_text(bad)
            r = st.is_stale(root)  # must not raise
            check(f"is_stale survives {bad[:14]!r}", isinstance(r, dict), True)
            out = subprocess.run([sys.executable, str(Path(__file__).parent / "staleness.py"),
                                  "nudge", "--root", str(root)], capture_output=True, text=True)
            check(f"nudge no-crash exit 0 {bad[:10]!r}", out.returncode, 0)
            check(f"nudge no traceback {bad[:10]!r}", "Traceback" in out.stderr, False)

        print("== keys always present ==")
        st.mark_refreshed(root)
        r = st.is_stale(root)
        for k in ("stale", "stored", "head", "changed", "code_changed"):
            check(f"key {k} present (fresh)", k in r, True)

        print("== marker's own path not counted ==")
        # commit the marker, then make a docs-only change; marker path must be filtered out
        st.mark_refreshed(root)
        _git(root, "add", "-A"); _git(root, "commit", "-qm", "commit marker")
        st.mark_refreshed(root)
        base = st.is_stale(root)
        check("fresh right after mark", base["stale"], False)
        (root / "README.md").write_text("docs\n")
        _git(root, "add", "README.md"); _git(root, "commit", "-qm", "docs only")
        r = st.is_stale(root)
        check("stale after docs commit", r["stale"], True)
        check("marker path excluded from count", r["changed"], 1)  # README only, not the marker

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
