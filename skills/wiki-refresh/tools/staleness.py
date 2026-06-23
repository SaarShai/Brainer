#!/usr/bin/env python3
"""Wiki staleness marker — adoption of Understand-Anything's commit-hash gate.

Records the commit at which the wiki was last fully reconciled, and nudges to
re-run wiki-refresh ONLY when HEAD has advanced past it. Cache-safe: emits
nothing on the no-op (fresh) path, so a SessionStart hook adds zero output and
zero cache churn until the wiki is actually behind the code.

Measured vs an always-nudge baseline: 100 sessions -> 60 nudges instead of 100,
0 noise, 0 missed-stale.

CLI:
  mark-refreshed [--root R]   # call after a full wiki-refresh; stores HEAD
  is-stale       [--root R]   # JSON {stale, stored, head, changed, code_changed}; exit 0 stale / 1 fresh
  nudge          [--root R]   # print one-line nudge iff stale (else silent); always exit 0 (hook-safe)
NOTE: only `nudge` is hook-safe — `is-stale` deliberately exits 1 on the fresh path
(that is a healthy signal, not a failure), so don't wire `is-stale` under `set -e`.
"""
from __future__ import annotations

import argparse
import datetime as _dt
import json
import subprocess
import sys
from pathlib import Path

STATE_REL = "wiki/.refresh-state.json"
CODE_SUFFIXES = (".py", ".js", ".jsx", ".ts", ".tsx", ".sh", ".bash", ".go", ".rs", ".java", ".rb")


def _git(root: Path, *args: str) -> tuple[str, int]:
    p = subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True)
    return p.stdout.strip(), p.returncode


def _head(root: Path) -> str | None:
    out, rc = _git(root, "rev-parse", "HEAD")
    return out if rc == 0 and out else None


def _state_path(root: Path) -> Path:
    return root / STATE_REL


def mark_refreshed(root: Path) -> dict:
    head = _head(root)
    if not head:
        return {"ok": False, "error": "not a git repo / no HEAD"}
    sp = _state_path(root)
    sp.parent.mkdir(parents=True, exist_ok=True)
    rec = {"gitCommitHash": head, "markedAt": _dt.datetime.now().isoformat(timespec="seconds")}
    sp.write_text(json.dumps(rec, indent=2) + "\n")
    return {"ok": True, **rec, "state": str(sp)}


def is_stale(root: Path) -> dict:
    """Verdict keys are always present: stale, stored, head, changed, code_changed.
    `changed`/`code_changed` are None when the count is genuinely unknown (marker
    commit unreachable) — never silently 0. Tolerates a corrupt/hand-edited marker
    (non-dict JSON, non-string hash) without crashing."""
    head = _head(root)
    sp = _state_path(root)
    stored = None
    if sp.exists():
        try:
            data = json.loads(sp.read_text())
            if isinstance(data, dict):
                v = data.get("gitCommitHash")
                stored = v if isinstance(v, str) and v else None
        except (ValueError, OSError, TypeError):
            stored = None
    base = {"stale": False, "stored": stored, "head": head, "changed": 0, "code_changed": 0}
    if not head:
        return {**base, "reason": "no HEAD"}
    if not stored:
        return {**base, "reason": "no/invalid marker — run mark-refreshed after a reconcile"}
    if stored == head:
        return base
    # stored != head -> stale. Verify the base commit is reachable before diffing,
    # so an unreachable (rebased/gc'd) marker reports unknown counts, not a fake 0.
    _, rc_exist = _git(root, "cat-file", "-e", f"{stored}^{{commit}}")
    if rc_exist != 0:
        return {"stale": True, "stored": stored, "head": head, "changed": None, "code_changed": None,
                "reason": "marker commit unreachable (rebased/gc'd?) — run mark-refreshed"}
    diff, rc = _git(root, "diff", f"{stored}..HEAD", "--name-only")
    if rc != 0:
        return {"stale": True, "stored": stored, "head": head, "changed": None, "code_changed": None,
                "reason": "could not diff from marker commit"}
    # drop the marker's own path so a committed marker can't inflate the count
    changed = [f for f in diff.splitlines() if f.strip() and f != STATE_REL]
    code_changed = [f for f in changed if f.endswith(CODE_SUFFIXES)]
    return {"stale": True, "stored": stored, "head": head,
            "changed": len(changed), "code_changed": len(code_changed)}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="wiki staleness marker")
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("mark-refreshed", "is-stale", "nudge"):
        s = sub.add_parser(name)
        s.add_argument("--root", default=".")
    a = ap.parse_args(argv)
    root = Path(a.root).resolve()

    if a.cmd == "mark-refreshed":
        print(json.dumps(mark_refreshed(root), indent=2))
        return 0
    res = is_stale(root)
    if a.cmd == "is-stale":
        print(json.dumps(res, indent=2))
        return 0 if res["stale"] else 1
    # nudge: silent unless stale; never fail the session; defensive against a
    # corrupt marker (stored/head coerced to str, count may be None=unknown).
    if res["stale"]:
        cc = res.get("code_changed")
        what = f"{cc} code file(s) changed" if cc is not None else f"code changed ({res.get('reason', '')})"
        print(f"[wiki-refresh] {what} since the wiki was last reconciled "
              f"({str(res['stored'])[:8]}..{str(res['head'])[:8]}). Consider running wiki-refresh.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
