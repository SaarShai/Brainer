#!/usr/bin/env python3
"""activation_trace — tiny append-only JSONL writer for per-skill ACTIVATION
telemetry (trigger-matched / body-loaded / tool-run / outcome), the usage
instrumentation the repo lacked: the skills catalog can name every skill that
EXISTS, but nothing recorded which ones actually FIRED in a live session —
a skill being mentioned in the catalog is not the same as a skill being
invoked. `record_activation` closes that gap the same way orchestration_trace
closes the lane-dispatch gap, and reuses that module's hardened redaction
walk rather than re-implementing it.

PERSISTENCE MUST NOT CRASH A CALLER: record_activation never raises — any
failure (unwritable path, bad permissions, disk full, missing redactor) is
caught and reported as a False return, exactly like orchestration_trace's
record_lane_event. Callers (e.g. compliance-canary's hook.py) MUST treat this
as best-effort telemetry, never a hard dependency of the calling flow.

Default trace path is `.brainer/trace/activations.jsonl` (repo-root
relative) — the SAME `.brainer/trace/` directory orchestration_trace's
lanes.jsonl already lives in, covered by the same blanket `.brainer/`
gitignore entry (verify with `git check-ignore`).

REDACTION REUSE (the load-bearing decision this module makes): rather than
copy-pasting or re-deriving the coerce-and-redact walk that took FOUR
cross-vendor adversarial rounds to harden in orchestration_trace.py, this
module IMPORTS orchestration_trace's internal `_coerce_and_redact` helper
directly and reuses it byte-for-byte. Extracting that logic into a brand-new
shared module (e.g. `_shared/trace_serialize.py`) was considered and
REJECTED: it would require editing orchestration_trace.py's internals (moving
`_stringify`/`_coerce_and_redact` out and changing its import), risking the 26
tests already pinning that exact hardened design down. Importing the existing
function is zero-risk to that contract and is genuine reuse (the same
function OBJECT runs for both lanes.jsonl and activations.jsonl), not a
parallel copy that could drift out of sync with the next redaction fix.

Same fail-CLOSED contract: if orchestration_trace's `_redact_secrets` is
unavailable (import failure), there is no way to guarantee a clean line, so
the event is dropped entirely — nothing is written, `record_activation`
returns False. A partial scrub is still a leak; we refuse to write rather
than write partially-redacted data. Same never-raises contract: the walk
guards every coercion, handles circular references (`[CIRCULAR]`),
pathologically deep structures (`[TOO_DEEP]`), and a `__str__` that itself
raises (`[UNSERIALIZABLE]`) — all inherited for free from the imported walk.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    # Reuse orchestration_trace's hardened coerce-and-redact walk directly —
    # see module docstring for why this is imported rather than re-extracted
    # or copy-pasted. `_coerce_and_redact` internally calls `_redact_secrets`
    # (orchestration_trace's own import of audit_redact.redact_secrets) and
    # is only ever invoked here after confirming that import succeeded
    # (mirrored below via `_redact_secrets`, imported for the same fail-closed
    # guard orchestration_trace itself performs).
    from orchestration_trace import _coerce_and_redact  # type: ignore
    from orchestration_trace import _redact_secrets  # type: ignore
except Exception:                                                # pragma: no cover - defensive
    _coerce_and_redact = None
    _redact_secrets = None

# repo root: skills/_shared/activation_trace.py -> three dirs up
# (_shared -> skills -> repo root). Same convention as orchestration_trace.py.
_REPO_ROOT = Path(os.path.abspath(__file__)).parent.parent.parent
DEFAULT_TRACE_PATH = _REPO_ROOT / ".brainer" / "trace" / "activations.jsonl"

# Fields record_activation accepts verbatim (the whole event, including these,
# is redacted at serialization — see below). Unknown extra keys are still
# written through — this is an append-only sink, not a strict schema validator.
_KNOWN_FIELDS = ("skill", "phase", "source")

# The four activation lifecycle phases this recorder distinguishes. Not
# enforced (an append-only sink accepts any string), but documented here so a
# caller doesn't have to guess the vocabulary: "trigger_matched" (a skill's
# trigger condition matched this turn — e.g. a drift probe fired, or a
# model-invokable description matched context), "body_loaded" (the skill's
# SKILL.md body was actually read/loaded), "tool_run" (one of the skill's
# tools/*.py executed), "outcome" (a terminal result — success/failure — for
# the activation).
KNOWN_PHASES = ("trigger_matched", "body_loaded", "tool_run", "outcome")

# `source` distinguishes real live-session activation telemetry from
# fixture/test data sharing the same activations.jsonl file — same
# provenance field orchestration_trace.py's lanes.jsonl carries (2026-07-06).
DEFAULT_SOURCE = "live"


def record_activation(path: "str | os.PathLike[str] | None", event: dict[str, Any]) -> bool:
    """Append one JSON line describing a single skill activation. Never raises.

    `path` defaults to `.brainer/trace/activations.jsonl` under the repo root
    when None/empty. `event` is the caller-supplied fields: `skill` (name),
    `phase` (one of KNOWN_PHASES — trigger_matched/body_loaded/tool_run/
    outcome), `source` ("live"/"fixture"/any caller value), plus any optional
    freeform fields. `phase` is NOT validated against KNOWN_PHASES — this is
    an append-only sink, not a schema validator; an unrecognized phase is
    still written through (same "unknown extra keys pass through" contract as
    orchestration_trace.py's `_KNOWN_FIELDS`).

    `source` defaults to `DEFAULT_SOURCE` ("live") when the caller omits it,
    filled in here (before the redact walk) via a shallow copy — `event`
    itself is never mutated. A caller that already sets `source` (e.g. a test
    fixture stamping "fixture") has it pass through unchanged.

    Redaction reuses orchestration_trace's hardened `_coerce_and_redact` walk
    verbatim (see module docstring for why this is imported rather than
    re-derived): the walk coerces every leaf to a raw string and redacts it —
    plus every dict KEY — BEFORE serialization, so the regex sees secrets
    with natural boundaries (an embedded `"`/newline or non-ASCII byte can't
    be JSON-escaped past the pattern); then `json.dumps(ensure_ascii=False)`
    on the already-redacted structure is re-scrubbed once more via
    `_redact_secrets` as belt-and-suspenders — identical two-pass design to
    orchestration_trace.record_lane_event.

    Fails CLOSED if the redactor (imported via orchestration_trace) is
    unavailable: there is then no way to guarantee the serialized line is
    clean, so the event is NOT written at all (returns False) — a partial
    scrub would still be a leak for keys/coerced values, so the whole event
    is dropped rather than written partially redacted.

    Returns True on a successful append, False on any failure (including a
    bad path, an unwritable directory, a non-serializable circular structure,
    or the redactor being unavailable) — the caller must treat activation
    persistence as best-effort, never a hard dependency."""
    try:
        if _coerce_and_redact is None or _redact_secrets is None:
            return False
        # Additive `source` default: fill in only when the caller didn't set
        # one, via a shallow copy so the caller's own dict is never mutated —
        # rides through the SAME imported coerce-and-redact walk as any other
        # key (identical pattern to orchestration_trace.record_lane_event).
        if isinstance(event, dict) and "source" not in event:
            event = {**event, "source": DEFAULT_SOURCE}
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
