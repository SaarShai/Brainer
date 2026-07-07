#!/usr/bin/env python3
"""Regression guard for the "lanes run prohibited git" failure class
(2026-07-06: `git checkout -- <19 paths>` wiped 5 concurrent lanes'
uncommitted work — 4 confirmed violations in one day).

Hooks do NOT fire inside subagents, so the guard has to live on the LEADER
side: `lane_guard.py snapshot` before dispatch, `lane_guard.py check` after
each lane returns. This test drives the real CLI end-to-end against
throwaway temp git repos only — it NEVER touches this (or any real) repo's
git state. SKIPs (does not FAIL) when git is absent from PATH.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent / "lane_guard.py"

FAILS: list[str] = []


def check(name, cond):
    if cond:
        print(f"  [PASS] {name}")
    else:
        FAILS.append(name)
        print(f"  [FAIL] {name}")


def git(cwd: Path, *args: str):
    r = subprocess.run(["git", *args], cwd=cwd, text=True, capture_output=True)
    assert r.returncode == 0, (args, r.stdout, r.stderr)
    return r


def run_guard(repo: Path, *args: str):
    r = subprocess.run(
        [sys.executable, str(SCRIPT), *args, "--repo", str(repo)],
        text=True, capture_output=True,
    )
    return r


def new_repo(tmp: Path, name: str) -> Path:
    repo = tmp / name
    repo.mkdir(parents=True)
    (repo / "tracked.txt").write_text("line1\n")
    git(repo, "init", "-q")
    git(repo, "config", "user.email", "t@t")
    git(repo, "config", "user.name", "t")
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "v1")
    return repo


def test_no_snapshot(tmp: Path):
    repo = new_repo(tmp, "no-snapshot")
    r = run_guard(repo, "check")
    check("check exits 1 with 'no snapshot' when snapshot file is missing",
          r.returncode == 1 and "no snapshot" in r.stdout.lower())


def test_positive_new_edit_passes(tmp: Path):
    repo = new_repo(tmp, "positive")
    r_snap = run_guard(repo, "snapshot")
    check("snapshot exits 0", r_snap.returncode == 0)

    (repo / "tracked.txt").write_text("line1\nline2\n")
    (repo / "new_from_lane.txt").write_text("created by lane\n")

    r = run_guard(repo, "check", "--json")
    check("POSITIVE: new edits after snapshot -> exit 0", r.returncode == 0)
    payload = json.loads(r.stdout)
    check("POSITIVE: verdict is PASS", payload["verdict"] == "PASS")
    check("POSITIVE: new edits surface as INFO, not FAIL",
          not payload["failures"]
          and any("new_from_lane.txt" in i or "tracked.txt" in i
                  for i in payload["info"]))


def test_negative_stash_created(tmp: Path):
    repo = new_repo(tmp, "neg-stash")
    (repo / "tracked.txt").write_text("uncommitted before snapshot\n")
    run_guard(repo, "snapshot")

    (repo / "tracked.txt").write_text("more change\n")
    git(repo, "stash", "-q")  # throwaway temp repo only — never the real tree

    r = run_guard(repo, "check", "--json")
    check("NEGATIVE (stash): check FAILs after a lane runs `git stash`",
          r.returncode == 2)
    payload = json.loads(r.stdout)
    check("NEGATIVE (stash): verdict FAIL and reason names stash",
          payload["verdict"] == "FAIL"
          and any("stash" in f for f in payload["failures"]))


def test_negative_head_moved(tmp: Path):
    repo = new_repo(tmp, "neg-head")
    run_guard(repo, "snapshot")

    (repo / "tracked.txt").write_text("committed by a rogue lane\n")
    git(repo, "add", "-A")  # throwaway temp repo only — never the real tree
    git(repo, "commit", "-qm", "rogue lane commit")

    r = run_guard(repo, "check", "--json")
    check("NEGATIVE (HEAD): check FAILs after HEAD moves", r.returncode == 2)
    payload = json.loads(r.stdout)
    check("NEGATIVE (HEAD): verdict FAIL and reason names HEAD",
          payload["verdict"] == "FAIL"
          and any("HEAD moved" in f for f in payload["failures"]))


def test_negative_file_reverted(tmp: Path):
    repo = new_repo(tmp, "neg-revert")
    (repo / "tracked.txt").write_text("someone's uncommitted work\n")
    run_guard(repo, "snapshot")

    # a lane "cleans" the tree by reverting a sibling's dirty file to HEAD
    git(repo, "checkout", "--", "tracked.txt")  # throwaway repo only

    r = run_guard(repo, "check", "--json")
    check("NEGATIVE (revert): check FAILs when a dirty file is reverted to HEAD",
          r.returncode == 2)
    payload = json.loads(r.stdout)
    check("NEGATIVE (revert): verdict FAIL and reason names the reverted file",
          payload["verdict"] == "FAIL"
          and any("reverted" in f and "tracked.txt" in f
                  for f in payload["failures"]))


def main() -> int:
    if shutil.which("git") is None:
        print("SKIP test_lane_guard (git not on PATH)")
        return 0

    tmp = Path(tempfile.mkdtemp(prefix="lane-guard-test-"))
    try:
        test_no_snapshot(tmp)
        test_positive_new_edit_passes(tmp)
        test_negative_stash_created(tmp)
        test_negative_head_moved(tmp)
        test_negative_file_reverted(tmp)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

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
