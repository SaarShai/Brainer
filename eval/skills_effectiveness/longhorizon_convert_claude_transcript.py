#!/usr/bin/env python3
"""Convert a CLAUDE-host long-horizon session directory (manifest.json +
turn-NN.jsonl produced by ``longhorizon_run_session_claude.py`` driving
``claude -p --output-format stream-json --verbose``) into the SAME
normalized raw-transcript event shape that ``longhorizon_gate.build_raw_transcript``
/ ``longhorizon_score_counted.build_raw_transcript`` assemble from CODEX
``--json`` event streams, so the FROZEN extractors
(``longhorizon_extract_blinded.py`` / ``longhorizon_extract_mechanism.py``)
can consume it unmodified.

Observed claude stream-json line types (captured 2026-07-18 via
``claude -p --output-format stream-json --verbose --dangerously-skip-permissions
"say exactly: hello"`` and a follow-up Bash-tool-use prompt; both are one-shot,
free-tier-negligible local calls, not paid API calls beyond ordinary Claude
Code usage):

- ``{"type":"system","subtype":"hook_started"|"hook_response",...,"hook_name":...}``
  -- SessionStart hook chatter.
- ``{"type":"system","subtype":"init","tools":[...],"mcp_servers":[...],...}``
  -- session init banner.
- ``{"type":"assistant","message":{"model":...,"role":"assistant",
  "content":[{"type":"text","text":...}] | [{"type":"tool_use","id":...,
  "name":...,"input":{...}}],"usage":{"input_tokens":...,
  "cache_creation_input_tokens":...,"cache_read_input_tokens":...,
  "output_tokens":...,...}},"session_id":...,"request_id":...}``
  -- one per assistant turn/iteration; ``message.content`` already uses the
  Anthropic block shape (``text`` / ``tool_use``).
- ``{"type":"user","message":{"role":"user","content":[{"tool_use_id":...,
  "type":"tool_result","content":"...","is_error":false}]},
  "tool_use_result":{...}}`` -- the tool-result turn Claude Code emits after
  a tool_use block; role is "user" but it is host-synthesized, not the
  scripted human prompt.
- ``{"type":"rate_limit_event","rate_limit_info":{...}}``
- ``{"type":"system","subtype":"post_turn_summary",...}``
- ``{"type":"result","subtype":"success","is_error":false,"result":"...",
  "usage":{...},"total_cost_usd":...,...}`` -- one per external
  ``claude -p`` invocation (i.e. one per scripted manifest turn).

KEY DESIGN DIFFERENCE FROM THE CODEX CONVERTER
-----------------------------------------------
Codex's ``item.completed`` events (``agent_message`` / ``command_execution`` /
``file_change``) do NOT already match the extractor-facing shape, so
``longhorizon_gate.completed_item_event`` synthesizes a second, parallel
``{"type":"assistant"|"tool", ...}`` event next to each preserved raw source
event. Claude's native ``assistant``/``user`` stream-json events ALREADY use
the exact shape the frozen extractors read via ``_blocks()`` / ``_tool_info()``
(``message.content`` is a list of ``{"type":"text"|"tool_use"|"tool_result",...}``
blocks). No synthetic ``"type":"tool"`` wrapper event is emitted here -- doing
so would duplicate, not clarify, information already present verbatim. Each
claude-native line is therefore appended to the raw transcript exactly once.

EXPLICIT PLACEHOLDER / DELIBERATE DIVERGENCE (do not silently fabricate)
-------------------------------------------------------------------------
Codex's ``turn.completed.usage`` is a session-cumulative counter, and
``longhorizon_gate.normalize_usage`` asserts it is monotonic non-decreasing
across turns (a codex-specific invariant it enforces via a delta subtraction).
Claude's stream has NO equivalent cumulative-session counter: each assistant
message's ``usage`` dict (and each external turn's ``result.usage``) is a
per-request/per-invocation total, not a running session total, so there is
nothing to compute a monotonic delta against. This converter does NOT call
``longhorizon_gate.normalize_usage`` and does NOT fabricate a synthetic
cumulative counter to feed it. Instead it preserves each assistant event's
native (already non-cumulative) Anthropic usage dict verbatim on that event;
``longhorizon_extract_mechanism._usage`` sums these directly (its own
per-record dedup, keyed by request/message id, already assumes non-cumulative
per-record inputs), which is the correct consumption model for genuinely
per-request counters. This is a deliberate, documented divergence -- not a
missing-field placeholder.

Forced-compaction turns (manifest ``forced_compactions`` entries, written by
``longhorizon_run_session_claude.run_session`` when the scripted turn text is
literally ``/compact``) are marked with a
``{"type":"context_pressure_equivalent","host_event_id":"compaction-turn-N",
"turn_index":N,"mechanism":"claude-native-compact"}`` event in place of the
scripted user-prompt event for that turn, mirroring the codex converter's
``context_pressure_equivalent`` marker but tagged with the claude-native
mechanism instead of a synthetic ``filler_byte_size`` (claude's own
``/compact`` has no byte-filler equivalent -- padding context with filler
bytes is a codex-rehearsal-specific technique, not something claude's native
compaction does or needs).
"""
from __future__ import annotations

