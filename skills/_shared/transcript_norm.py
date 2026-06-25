#!/usr/bin/env python3
"""Cross-host transcript normalizer.

Claude Code and Codex write different transcript schemas. Telemetry scanning and the
compliance-canary detectors were written against Claude's flat shape:

    {"type":"assistant","timestamp":T,"message":{"content":[
        {"type":"tool_use","name":N,"input":{...}}, {"type":"text","text":...}]}}
    {"type":"user","message":{"content":[{"type":"text","text":...}]}}

Codex nests everything under `payload` and uses different record/tool types:

    {"type":"response_item","timestamp":T,"payload":{"type":"message","role":"user",
        "content":[{"type":"input_text","text":...}]}}
    {"type":"response_item","payload":{"type":"function_call","name":N,
        "arguments":"<json-string>","call_id":...}}

Rather than teach every downstream detector both schemas, we normalize Codex records
INTO the Claude shape here. Claude transcripts pass through unchanged. One extra trick:
Codex has no discrete `Skill` tool_use (skills load inline), so a skill use is invisible
to a transcript scan — EXCEPT a slash-triggered skill, which appears as a user message
starting with its token. For those we SYNTHESIZE a Claude-shaped `Skill` tool_use right
after the user turn, so the existing telemetry scanner records it. Model-invokable skills
on Codex remain uncapturable by scanning (no event exists) — those stay manual.
"""
from __future__ import annotations

import json
import re

_CODEX_RECORD_TYPES = {"response_item", "event_msg", "session_meta", "turn_context"}

# Codex shell tools -> Claude's "Bash" so name-based detectors (the nomination
# substantive-action filter, trivial-command checks) work unchanged. Their command
# lives under a different arg key (`cmd`), normalized to `command` below.
_CODEX_SHELL_TOOLS = {"exec_command", "local_shell_call", "shell", "container.exec"}

# Slash token (as typed by the user) -> the skills/<dir> name telemetry tracks.
# Keep in sync with the slash-triggered skills documented in CLAUDE.md.
SLASH_TO_SKILL = {
    "learn": "learn-skill",
    "think": "think",
    "retro": "task-retrospective",
}

# Codex expands ANY skill invocation (slash OR model-invoked) into an injected
# user message: "<skill>\n<name>think</name>\n<path>.../skills/think/SKILL.md</path>...".
# `<name>` is already the skills/<dir> name telemetry tracks — the canonical,
# host-emitted invocation signal (more reliable than parsing the slash, which Codex
# rewrites to a markdown link). This block is scaffolding, not dialogue, so we record
# the invocation but do NOT emit it as a user turn (keeps abort-inference anchored on
# the next REAL user message).
_CODEX_SKILL_BLOCK = re.compile(r"<skill>\s*<name>\s*([^<\s]+)\s*</name>", re.IGNORECASE)


def _skill_tool_use(skill: str, ts: str) -> dict:
    return {"type": "assistant", "timestamp": ts, "message": {"content": [
        {"type": "tool_use", "name": "Skill", "input": {"skill": skill}}]}}


def is_codex(events: list[dict]) -> bool:
    """A transcript is Codex-shaped if any record carries a `payload` and a Codex
    record `type`. Claude records have neither."""
    for e in events:
        if isinstance(e, dict) and "payload" in e and e.get("type") in _CODEX_RECORD_TYPES:
            return True
    return False


def _codex_text(content) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = [b.get("text", "") for b in content
                 if isinstance(b, dict) and b.get("type") in ("input_text", "output_text", "text")]
        return "\n".join(p for p in parts if p)
    return ""


def _slash_skill(text: str) -> str | None:
    """If a user message begins with a known slash token, return the tracked skill name."""
    s = (text or "").lstrip()
    if not s.startswith("/"):
        return None
    token = s[1:].split(None, 1)[0].strip().lower() if len(s) > 1 else ""
    return SLASH_TO_SKILL.get(token)


def _norm_codex(events: list[dict]) -> list[dict]:
    out: list[dict] = []
    for e in events:
        if not isinstance(e, dict):
            continue
        ts = e.get("timestamp", "")
        p = e.get("payload") or {}
        ptype = p.get("type")
        if ptype == "message":
            role = p.get("role")
            text = _codex_text(p.get("content"))
            if role == "user":
                m = _CODEX_SKILL_BLOCK.search(text)
                if m:
                    # Codex skill-expansion block: record the invocation, skip the
                    # injected scaffolding as a dialogue turn.
                    out.append(_skill_tool_use(m.group(1).strip(), ts))
                    continue
                out.append({"type": "user", "timestamp": ts,
                            "message": {"content": [{"type": "text", "text": text}]}})
                skill = _slash_skill(text)  # fallback if a host passes a raw slash
                if skill:
                    out.append(_skill_tool_use(skill, ts))
            elif role == "assistant":
                out.append({"type": "assistant", "timestamp": ts,
                            "message": {"content": [{"type": "text", "text": text}]}})
            # developer/system roles: dropped (not part of the user/assistant dialogue)
        elif ptype == "function_call":
            args = p.get("arguments")
            if isinstance(args, str):
                try:
                    args = json.loads(args)
                except (ValueError, TypeError):
                    args = {"_raw": args}
            if not isinstance(args, dict):
                args = {"_raw": args}
            name = p.get("name", "")
            if name in _CODEX_SHELL_TOOLS:
                # map to Claude's Bash shape so command-aware detectors read it
                cmd = args.get("command") or args.get("cmd") or ""
                args = {**args, "command": cmd}
                name = "Bash"
            out.append({"type": "assistant", "timestamp": ts, "message": {"content": [
                {"type": "tool_use", "name": name, "input": args}]}})
        # function_call_output / reasoning / event_msg / meta: not part of the
        # tool_use / message stream the detectors count — drop.
    return out


def normalize(events: list[dict]) -> list[dict]:
    """Return events in Claude shape. Codex transcripts are converted; Claude
    transcripts (and anything already in Claude shape) pass through untouched."""
    if is_codex(events):
        return _norm_codex(events)
    return events
