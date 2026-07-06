#!/usr/bin/env python3
"""orchestration_trace — tiny append-only JSONL writer for per-lane dispatch
telemetry (usage/latency/served-model), consumed by model_roster.run_dispatch.

PERSISTENCE MUST NOT CRASH A CALLER: record_lane_event never raises — any
failure (unwritable path, bad permissions, disk full) is caught and reported
as a False return, exactly like the CLI dispatch paths in model_roster.py that
drop a failing member rather than take down the whole panel.

Default trace path is `.brainer/trace/lanes.jsonl` (repo-root relative), the
same `.brainer/<tool>/...` convention output-filter's index.jsonl and
context-keeper's session archive already use — already covered by the repo's
`.brainer/` gitignore entry (verify with `git check-ignore`).

Redaction: any free-text field that could carry repo/task content (here,
`task_digest`) MUST be scrubbed through the shared `redact_secrets` before it
touches disk — this is a PERSISTENCE surface, not egress, but the same secret
family (keys, tokens, .env assignments) must never land in a trace file either.
Fails CLOSED on that one field only (per the brief): if the redactor cannot be
imported, `task_digest` is stored as None rather than raw text; the event
itself still gets appended (persistence fails open; the redaction it depends
on does not silently pass raw secrets through instead)."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    from audit_redact import redact_secrets as _redact_secrets  # type: ignore
except Exception:                                                # pragma: no cover - defensive
    _redact_secrets = None

# repo root: skills/_shared/orchestration_trace.py -> three dirs up
# (_shared -> skills -> repo root).
_REPO_ROOT = Path(os.path.abspath(__file__)).parent.parent.parent
DEFAULT_TRACE_PATH = _REPO_ROOT / ".brainer" / "trace" / "lanes.jsonl"

# Fields record_lane_event accepts verbatim (besides task_digest, which is
# redacted before storage). Unknown extra keys are still written through —
# this is an append-only sink, not a strict schema validator.
_KNOWN_FIELDS = ("role", "lane", "vendor", "ok", "usage", "latency_ms", "served_model", "task_digest")


def record_lane_event(path: "str | os.PathLike[str] | None", event: dict[str, Any]) -> bool:
    """Append one JSON line describing a single lane dispatch. Never raises.

    `path` defaults to `.brainer/trace/lanes.jsonl` under the repo root when
    None/empty. `event` is the caller-supplied fields (role, lane, vendor, ok,
    usage, latency_ms, served_model, task_digest, ...); `task_digest` is passed
    through the shared secret redactor before it is written — if the redactor
    is unavailable, `task_digest` is stored as None instead of raw text
    (fail-closed on that field only, per the persistence-vs-egress split
    documented in model_roster.py's `_redact` fallback).

    Returns True on a successful append, False on any failure (including a bad
    path, an unwritable directory, or a non-serializable event) — the caller
    must treat trace persistence as best-effort, never a hard dependency."""
    try:
        record = dict(event)
        if "task_digest" in record:
            digest = record["task_digest"]
            if digest is None or _redact_secrets is None:
                record["task_digest"] = None
            else:
                record["task_digest"] = _redact_secrets(digest)
        target = Path(path) if path else DEFAULT_TRACE_PATH
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, sort_keys=True) + "\n")
        return True
    except Exception:
        return False