import json
from pathlib import Path


def read_manifest(session_dir: Path) -> dict:
    return json.loads((session_dir / "manifest.json").read_text(encoding="utf-8"))


def compacted_turns(manifest: dict) -> set[int]:
    return {
        row["turn_index"]
        for row in manifest.get("forced_compactions", [])
        if row.get("mechanism") == "claude-native-compact"
    }


def convert_session_events(session_dir: Path, turns: dict[int, str]) -> list[dict]:
    """Return the ordered normalized raw-transcript events for every scripted
    turn in ``turns`` (turn_index -> scripted prompt text), reading
    ``manifest.json`` + ``turn-NN.jsonl`` from ``session_dir``. Raises
    ValueError on any physically malformed source line (mirrors the codex
    converters' fail-fast behavior)."""
    manifest = read_manifest(session_dir)
    compactions = compacted_turns(manifest)
    events: list[dict] = []
    for turn_number in sorted(turns):
        if turn_number in compactions:
            events.append({
                "type": "context_pressure_equivalent",
                "host_event_id": f"compaction-turn-{turn_number}",
                "turn_index": turn_number,
                "mechanism": "claude-native-compact",
            })
        else:
            events.append({"type": "user", "message": {"role": "user", "content": turns[turn_number]}})
        turn_file = session_dir / f"turn-{turn_number:02d}.jsonl"
        for line_number, line in enumerate(turn_file.read_text(encoding="utf-8").splitlines(), 1):
            if not line.strip():
                continue
            try:
                source = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"non-JSON source line: {turn_file}:{line_number}") from exc
            if not isinstance(source, dict):
                raise ValueError(f"non-object source event: {turn_file}:{line_number}")
            events.append(source)
    return events


def write_raw_transcript(events: list[dict], raw_path: Path) -> Path:
    raw_path.write_text(
        "".join(json.dumps(event, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n" for event in events),
        encoding="utf-8",
    )
    return raw_path


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("session_dir", type=Path)
    parser.add_argument("--scenario", required=True, type=Path, help="scenario markdown with T01 -- `...` scripted turns")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    try:
        from .longhorizon_run_session_claude import parse_scripted_turns
    except ImportError:
        from longhorizon_run_session_claude import parse_scripted_turns

    turns = {index: text for index, text in parse_scripted_turns(args.scenario)}
    events = convert_session_events(args.session_dir, turns)
    write_raw_transcript(events, args.output)
    print(json.dumps({"events": len(events), "output": str(args.output)}))
    return 0


if __name__ == "__main__":
    import sys

    sys.exit(main())
