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

Current Codex Desktop builds may instead wrap tool orchestration as:

    {"type":"response_item","payload":{"type":"custom_tool_call","name":"exec",
        "input":"const r = await tools.exec_command({cmd:...})", "call_id":...}}
    {"type":"response_item","payload":{"type":"custom_tool_call_output",...}}

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
_PROCESS_EXIT_RE = re.compile(
    r"(?:^|\n)\s*(?:(?:Process|Script) exited with code|Command failed with exit code)\s+(-?\d+)\b",
    re.IGNORECASE,
)
_COMMAND_FAILURE_RE = re.compile(
    r"(?:^|\n)\s*(?:Command failed|Process failed)(?:\s*[:.]|\s*$)",
    re.IGNORECASE,
)
_FAILURE_STATUSES = {"failed", "failure", "error", "errored", "cancelled", "canceled",
                     "timed_out", "timeout"}
_SUCCESS_STATUSES = {"success", "succeeded", "completed", "complete", "ok", "passed", "pass"}


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


def _codex_result_status(value, depth: int = 0) -> bool | None:
    """Return True for explicit/known failure, False for explicit success, else None."""
    if depth > 8:
        return None
    statuses: list[bool] = []
    if isinstance(value, dict):
        for key, nested in value.items():
            normalized = str(key).lower().replace("_", "").replace("-", "")
            if normalized in {"iserror", "success", "ok"} and isinstance(nested, bool):
                statuses.append(nested if normalized == "iserror" else not nested)
            elif normalized in {"exitcode", "returncode"}:
                if isinstance(nested, int) and not isinstance(nested, bool):
                    statuses.append(nested != 0)
                elif isinstance(nested, str) and re.fullmatch(r"-?\d+", nested.strip()):
                    statuses.append(int(nested) != 0)
            elif normalized in {"status", "state"} and isinstance(nested, str):
                status = nested.strip().lower().replace("-", "_").replace(" ", "_")
                if status in _FAILURE_STATUSES:
                    statuses.append(True)
                elif status in _SUCCESS_STATUSES:
                    statuses.append(False)
            nested_status = _codex_result_status(nested, depth + 1)
            if nested_status is not None:
                statuses.append(nested_status)
    elif isinstance(value, list):
        for nested in value:
            nested_status = _codex_result_status(nested, depth + 1)
            if nested_status is not None:
                statuses.append(nested_status)
    elif isinstance(value, str):
        text = value.strip()
        if text.startswith(("{", "[")):
            try:
                nested = json.loads(text)
            except (ValueError, TypeError):
                nested = None
            if isinstance(nested, (dict, list)):
                nested_status = _codex_result_status(nested, depth + 1)
                if nested_status is not None:
                    statuses.append(nested_status)
        match = _PROCESS_EXIT_RE.search(value)
        if match:
            statuses.append(int(match.group(1)) != 0)
        elif _COMMAND_FAILURE_RE.search(value):
            statuses.append(True)
    if True in statuses:
        return True
    if False in statuses:
        return False
    return None


_CUSTOM_EXEC_CALL_RE = re.compile(r"\btools\.exec_command\s*\(")
_CUSTOM_EXEC_CMD_RE = re.compile(r"\bcmd\s*:\s*")
_CUSTOM_APPLY_PATCH_CALL_RE = re.compile(r"\btools\.apply_patch\s*\(")
_JS_IDENTIFIER_RE = re.compile(r"[A-Za-z_$][A-Za-z0-9_$]*")
_APPLY_PATCH_FILE_RE = re.compile(
    r"^\*\*\* (?:Add|Update|Delete) File:([^\r\n]*)\r?$", re.MULTILINE
)


def _read_js_string(source: str, start: int) -> tuple[str, int] | None:
    """Decode one quoted JS string/template literal without evaluating code.

    The Codex custom `exec` record stores the functions.exec JavaScript source,
    not the nested exec_command arguments. We only accept a literal `cmd`
    property on a direct `tools.exec_command(...)` call; dynamic expressions
    stay opaque and therefore cannot become verification evidence by guesswork.
    """
    if start >= len(source) or source[start] not in {'"', "'", "`"}:
        return None
    quote = source[start]
    out: list[str] = []
    i = start + 1
    escapes = {"n": "\n", "r": "\r", "t": "\t", "b": "\b", "f": "\f",
               "v": "\v", "0": "\0"}
    while i < len(source):
        ch = source[i]
        if ch == quote:
            return "".join(out), i + 1
        if ch == "\\" and i + 1 < len(source):
            nxt = source[i + 1]
            out.append(escapes.get(nxt, nxt))
            i += 2
            continue
        out.append(ch)
        i += 1
    return None


