#!/usr/bin/env python3
"""Append one normalized brainer-audit event to a JSONL file."""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

REPO_ROOT = Path(__file__).resolve().parents[3]
SCHEMA_VERSION = 1
EVENT_TYPES = {
    "user_prompt",
    "assistant_message",
    "tool_call",
    "tool_result",
    "file_change",
    "git_snapshot",
    "session_end",
}
HOSTS = {"codex", "claude", "antigravity", "unknown"}
TEXT_KEYS = {"content_summary", "command", "raw_ref"}

REDACT_PATTERNS = [
    re.compile(r"(?i)(authorization\s*:\s*bearer\s+)[A-Za-z0-9._~+/=-]+"),
    re.compile(r"(?i)\b(api[_-]?key|token|password|secret)\s*[:=]\s*['\"]?[^'\"\s]+"),
    re.compile(r"\bsk-[A-Za-z0-9]{16,}\b"),
]


class IngestError(Exception):
    pass


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.resolve().relative_to(parent.resolve())
        return True
    except ValueError:
        return False


def ensure_write_allowed(path: Path) -> None:
    if os.environ.get("BRAINER_CHECK_NO_WRITE") == "1" and is_relative_to(path, REPO_ROOT):
        raise IngestError(f"BRAINER_CHECK_NO_WRITE=1: refusing to write audit event inside {REPO_ROOT}")


def redact(text: str) -> str:
    out = text or ""
    out = REDACT_PATTERNS[0].sub(lambda m: m.group(1) + "[REDACTED]", out)
    out = REDACT_PATTERNS[1].sub(lambda m: m.group(1) + "=[REDACTED]", out)
    out = REDACT_PATTERNS[2].sub("[REDACTED]", out)
    return out


def parse_field(values: List[str]) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    for item in values:
        if "=" not in item:
            raise IngestError(f"--field must be key=value, got {item!r}")
        key, raw = item.split("=", 1)
        key = key.strip()
        if not key:
            raise IngestError("--field key cannot be empty")
        try:
            out[key] = json.loads(raw)
        except json.JSONDecodeError:
            out[key] = raw
    return out


def build_event(args: argparse.Namespace) -> Dict[str, Any]:
    if args.event not in EVENT_TYPES:
        raise IngestError(f"unknown event type: {args.event}")
    host = args.host or "unknown"
    if host not in HOSTS:
        raise IngestError(f"unknown host: {host}")
    event: Dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "mode": "brainer-audit",
        "session_id": args.session_id or "offline",
        "turn_id": args.turn_id or "",
        "host": host,
        "project_path": args.project_path or "",
        "event": args.event,
        "timestamp": args.timestamp or utc_now(),
    }
    optional = {
        "tool": args.tool,
        "command": args.command,
        "exit_code": args.exit_code,
        "content_summary": args.content_summary,
        "raw_ref": args.raw_ref,
    }
    optional.update(parse_field(args.field or []))
    for key, value in optional.items():
        if value in (None, ""):
            continue
        if key in TEXT_KEYS:
            event[key] = redact(str(value))
        else:
            event[key] = value
    return event


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(prog="ingest_event.py", description=__doc__)
    ap.add_argument("--events", required=True, help="JSONL path to append to")
    ap.add_argument("--event", required=True, choices=sorted(EVENT_TYPES))
    ap.add_argument("--session-id", default="offline")
    ap.add_argument("--turn-id", default="")
    ap.add_argument("--host", default="unknown", choices=sorted(HOSTS))
    ap.add_argument("--project-path", default="")
    ap.add_argument("--tool", default="")
    ap.add_argument("--command", default="")
    ap.add_argument("--exit-code", default="")
    ap.add_argument("--content-summary", default="")
    ap.add_argument("--raw-ref", default="")
    ap.add_argument("--timestamp", default="")
    ap.add_argument("--field", action="append", default=[], help="Extra JSON field as key=value")
    args = ap.parse_args(argv)

    path = Path(args.events).expanduser().resolve()
    try:
        ensure_write_allowed(path)
        event = build_event(args)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(event, sort_keys=True) + "\n")
        print(json.dumps({"ok": True, "event": event}, indent=2, sort_keys=True))
        return 0
    except IngestError as exc:
        print(f"ingest_event.py: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
