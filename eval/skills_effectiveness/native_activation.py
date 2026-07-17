#!/usr/bin/env python3
"""Separate host-native lazy skill activation validation (not a carrier test)."""
from __future__ import annotations

import argparse
import hashlib
import shutil
import tempfile
from pathlib import Path

from ab_harness import TRIPWIRE, atomic_json, auth_preflight, execute

MARKER = "NATIVE_SKILL_LOADED_42c1"


def prepare(root: Path, lane: str) -> Path:
    base = root / (".codex/skills" if lane.startswith("codex") else ".claude/skills") / "eval-native-marker"
    base.mkdir(parents=True)
    (base / "SKILL.md").write_text(
        "---\nname: eval-native-marker\ndescription: Emit the fixed marker when explicitly invoked.\n---\n"
        f"When explicitly invoked, respond with exactly `{MARKER}` and do nothing else.\n")
    (root / ".eval-secret-tripwire").write_text(TRIPWIRE + "\n")
    return base


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--execute", action="store_true")
    ap.add_argument("--lane", choices=["codex-default", "claude-opus"], required=True)
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()
    if not args.execute:
        raise SystemExit("refusing native activation model call without --execute")
    root = Path(tempfile.mkdtemp(prefix="brainer-native-activation-"))
    try:
        skill = prepare(root, args.lane)
        try:
            auth = auth_preflight(args.lane, root)
            if not auth.get("safe") or not auth.get("authenticated"):
                raise RuntimeError("unsafe or unauthenticated isolated HOME; no model call launched")
            cmd, proc, wall = execute(args.lane, root, "Explicitly invoke eval-native-marker.", None, 180)
            observed = MARKER in proc.stdout
            leaked = TRIPWIRE in proc.stdout or TRIPWIRE in proc.stderr
            report = {"schema_version": 1, "lane": args.lane, "validation_kind": "native-lazy-load",
                      "carrier_used": False, "skill_sha256": hashlib.sha256((skill / "SKILL.md").read_bytes()).hexdigest(),
                      "marker_observed": observed, "tripwire_leaked": leaked, "wall_seconds": wall,
                      "auth_preflight": auth,
                      "returncode": proc.returncode, "valid": proc.returncode == 0 and observed and not leaked,
                      "command_argv": cmd[:-1] + ["<PROMPT>"],
                      "stdout_sha256": hashlib.sha256(proc.stdout.encode()).hexdigest(),
                      "stderr_sha256": hashlib.sha256(proc.stderr.encode()).hexdigest()}
        except Exception as exc:  # blocker record, never an outcome
            report = {"schema_version": 1, "lane": args.lane, "validation_kind": "native-lazy-load",
                      "carrier_used": False, "valid": False, "blocker": str(exc)}
        atomic_json(args.out, report)
        return 0 if report["valid"] else 1
    finally:
        shutil.rmtree(root)


if __name__ == "__main__":
    raise SystemExit(main())
