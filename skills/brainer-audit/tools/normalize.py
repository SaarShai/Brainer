#!/usr/bin/env python3
"""Normalize Claude/Codex hook payloads into Brainer audit events."""
from __future__ import annotations

import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

_SHARED = Path(__file__).resolve().parents[2] / "_shared"
if str(_SHARED) not in sys.path:
    sys.path.insert(0, str(_SHARED))

from audit_redact import redact, redact_obj  # noqa: E402

SCHEMA_VERSION = 1
HOSTS = {"claude", "codex", "antigravity", "unknown"}
EVENT_MAP = {
    "UserPromptSubmit": "user_prompt",
    "PreToolUse": "tool_call",
    "PostToolUse": "tool_result",
    "Stop": "session_end",
    "SessionEnd": "session_end",
    "SessionStart": "git_snapshot",
    "PermissionRequest": "tool_call",
    "SubagentStart": "tool_call",
    "SubagentStop": "tool_result",
    "PreCompact": "git_snapshot",
    "PostCompact": "git_snapshot",
}
TEXT_KEYS = {"content_summary", "command", "raw_ref"}
CORRECTION_RE = re.compile(
    r"(?i)(?:^\s*(?:no[,.! ]|nope\b|wrong[,. ])|that'?s (?:wrong|incorrect)|i (?:said|asked|told you)|you (?:skipped|assumed|claimed|misunderstood))"
)


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _stringify(value: Any, limit: int = 1200) -> str:
    if value in (None, ""):
        return ""
    if isinstance(value, str):
        return redact(value[:limit])
    try:
        text = json.dumps(value, sort_keys=True, ensure_ascii=False)
    except TypeError:
        text = str(value)
    return redact(text[:limit])


def _first(payload: Dict[str, Any], *keys: str) -> str:
    for key in keys:
        if key in payload and payload[key] not in (None, ""):
            return str(payload[key])
    return ""


def _nested(payload: Dict[str, Any], key: str) -> Any:
    current: Any = payload
    for part in key.split("."):
        if not isinstance(current, dict):
            return None
        current = current.get(part)
    return current


def content_summary(payload: Dict[str, Any], event_name: str) -> str:
    candidates = [
        payload.get("prompt"),
        payload.get("message"),
        payload.get("content"),
        payload.get("input"),
        payload.get("output"),
        payload.get("tool_input"),
        payload.get("tool_output"),
        payload.get("result"),
        _nested(payload, "tool.input"),
        _nested(payload, "tool.output"),
        _nested(payload, "tool_response.content"),
    ]
    for value in candidates:
        text = _stringify(value)
        if text:
            return text
    return _stringify({k: v for k, v in payload.items() if k not in {"transcript_path"}}, limit=800)


def normalize_event(payload: Dict[str, Any], *, host: str = "unknown", event_name: str = "") -> Dict[str, Any]:
    host = host if host in HOSTS else "unknown"
    raw_event = event_name or _first(payload, "hook_event_name", "event", "event_name") or "unknown"
    normalized_event = EVENT_MAP.get(raw_event, raw_event if raw_event in set(EVENT_MAP.values()) else "tool_result")
    command = _first(payload, "command", "tool_command") or _stringify(_nested(payload, "tool.command"))
    tool = _first(payload, "tool", "tool_name", "name") or _stringify(_nested(payload, "tool.name"))
    exit_code = payload.get("exit_code", payload.get("status_code", ""))
    project = _first(payload, "cwd", "project_path") or str(Path.cwd())
    event: Dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "mode": "brainer-audit",
        "session_id": _first(payload, "session_id") or "hook",
        "turn_id": _first(payload, "turn_id") or "",
        "host": host,
        "project_path": project,
        "event": normalized_event,
        "timestamp": _first(payload, "timestamp") or utc_now(),
        "hook_event_name": raw_event,
        "content_summary": content_summary(payload, raw_event),
    }
    if tool:
        event["tool"] = tool
    if command:
        event["command"] = redact(command)
    if exit_code != "":
        event["exit_code"] = exit_code
    if payload.get("transcript_path"):
        event["raw_ref"] = redact(str(payload["transcript_path"]))
    if payload.get("is_error") is not None:
        event["is_error"] = bool(payload.get("is_error"))
    if payload.get("line_count") is not None:
        event["line_count"] = payload.get("line_count")
    if payload.get("output_bytes") is not None:
        event["output_bytes"] = payload.get("output_bytes")
    # Final redaction gate: scrub every string leaf (incl. project_path / tool)
    # so no raw secret reaches disk regardless of which payload field carried it.
    return redact_obj(event)


def normalize_task_retro_event(audit_event: Dict[str, Any]) -> Dict[str, Any]:
    text = audit_event.get("content_summary") or audit_event.get("command") or audit_event.get("hook_event_name") or ""
    kind = "correction" if CORRECTION_RE.search(str(text)) else "evidence"
    return redact_obj({
        "schema_version": 1,
        "mode": "task-retrospective",
        "timestamp": audit_event.get("timestamp") or utc_now(),
        "type": kind,
        "text": text,
        "evidence_ref": f"{audit_event.get('host', 'unknown')}:{audit_event.get('hook_event_name', audit_event.get('event', 'event'))}",
    })
