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

Redaction — COERCE-AND-REDACT WALK, then a final string-pass. This is the
third design; the two it replaces each leaked (2026-07-05 cross-vendor review,
three passes):

  1. A structure-walk that redacted values before coercion leaked 3 ways —
     dict KEYS were never scrubbed; a non-string value (bytes/object) whose
     `str()` yields a secret was only stringified by `json.dumps(default=str)`
     AFTER the scrub ran, so it bypassed redaction; the import-fail fallback
     only blanked string leaves.
  2. A pure final-string-pass (`json.dumps(default=str)` then redact the one
     serialized line) closed those, but JSON serialization MUTATES the secret
     text before the regex sees it, opening new bypasses: a secret containing
     `"` or a newline is escaped (`\"`, `\n`) so the token pattern no longer
     anchors; `ensure_ascii=True` turns a non-ASCII secret byte into a
     ``\\uXXXX`` escape which the pattern misses; a `bytes` value reprs with
     backslash artifacts.

The fix combines both so neither blind spot survives:

  a. Walk the event first. Coerce EVERY leaf to a raw string (bytes decoded,
     objects `str()`-ed) and redact it — and redact dict KEYS too — BEFORE any
     serialization. The regex therefore sees the secret with its natural
     boundaries (a `"` or newline is a clean token terminator, not an inserted
     backslash), catching the escaped-secret and non-ASCII cases pass 2 missed,
     and catching key/coerced-value secrets pass 1 missed.
  b. Serialize the already-redacted structure with `ensure_ascii=False` (no
     ``\\uXXXX`` escaping can re-hide a byte) and run `redact_secrets` over the
     line once more as belt-and-suspenders. Redaction is idempotent, so the
     second pass only ever catches something the walk somehow left.

This is a PERSISTENCE surface, not egress, but the same secret family (keys,
tokens, .env assignments) must never land in a trace file either.

Fails CLOSED: if the redactor cannot be imported there is no way to guarantee
the line is clean, so the event is dropped entirely — nothing is written,
`record_lane_event` returns False. A partial scrub is still a leak; we refuse
to write rather than write partially-redacted data.

Never-raises: the walk guards every coercion (`bytes.decode(errors="replace")`
never raises; `str()` and cycle/depth traversal are wrapped), and the whole
body is inside a try/except returning False. A circular reference is broken by
an id-based `seen` set (emits `[CIRCULAR]`), a pathologically deep structure by
a depth cap (`[TOO_DEEP]`), and a `__str__` that itself raises by the coercion
guard (`[UNSERIALIZABLE]`) — so an odd-shaped field is stored coerced, not
dropped, and nothing takes down the caller."""
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

# Fields record_lane_event accepts verbatim (the whole event, including these,
# is redacted at serialization — see below). Unknown extra keys are still
# written through — this is an append-only sink, not a strict schema validator.
_KNOWN_FIELDS = ("role", "lane", "vendor", "ok", "usage", "latency_ms", "served_model", "task_digest")

# Depth guard for the coerce-and-redact walk: a structure nested deeper than
# this is almost certainly pathological (or an unbroken cycle the id-set below
# would already catch); we stop rather than risk a stack overflow.
_MAX_DEPTH = 200


def _stringify(value: Any) -> str:
    """Coerce any non-container leaf to a raw string for redaction. Never raises.

    `bytes` are DECODED (`errors="replace"`), not `repr`-ed, so a token inside
    them keeps its exact character sequence for the regex (a backslash artifact
    from `repr(b"...")` would dodge the pattern). Any object whose `str()`
    raises falls back to a fixed placeholder rather than propagating."""
    if isinstance(value, bytes):
        return value.decode("utf-8", "replace")
    if isinstance(value, bytearray):
        return bytes(value).decode("utf-8", "replace")
    try:
        return str(value)
    except Exception:
        return "[UNSERIALIZABLE]"


def _coerce_and_redact(obj: Any, seen: set[int], depth: int) -> Any:
    """Walk `obj`, redacting every string leaf AND every dict key BEFORE
    serialization, coercing non-str/non-container leaves to redacted strings.

    Returns a structure of only JSON-native types (str/int/float/bool/None +
    dict/list) with all secret-shaped material already scrubbed, so the later
    `json.dumps` cannot mutate a secret past the regex (the escaped-quote /
    non-ASCII / bytes-repr bypasses that a serialize-then-redact design hits).
    `_redact_secrets` is guaranteed non-None here — the caller checks first."""
    if depth > _MAX_DEPTH:
        return "[TOO_DEEP]"
    if isinstance(obj, str):
        return _redact_secrets(obj)
    # JSON-native scalars carry no regex-catchable secret text; pass through so
    # numbers/bools stay typed in the output.
    if obj is None or isinstance(obj, bool) or isinstance(obj, (int, float)):
        return obj
    if isinstance(obj, (dict, list, tuple)):
        oid = id(obj)
        if oid in seen:
            return "[CIRCULAR]"
        seen.add(oid)
        try:
            if isinstance(obj, dict):
                return {
                    _redact_secrets(_stringify(k)): _coerce_and_redact(v, seen, depth + 1)
                    for k, v in obj.items()
                }
            return [_coerce_and_redact(item, seen, depth + 1) for item in obj]
        finally:
            seen.discard(oid)
    # bytes / arbitrary object → stringify (decoding bytes) then redact.
    return _redact_secrets(_stringify(obj))


def record_lane_event(path: "str | os.PathLike[str] | None", event: dict[str, Any]) -> bool:
    """Append one JSON line describing a single lane dispatch. Never raises.

    `path` defaults to `.brainer/trace/lanes.jsonl` under the repo root when
    None/empty. `event` is the caller-supplied fields (role, lane, vendor, ok,
    usage, latency_ms, served_model, task_digest, ...).

    Redaction runs in TWO passes (see module docstring): first a walk that
    coerces every leaf to a raw string and redacts it — plus every dict KEY —
    BEFORE serialization, so the regex sees secrets with natural boundaries
    (an embedded `"`/newline or non-ASCII byte can't be JSON-escaped past the
    pattern); then `json.dumps(ensure_ascii=False)` on the already-redacted
    structure, re-scrubbed once as belt-and-suspenders.

    Fails CLOSED if `_redact_secrets` is unavailable: there is then no way to
    guarantee the serialized line is clean, so the event is NOT written at all
    (returns False) — a partial scrub (e.g. blanking only string values) would
    still be a leak for keys/coerced values, so the whole event is dropped
    rather than written partially redacted.

    Returns True on a successful append, False on any failure (including a bad
    path, an unwritable directory, a non-serializable circular structure, or
    the redactor being unavailable) — the caller must treat trace persistence
    as best-effort, never a hard dependency."""
    try:
        if _redact_secrets is None:
            return False
        # (a) walk + redact BEFORE serialization so the regex sees raw secrets
        # with natural boundaries; (b) serialize with ensure_ascii=False (no
        # \uXXXX re-hiding) and redact the line once more as belt-and-suspenders.
        scrubbed = _coerce_and_redact(event, set(), 0)
        line = json.dumps(scrubbed, sort_keys=True, ensure_ascii=False, default=str)
        line = _redact_secrets(line)
        target = Path(path) if path else DEFAULT_TRACE_PATH
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("a", encoding="utf-8") as fh:
            fh.write(line + "\n")
        return True
    except Exception:
        return False
