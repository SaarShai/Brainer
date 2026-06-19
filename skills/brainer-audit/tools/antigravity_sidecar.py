#!/usr/bin/env python3
"""Best-effort Antigravity sidecar snapshot collector.

This is a lower-fidelity collector. It does not claim native Antigravity hooks;
it snapshots git state and optional artifact/log folders into normalized
Brainer-audit events.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))
_SHARED = Path(__file__).resolve().parents[2] / "_shared"
if str(_SHARED) not in sys.path:
    sys.path.insert(0, str(_SHARED))

from audit_paths import PathConfinementError, safe_resolve_under  # noqa: E402
from watch_artifacts import build_sidecar_events, append_jsonl, discover_artifact_dirs  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[3]


class SidecarError(Exception):
    pass


def is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.resolve().relative_to(parent.resolve())
        return True
    except ValueError:
        return False


def ensure_write_allowed(path: Path) -> None:
    if os.environ.get("BRAINER_CHECK_NO_WRITE") == "1" and is_relative_to(path, REPO_ROOT):
        raise SidecarError(f"BRAINER_CHECK_NO_WRITE=1: refusing to write sidecar events inside {REPO_ROOT}")


def current_events_path(root: Path) -> Path:
    base = root / ".brainer" / "brainer-audit"
    marker = base / "current.json"
    if not marker.exists():
        raise SidecarError("no --events path and no active .brainer/brainer-audit/current.json marker")
    try:
        data = json.loads(marker.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise SidecarError(f"malformed {marker}: {exc}") from exc
    path = data.get("events_path")
    if not path:
        raise SidecarError(f"{marker} has no events_path")
    # A tampered marker must not redirect the write outside the audit store.
    try:
        return safe_resolve_under(base, path)
    except PathConfinementError as exc:
        raise SidecarError(f"marker events_path escapes audit store: {exc}") from exc


def command_status(args: argparse.Namespace) -> int:
    root = Path(args.root).expanduser().resolve()
    dirs = discover_artifact_dirs(root, args.artifact_dir or [])
    marker = root / ".brainer" / "brainer-audit" / "current.json"
    payload: Dict[str, Any] = {
        "mode": "brainer-audit",
        "host": "antigravity",
        "collector": "antigravity_sidecar",
        "native_hooks": "unverified",
        "active_marker": marker.exists(),
        "artifact_dirs": [str(path) for path in dirs],
        "evidence_fidelity": "lower-sidecar",
    }
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


def command_snapshot(args: argparse.Namespace) -> int:
    root = Path(args.root).expanduser().resolve()
    if args.events:
        # Operator-supplied target: confine it under the project root.
        try:
            events_path = safe_resolve_under(root, args.events)
        except PathConfinementError as exc:
            raise SidecarError(f"--events path escapes project root: {exc}") from exc
    else:
        events_path = current_events_path(root)
    ensure_write_allowed(events_path)
    events = build_sidecar_events(
        root,
        args.session_id or "antigravity-sidecar",
        args.artifact_dir or [],
        max_files=args.max_files,
        include_content=args.include_content,
    )
    written = append_jsonl(events_path, events)
    out = {
        "ok": True,
        "collector": "antigravity_sidecar",
        "host": "antigravity",
        "native_hooks": "unverified",
        "evidence_fidelity": "lower-sidecar",
        "events_path": str(events_path),
        "events_written": written,
    }
    print(json.dumps(out, indent=2, sort_keys=True))
    return 0


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="antigravity_sidecar.py", description=__doc__)
    ap.add_argument("--root", default=os.getcwd())
    ap.add_argument("--artifact-dir", action="append", default=[])
    sub = ap.add_subparsers(dest="cmd", required=True)

    status = sub.add_parser("status", help="Show sidecar discovery state")
    status.set_defaults(func=command_status)

    snap = sub.add_parser("snapshot", help="Append one lower-fidelity sidecar snapshot")
    snap.add_argument("--events", default="", help="JSONL path; defaults to active brainer-audit marker")
    snap.add_argument("--session-id", default="antigravity-sidecar")
    snap.add_argument("--max-files", type=int, default=50)
    snap.add_argument("--include-content", action="store_true", help="Include short redacted previews for text artifacts")
    snap.set_defaults(func=command_snapshot)
    return ap


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return int(args.func(args))
    except (SidecarError, OSError, ValueError) as exc:
        print(f"antigravity_sidecar.py: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
