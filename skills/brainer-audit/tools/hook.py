#!/usr/bin/env python3
"""Claude/Codex command hook adapter for brainer-audit.

Writes only when `.brainer/brainer-audit/current.json` or
`.brainer/task-retrospective/current.json` exists.

Supported hook events: UserPromptSubmit, PreToolUse, PostToolUse, Stop,
PreCompact, PostCompact.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, Optional

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))
_SHARED = Path(__file__).resolve().parents[2] / "_shared"
if str(_SHARED) not in sys.path:
    sys.path.insert(0, str(_SHARED))

from audit_paths import PathConfinementError, safe_resolve_under  # noqa: E402
from normalize import normalize_event, normalize_task_retro_event  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[3]


class HookError(Exception):
    pass


def is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.resolve().relative_to(parent.resolve())
        return True
    except ValueError:
        return False


def write_allowed(root: Path) -> bool:
    return not (os.environ.get("BRAINER_CHECK_NO_WRITE") == "1" and is_relative_to(root, REPO_ROOT))


def load_stdin() -> Dict[str, Any]:
    raw = sys.stdin.read()
    if not raw.strip():
        return {}
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise HookError(f"malformed hook payload: {exc}") from exc
    if not isinstance(data, dict):
        raise HookError("hook payload must be a JSON object")
    return data


def load_json(path: Path) -> Optional[Dict[str, Any]]:
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


def append_jsonl(path: Path, event: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(event, sort_keys=True) + "\n")


def maybe_write_brainer_audit(root: Path, event: Dict[str, Any]) -> bool:
    base = root / ".brainer" / "brainer-audit"
    state = load_json(base / "current.json")
    if not state:
        return False
    raw = state.get("events_path") or ""
    if not raw:
        return False
    try:
        path = safe_resolve_under(base, raw)
    except PathConfinementError:
        return False
    append_jsonl(path, event)
    return True


def maybe_write_task_retro(root: Path, event: Dict[str, Any]) -> bool:
    base = root / ".brainer" / "task-retrospective"
    state = load_json(base / "current.json")
    if not state:
        return False
    raw = state.get("events_path") or ""
    if not raw:
        return False
    try:
        path = safe_resolve_under(base, raw)
    except PathConfinementError:
        return False
    append_jsonl(path, normalize_task_retro_event(event))
    return True


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="hook.py", description=__doc__)
    ap.add_argument("--host", choices=["claude", "codex", "unknown"], default="unknown")
    ap.add_argument("--event", default="")
    ap.add_argument("--root", default=os.getcwd())
    ap.add_argument("--debug", action="store_true")
    args = ap.parse_args(argv)
    try:
        root = Path(args.root).expanduser().resolve()
        payload = load_stdin()
        event = normalize_event(payload, host=args.host, event_name=args.event)
        event["project_path"] = event.get("project_path") or str(root)
        if not write_allowed(root):
            if args.debug:
                print(json.dumps({"ok": True, "written": 0, "reason": "no_write"}, sort_keys=True), file=sys.stderr)
            return 0
        written = 0
        written += 1 if maybe_write_brainer_audit(root, event) else 0
        written += 1 if maybe_write_task_retro(root, event) else 0
        if args.debug:
            print(json.dumps({"ok": True, "written": written, "event": event}, sort_keys=True), file=sys.stderr)
        return 0
    except HookError as exc:
        if args.debug:
            print(json.dumps({"ok": False, "error": str(exc)}, sort_keys=True), file=sys.stderr)
        return 0


if __name__ == "__main__":
    sys.exit(main())