def _custom_exec_commands(source: str) -> list[str]:
    """Extract literal `cmd` values from direct nested exec_command calls."""
    calls = list(_CUSTOM_EXEC_CALL_RE.finditer(source or ""))
    commands: list[str] = []
    for index, call in enumerate(calls):
        stop = calls[index + 1].start() if index + 1 < len(calls) else len(source)
        prop = _CUSTOM_EXEC_CMD_RE.search(source, call.end(), stop)
        if not prop:
            continue
        parsed = _read_js_string(source, prop.end())
        if parsed is not None:
            commands.append(parsed[0])
    return commands


def _custom_apply_patch_paths(source: str) -> list[str]:
    """Extract explicit mutation headers from statically visible apply_patch text."""
    paths: list[str] = []
    for call in _CUSTOM_APPLY_PATCH_CALL_RE.finditer(source or ""):
        start = call.end()
        while start < len(source) and source[start].isspace():
            start += 1
        parsed = _read_js_string(source, start)
        if parsed is None:
            identifier = _JS_IDENTIFIER_RE.match(source, start)
            if not identifier:
                continue
            assignment_re = re.compile(
                rf"\b(?:const|let|var)\s+{re.escape(identifier.group(0))}\s*=\s*"
            )
            assignments = list(assignment_re.finditer(source, 0, call.start()))
            if not assignments:
                continue
            parsed = _read_js_string(source, assignments[-1].end())
        if parsed is not None:
            paths.extend(path for match in _APPLY_PATCH_FILE_RE.finditer(parsed[0])
                         if (path := match.group(1).strip()))
    return paths


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
            tool_use = {"type": "tool_use", "name": name, "input": args}
            if p.get("call_id"):
                tool_use["id"] = p["call_id"]
            out.append({"type": "assistant", "timestamp": ts,
                        "message": {"content": [tool_use]}})
        elif ptype == "function_call_output":
            result_status = _codex_result_status(p)
            out.append({"type": "user", "timestamp": ts, "message": {"content": [{
                "type": "tool_result",
                "tool_use_id": p.get("call_id", ""),
                "is_error": result_status is True,
                "content": p.get("output", ""),
            }]}})
        elif ptype == "custom_tool_call":
            name = str(p.get("name") or "")
            raw_input = p.get("input")
            if name == "exec" and isinstance(raw_input, str):
                commands = _custom_exec_commands(raw_input)
                # functions.exec is the current host's shell-orchestration
                # boundary. Keep the raw source for audit, but expose only
                # directly awaited literal exec_command `cmd` values to the
                # command-aware detectors. Statically visible apply_patch
                # targets are carried separately for path-touch detection.
                args = {"command": "\n;\n".join(commands),
                        "_raw": raw_input}
                patch_paths = _custom_apply_patch_paths(raw_input)
                if patch_paths:
                    args["_apply_patch_paths"] = patch_paths
                name = "Bash"
            elif isinstance(raw_input, dict):
                args = raw_input
            else:
                args = {"_raw": raw_input}
            tool_use = {"type": "tool_use", "name": name, "input": args}
            if p.get("call_id"):
                tool_use["id"] = p["call_id"]
            out.append({"type": "assistant", "timestamp": ts,
                        "message": {"content": [tool_use]}})
        elif ptype == "custom_tool_call_output":
            result_status = _codex_result_status(p)
            out.append({"type": "user", "timestamp": ts, "message": {"content": [{
                "type": "tool_result",
                "tool_use_id": p.get("call_id", ""),
                "is_error": result_status is True,
                "content": p.get("output", p.get("content", "")),
            }]}})
        # reasoning / event_msg / meta: not part of the tool_use / message
        # stream the detectors count — drop.
    return out


def normalize(events: list[dict]) -> list[dict]:
    """Return events in Claude shape. Codex transcripts are converted; Claude
    transcripts (and anything already in Claude shape) pass through untouched."""
    if is_codex(events):
        return _norm_codex(events)
    return events
