#!/usr/bin/env python3
"""lane_guard.py — leader-side post-lane git-safety check.

Hooks do not fire inside subagents, so a rogue lane running state-changing
git (checkout/reset/stash/commit) on the shared tree is invisible to any
in-lane guard (2026-07-06: `git checkout -- <19 paths>` wiped 5 concurrent
lanes' uncommitted work). This tool runs LEADER-side instead: snapshot the
repo state before dispatching a wave of lanes, then check after each lane
returns.

Strictly read-only w.r.t. git: only `git status`, `git stash list`,
`git rev-parse`, and `git hash-object` are ever invoked. Never run this
tool's `snapshot`/`check` subcommands as a substitute for actual git
mutation — it does not, and must never, mutate the repo it inspects.

Usage:
    lane_guard.py snapshot [--repo PATH]
    lane_guard.py check [--repo PATH] [--json]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import time
from pathlib import Path

SNAPSHOT_REL = Path(".brainer/lane_guard/snapshot.json")


def _run(repo: Path, args: list[str]) -> str:
    out = subprocess.run(
        ["git", "-C", str(repo)] + args,
        capture_output=True, text=True, check=True,
    )
    return out.stdout


def _git_status(repo: Path) -> list[tuple[str, str]]:
    """Return [(status_code, path), ...] from `git status --porcelain`."""
    raw = _run(repo, ["status", "--porcelain"])
    entries = []
    for line in raw.splitlines():
        if not line:
            continue
        code = line[:2]
        path = line[3:]
        if " -> " in path:  # rename/copy: "old -> new"; track the new path
            path = path.split(" -> ", 1)[1]
        entries.append((code, path))
    return entries


def _stash_count(repo: Path) -> int:
    raw = _run(repo, ["stash", "list"])
    return len([l for l in raw.splitlines() if l.strip()])


def _head_sha(repo: Path) -> str:
    return _run(repo, ["rev-parse", "HEAD"]).strip()


def _file_hash(repo: Path, path: str) -> str | None:
    """Content hash of a working-tree file via `git hash-object` (read-only,
    does not require the file to be tracked). None if the file is gone."""
    full = repo / path
    if not full.exists() or full.is_dir():
        return None
    try:
        return _run(repo, ["hash-object", "--", path]).strip()
    except subprocess.CalledProcessError:
        return None


def _status_hash(entries: list[tuple[str, str]]) -> str:
    blob = "\n".join(f"{c}\t{p}" for c, p in sorted(entries))
    return hashlib.sha256(blob.encode()).hexdigest()


def cmd_snapshot(repo: Path) -> int:
    entries = _git_status(repo)
    files = {path: {"status": code, "hash": _file_hash(repo, path)}
             for code, path in entries}
    snap = {
        "timestamp": time.time(),
        "head": _head_sha(repo),
        "stash_count": _stash_count(repo),
        "status_hash": _status_hash(entries),
        "files": files,
    }
    snap_path = repo / SNAPSHOT_REL
    snap_path.parent.mkdir(parents=True, exist_ok=True)
    snap_path.write_text(json.dumps(snap, indent=2))
    print(
        f"lane_guard snapshot: HEAD={snap['head'][:12]} "
        f"stash={snap['stash_count']} dirty_files={len(files)} -> {snap_path}"
    )
    return 0


def cmd_check(repo: Path, as_json: bool) -> int:
    snap_path = repo / SNAPSHOT_REL
    if not snap_path.exists():
        msg = (f"no snapshot: run `lane_guard.py snapshot` before dispatch "
               f"(expected {snap_path})")
        if as_json:
            print(json.dumps({"verdict": "NO_SNAPSHOT", "message": msg}))
        else:
            print(f"NO SNAPSHOT: {msg}")
        return 1

    snap = json.loads(snap_path.read_text())
    cur_entries = _git_status(repo)
    cur_files = {path: {"status": code, "hash": _file_hash(repo, path)}
                 for code, path in cur_entries}
    cur_head = _head_sha(repo)
    cur_stash = _stash_count(repo)

    failures: list[str] = []
    infos: list[str] = []

    if cur_stash != snap["stash_count"]:
        failures.append(
            f"stash count changed: {snap['stash_count']} -> {cur_stash} "
            f"(a lane ran `git stash`)"
        )

    if cur_head != snap["head"]:
        failures.append(
            f"HEAD moved: {snap['head'][:12]} -> {cur_head[:12]} "
            f"(a lane committed/reset/checked-out a ref)"
        )

    for path, info in snap["files"].items():
        if path not in cur_files:
            failures.append(
                f"reverted: {path} was dirty at snapshot time "
                f"(status={info['status']!r}) and is now clean/matches HEAD "
                f"— a lane discarded uncommitted work"
            )

    for path, info in cur_files.items():
        if path not in snap["files"]:
            infos.append(f"new modification: {path} (status={info['status']!r})")
        elif info["hash"] != snap["files"][path]["hash"]:
            infos.append(f"further edit: {path} (expected lane output)")

    verdict = "FAIL" if failures else "PASS"

    if as_json:
        print(json.dumps({
            "verdict": verdict,
            "failures": failures,
            "info": infos,
            "snapshot_head": snap["head"],
            "current_head": cur_head,
        }, indent=2))
    else:
        print(f"lane_guard check: {verdict}")
        for f in failures:
            print(f"  FAIL: {f}")
        for i in infos:
            print(f"  INFO: {i}")

    return 2 if failures else 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                  formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    p_snap = sub.add_parser("snapshot", help="record current repo state")
    p_snap.add_argument("--repo", default=".")

    p_check = sub.add_parser("check", help="compare current state to snapshot")
    p_check.add_argument("--repo", default=".")
    p_check.add_argument("--json", action="store_true")

    args = ap.parse_args()
    repo = Path(args.repo).resolve()

    if args.cmd == "snapshot":
        return cmd_snapshot(repo)
    return cmd_check(repo, args.json)


if __name__ == "__main__":
    sys.exit(main())
