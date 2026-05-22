from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from tokens import estimate_tokens, trim_to_tokens


PATH_RE = re.compile(r"(?P<path>(?:/|\.{1,2}/|[\w.-]+/)[\w./ @+-]+\.[A-Za-z0-9_+-]+)")
CMD_RE = re.compile(r"(?:cmd|command|bash|shell)[\"': ]+([^\\n]{3,240})", re.IGNORECASE)
ERR_RE = re.compile(r"((?:error|exception|traceback|failed|fatal)[^\n]{0,240})", re.IGNORECASE)
MODEL_CONTEXT_PATTERNS = (
    (re.compile(r"(turboquant|long[-_ ]context|1m|million)", re.IGNORECASE), 1_000_000),
    (re.compile(r"(gemini|flash|pro)", re.IGNORECASE), 1_000_000),
    (re.compile(r"(claude|opus|sonnet|haiku|anthropic)", re.IGNORECASE), 200_000),
    (re.compile(r"(gpt|openai|codex)", re.IGNORECASE), 128_000),
    (re.compile(r"(qwen|gemma|phi|llama|local|ollama)", re.IGNORECASE), 128_000),
)

HOST_CONTEXT_CONTROLS: dict[str, dict[str, Any]] = {
    "claude": {
        "strategy": "native-clear-or-compact",
        "compact": "/compact",
        "clear": "/clear",
        "fresh": "/clear, then paste only the handoff packet plus the startup doc",
        "status": "/context or /cost when available",
        "notes": [
            "Interactive Claude Code supports /clear and /compact.",
            "If a Claude SlashCommand/SDK tool is available, invoke /clear or /compact there; otherwise ask the user to run it.",
            "Use /clear for the cleanest fresh context, or /compact with a handoff-focused instruction when same-chat continuity matters.",
        ],
    },
    "codex": {
        "strategy": "fresh-successor-workaround-current-clear-unsolved",
        "compact": "host /compact if the user can run it; App Server current-thread compact failed in tested Desktop environment",
        "clear": "/clear",
        "fresh": "host /new or /clear when available; programmatic workaround: te context codex-fresh-thread",
        "status": "/status",
        "notes": [
            "Codex CLI supports /compact, /clear, and /new.",
            "These are host UI commands; an assistant response that says /new usually does not execute them.",
            "App Server current-thread compact was tested and failed with tools.defer_loading requiring tools.tool_search.",
            "./te context codex-compact-thread is experimental; do not present it as a reliable current-thread clear path.",
            "Codex App Server can create a fresh successor thread with thread/start + turn/start when given an accessible model.",
            "Fresh successor is not in-place clearing; it bypasses the old transcript by starting a new thread with only the handoff.",
            "/clear starts a fresh chat; Ctrl+L only clears the terminal view.",
        ],
    },
    "gemini": {
        "strategy": "native-compress-or-new-session",
        "compact": "/compress",
        "clear": "/clear",
        "fresh": "Use /compress for summary, or start a new chat/session with only the handoff packet plus the startup doc",
        "status": "/stats when available",
        "notes": [
            "Gemini CLI documents /compress as replacing chat context with a summary.",
            "/clear behavior varies by version/docs; verify whether it clears context or only screen.",
            "Treat /compress and new-session actions as user/host controls unless a real tool exposes them.",
        ],
    },
    "cursor": {
        "strategy": "new-chat-with-handoff",
        "compact": "host-specific compact/new chat command",
        "clear": "new chat/session",
        "fresh": "start a new chat with only the handoff packet plus the startup doc",
        "status": "host-specific context/status view",
        "notes": [
            "Cursor behavior depends on product version and enabled agent mode.",
            "Use MCP/hooks such as context-mode for output quarantine when available.",
        ],
    },
    "generic": {
        "strategy": "manual-fresh-session",
        "compact": "host-specific compact/compress command if available",
        "clear": "host-specific clear/new-chat command if available",
        "fresh": "start a new session with only the handoff packet plus the startup doc",
        "status": "host-specific token/context meter if available",
        "notes": [
            "The framework can prepare the packet; the host must perform the actual context reset.",
            "If no native clear exists, stop old-context work and start a new session manually.",
        ],
    },
}


def model_context_tokens(model: str | None) -> int | None:
    if not model or model == "auto":
        return None
    for pattern, tokens in MODEL_CONTEXT_PATTERNS:
        if pattern.search(model):
            return tokens
    return None


def resolve_max_tokens(value: int | str | None, model: str | None = None) -> int:
    if isinstance(value, int):
        return value
    env = os.environ.get("TOKEN_ECONOMY_CONTEXT_MAX")
    if env and env.isdigit():
        return int(env)
    if isinstance(value, str) and value.isdigit():
        return int(value)
    model_tokens = model_context_tokens(model)
    if model_tokens:
        return model_tokens
    return 128_000


def host_context_controls(agent: str = "auto") -> dict[str, Any]:
    key = (agent or "auto").lower()
    if key == "auto":
        key = "generic"
    controls = HOST_CONTEXT_CONTROLS.get(key, HOST_CONTEXT_CONTROLS["generic"])
    return {
        "agent": key,
        **controls,
        "universal_protocol": "summarize current work, document durable memory with a lightweight wiki-documenter, write a lean handoff, clear or bypass old context, then use the selected host strategy to continue with only the startup doc plus the handoff.",
        "summ_rule": "After writing the handoff, choose the platform strategy from this profile; do not assume all hosts can clear context the same way.",
        "completion_test": "Refresh is complete only after the host-reported active context drops or a fresh conversation starts.",
    }


def current_codex_transcript(thread_id: str | None = None, sessions_root: Path | None = None) -> Path | None:
    target = thread_id or os.environ.get("CODEX_THREAD_ID")
    if not target:
        return None
    root = sessions_root or (Path.home() / ".codex" / "sessions")
    if not root.exists():
        return None
    matches = sorted(root.rglob(f"*{target}*.jsonl"), key=lambda path: path.stat().st_mtime, reverse=True)
    return matches[0] if matches else None


def _relative_or_abs(path: Path, root: Path) -> str:
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)


def startup_doc(repo_root: Path) -> Path:
    """Return the startup contract path for root or embedded installs."""
    root_doc = repo_root / "start.md"
    if root_doc.exists():
        return root_doc
    embedded_doc = repo_root / "framework" / "start.md"
    if embedded_doc.exists():
        return embedded_doc
    return root_doc


def startup_doc_label(repo_root: Path) -> str:
    return _relative_or_abs(startup_doc(repo_root), repo_root)


def l1_index_path(repo_root: Path) -> Path:
    root_l1 = repo_root / "L1_index.md"
    if root_l1.exists():
        return root_l1
    embedded_l1 = repo_root / "framework" / "L1_index.md"
    if embedded_l1.exists():
        return embedded_l1
    return root_l1


def l0_rules_path(repo_root: Path) -> Path:
    root_l0 = repo_root / "L0_rules.md"
    if root_l0.exists():
        return root_l0
    embedded_l0 = repo_root / "framework" / "L0_rules.md"
    if embedded_l0.exists():
        return embedded_l0
    return root_l0


def te_command(repo_root: Path) -> str:
    """Return the command agents should run from repo_root."""
    root_te = repo_root / "te"
    if root_te.exists():
        return "./te"
    embedded_te = repo_root / "framework" / "te"
    if embedded_te.exists():
        return "./framework/te"
    return "python -m token_economy.cli"


def fresh_launch_commands(agent: str, repo_root: Path, handoff: Path | None = None) -> dict[str, Any]:
    key = (agent or "generic").lower()
    if key == "auto":
        key = "generic"
    repo = str(repo_root)
    handoff_path = str(handoff) if handoff else ".token-economy/checkpoints/<handoff>.md"
    start_path = str(startup_doc(repo_root))
    te = te_command(repo_root)
    prompt = (
        f"Read {start_path} and {handoff_path} only. Continue from that handoff. "
        "Do not load anything else until retrieval proves relevance. Start in plan mode."
    )
    commands = {
        "codex": [
            f'{te} context codex-fresh-thread --handoff "{handoff_path}" --execute',
            f'codex fork --last -C "{repo}" "{prompt}"',
            f'codex -C "{repo}" "{prompt}"',
            f'codex exec -C "{repo}" "{prompt}"',
        ],
        "claude": [
            f'claude --add-dir "{repo}" "{prompt}"',
            f'claude -p --add-dir "{repo}" "{prompt}"',
        ],
        "gemini": [
            f'gemini --prompt-interactive "{prompt}"',
            f'gemini --prompt "{prompt}"',
        ],
        "cursor": [
            f"Open a new Cursor/agent chat in {repo} and provide: {prompt}",
        ],
        "generic": [
            f"Start a new agent session in {repo} and provide: {prompt}",
        ],
    }
    return {
        "agent": key,
        "handoff": handoff_path,
        "startup_doc": start_path,
        "te_command": te,
        "preferred": commands.get(key, commands["generic"])[0],
        "alternatives": commands.get(key, commands["generic"])[1:],
        "note": "This starts a fresh successor session/thread instead of clearing the current host transcript.",
    }


def env_threshold(name: str, default: float) -> float:
    raw = os.environ.get(name)
    if raw is None:
        return default
    value = float(raw)
    return value / 100 if value > 1 else value


def status_for_text(text: str, max_tokens: int | str | None = None, threshold: float = 0.20, model: str | None = None) -> dict[str, Any]:
    used = estimate_tokens(text)
    maximum = resolve_max_tokens(max_tokens, model=model)
    refresh_threshold = env_threshold("REFRESH_AT_PCT", threshold)
    warn_threshold = env_threshold("WARN_AT_PCT", 0.15)
    ratio = used / maximum if maximum else 0.0
    action = "refresh" if ratio >= refresh_threshold else "warn" if ratio >= warn_threshold else "continue"
    return {
        "estimated_tokens": used,
        "max_tokens": maximum,
        "ratio": round(ratio, 4),
        "pct": round(ratio * 100, 2),
        "warn_threshold": warn_threshold,
        "refresh_threshold": refresh_threshold,
        "threshold": refresh_threshold,
        "action": action,
    }


def status_for_files(paths: list[Path], max_tokens: int | str | None = None, threshold: float = 0.20) -> dict[str, Any]:
    chunks = []
    for path in paths:
        if path.exists() and path.is_file():
            chunks.append(path.read_text(encoding="utf-8", errors="replace"))
    return status_for_text("\n".join(chunks), max_tokens=max_tokens, threshold=threshold)


def extract_transcript_facts(text: str) -> dict[str, list[str]]:
    paths = sorted(set(m.group("path").strip() for m in PATH_RE.finditer(text)))[:80]
    commands = sorted(set(m.group(1).strip().strip("\"'") for m in CMD_RE.finditer(text)))[:50]
    errors = sorted(set(m.group(1).strip() for m in ERR_RE.finditer(text)))[:50]
    decisions = sorted(set(line.strip("- ").strip() for line in text.splitlines() if "decision" in line.lower() or "decide" in line.lower()))[:30]
    wiki_pages = sorted(set(x for x in re.findall(r"\[\[([^\]]+)\]\]", text)))[:30]
    return {"files": paths, "commands": commands, "errors": errors, "decisions": decisions, "wiki_pages": wiki_pages}


def parse_handoff_metadata(path: Path) -> dict[str, str]:
    text = path.read_text(encoding="utf-8", errors="replace")
    if not text.startswith("---"):
        return {}
    parts = text.split("---", 2)
    if len(parts) < 3:
        return {}
    meta: dict[str, str] = {}
    for raw in parts[1].splitlines():
        if ":" not in raw:
            continue
        key, value = raw.split(":", 1)
        meta[key.strip()] = value.strip().strip("\"'")
    return meta


def meter(transcript: Path | None = None, model: str = "auto", max_tokens: int | str | None = None, threshold: float = 0.20) -> dict[str, Any]:
    text = ""
    if transcript and transcript.exists():
        text = transcript.read_text(encoding="utf-8", errors="replace")
    status = status_for_text(text, max_tokens=max_tokens, model=model, threshold=threshold)
    status["model"] = model
    status["tokenizer"] = "char/4-fallback"
    return status


def relay_state_paths(repo_root: Path) -> dict[str, Path]:
    state_dir = repo_root / ".token-economy" / "checkpoints" / "relay-auto"
    return {
        "dir": state_dir,
        "last": state_dir / "last-relay.json",
        "pending": state_dir / "pending-relay.json",
    }


def should_auto_relay(repo_root: Path, transcript: Path | None, status: dict[str, Any], cooldown_seconds: int = 1800) -> dict[str, Any]:
    paths = relay_state_paths(repo_root)
    if status.get("action") != "refresh":
        return {"should_relay": False, "reason": "below_threshold", "state": {k: str(v) for k, v in paths.items()}}
    if not transcript or not transcript.exists():
        return {"should_relay": False, "reason": "transcript_unavailable", "state": {k: str(v) for k, v in paths.items()}}
    stat = transcript.stat()
    key = {"path": str(transcript), "size": stat.st_size}
    now = datetime.now(timezone.utc).timestamp()
    previous: dict[str, Any] = {}
    if paths["last"].exists():
        try:
            previous = json.loads(paths["last"].read_text(encoding="utf-8"))
        except Exception:
            previous = {}
    recent = now - float(previous.get("time", 0)) < cooldown_seconds
    same_or_older = previous.get("path") == key["path"] and int(previous.get("size", 0)) >= key["size"]
    if recent or same_or_older:
        return {
            "should_relay": False,
            "reason": "cooldown_or_same_transcript",
            "previous": previous,
            "state": {k: str(v) for k, v in paths.items()},
        }
    payload = {**key, "time": now, "reason": "context >= refresh threshold", "action": "relay_at_safe_checkpoint"}
    return {"should_relay": True, "reason": "threshold_crossed", "payload": payload, "state": {k: str(v) for k, v in paths.items()}}


def write_pending_relay(repo_root: Path, payload: dict[str, Any]) -> dict[str, str]:
    paths = relay_state_paths(repo_root)
    paths["dir"].mkdir(parents=True, exist_ok=True)
    paths["last"].write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    paths["pending"].write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return {k: str(v) for k, v in paths.items()}


def checkpoint(
    repo_root: Path,
    goal: str = "",
    plan: str = "",
    transcript: Path | None = None,
    max_packet_tokens: int = 2000,
    context_pct: str | float = "unknown",
) -> dict[str, Any]:
    state_dir = repo_root / ".token-economy" / "checkpoints"
    state_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    transcript_text = ""
    if transcript and transcript.exists():
        transcript_text = transcript.read_text(encoding="utf-8", errors="replace")
    facts = extract_transcript_facts(transcript_text)
    old_thread_id = os.environ.get("CODEX_THREAD_ID") or "none"
    old_transcript = str(transcript) if transcript else "none"
    start_label = startup_doc_label(repo_root)
    te = te_command(repo_root)
    l0 = l0_rules_path(repo_root)
    l1 = l1_index_path(repo_root)
    l0_pointer = f"- L0 rules: `{_relative_or_abs(l0, repo_root)}`" if l0.exists() else f"- L0 rules: missing; run `{te} wiki index`."
    l1_pointer = f"- L1 index: `{_relative_or_abs(l1, repo_root)}`" if l1.exists() else f"- L1 index: missing; run `{te} wiki index`."
    task_slug = re.sub(r"[^a-zA-Z0-9]+", "-", (goal or "token-economy-task").lower()).strip("-") or "token-economy-task"
    iso = datetime.now(timezone.utc).isoformat()
    packet = f"""---
type: handoff
from-session: local
created: {iso}
context-pct-at-refresh: {context_pct}
next-mode: plan-first
old-thread-id: {old_thread_id}
old-transcript: {old_transcript}
old-session-query-policy: explicit-only
---

# HANDOFF - {task_slug}

## 1. Current task (1-liner)
{goal or "Continue the current Token Economy task."}

## 2. What done
- Handoff generated as a lean continuation packet.

## 3. What in-progress (blockers)
- {plan or "Inspect repo state, retrieve relevant wiki/context on demand, then execute verified steps."}

## 4. What next (priority order)
- Read this handoff and `{start_label}` only.
- Load L0/L1 pointers.
- Verify this is the fresh successor, then continue from where the old session stopped.
- Build plan before execution.

## 5. Key files touched (paths only - do NOT re-read speculatively)
{format_list(facts["files"])}

## 6. Key decisions + reasoning (why, not what)
{format_list(facts["decisions"])}

## 7. Wiki pages updated / created (wikilinks)
{format_list(facts["wiki_pages"])}

## 8. Open questions
- Retrieve relevant pages before deciding.
- Keep Caveman Ultra for surfaced output unless user asks for detail.
- Document durable facts only after verified execution; use a lightweight wiki-documenter for docs-only memory.

## 9. Instructions for next agent
- Start in plan mode. Think step-by-step. Create a robust plan before executing.
- Read this handoff + `{start_label}` only. Do not load full wiki.
- Do not load docs-only wiki memory; retrieve linked pages only when relevant.
- Build plan. Get user approval if host process requires approval. Then execute.
- If a needed fact is absent and repo/wiki retrieval is insufficient, ask the old session explicitly:
  `{te} context ask-old --handoff <handoff-file> --question "<specific missing fact>"`
- Record old-session answers only if they change ongoing work or the next handoff.
- On complete: update wiki, log entry, create fresh handoff if context >= 20%.
- If old host could not clear context, continue implementation only in this fresh session.

## Memory Pointers
{l0_pointer}
{l1_pointer}
- Startup contract: `{start_label}`
- Token Economy CLI: `{te}`
- Wiki search: `{te} wiki search "<query>"`
- Recent context: `{te} context status`
- L2 facts: `L2_facts/`
- L3 SOPs: `L3_sops/`
- L4 archive: `L4_archive/`

## Commands Seen
{format_list(facts["commands"])}

## Errors Seen
{format_list(facts["errors"])}
"""
    packet = trim_to_tokens(packet, max_packet_tokens)
    path = state_dir / f"{ts}-fresh-session.md"
    path.write_text(packet, encoding="utf-8")
    return {"path": str(path), "tokens": estimate_tokens(packet), "packet": packet}


def lint_handoff(path: Path, max_tokens: int = 2000) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8", errors="replace")
    required = [
        "## 1. Current task",
        "## 2. What done",
        "## 3. What in-progress",
        "## 4. What next",
        "## 5. Key files touched",
        "## 6. Key decisions",
        "## 7. Wiki pages updated",
        "## 8. Open questions",
        "## 9. Instructions for next agent",
        "Start in plan mode",
    ]
    missing = [item for item in required if item not in text]
    tokens = estimate_tokens(text)
    return {"path": str(path), "tokens": tokens, "max_tokens": max_tokens, "missing": missing, "ok": not missing and tokens <= max_tokens}


def ask_old_from_transcript(transcript: Path, question: str, max_snippets: int = 8) -> dict[str, Any]:
    if not transcript.exists():
        return {"ok": False, "mode": "transcript", "error": "old transcript unavailable", "transcript": str(transcript)}
    text = transcript.read_text(encoding="utf-8", errors="replace")
    terms = [term.lower() for term in re.findall(r"[A-Za-z0-9_.-]{4,}", question)][:12]
    lines = text.splitlines()
    scored: list[tuple[int, int, str]] = []
    for i, line in enumerate(lines):
        haystack = line.lower()
        score = sum(1 for term in terms if term in haystack)
        if score:
            scored.append((score, i, line.strip()))
    scored.sort(key=lambda row: (-row[0], row[1]))
    snippets = []
    seen: set[int] = set()
    for _, idx, _ in scored:
        if idx in seen:
            continue
        seen.add(idx)
        start = max(0, idx - 1)
        end = min(len(lines), idx + 2)
        snippets.append({"line": idx + 1, "text": "\n".join(line.strip() for line in lines[start:end] if line.strip())[:1200]})
        if len(snippets) >= max_snippets:
            break
    return {
        "ok": bool(snippets),
        "mode": "transcript",
        "question": question,
        "transcript": str(transcript),
        "snippets": snippets,
        "note": "Bounded transcript search only; ask a narrower question if the answer is missing.",
    }


def ask_old_session_plan(repo_root: Path, handoff: Path, question: str, execute: bool = False) -> dict[str, Any]:
    meta = parse_handoff_metadata(handoff)
    old_thread_id = meta.get("old-thread-id")
    old_transcript = meta.get("old-transcript")
    if old_thread_id and old_thread_id != "none":
        return {
            "ok": True,
            "mode": "codex-old-thread",
            "execute": execute,
            "thread_id": old_thread_id,
            "old_transcript": old_transcript,
            "handoff": str(handoff),
            "question": question,
            "prompt": (
                "Answer only this specific relay follow-up from your old session context. "
                "Cite the source from old context when possible. Do not continue implementation. "
                f"Question: {question}"
            ),
            "command": f'{te_command(repo_root)} context ask-old --handoff "{handoff}" --question "{question}" --execute',
        }
    if old_transcript and old_transcript != "none":
        transcript = Path(old_transcript).expanduser()
        if not transcript.is_absolute():
            transcript = repo_root / transcript
        return ask_old_from_transcript(transcript, question)
    return {
        "ok": False,
        "mode": "unavailable",
        "handoff": str(handoff),
        "question": question,
        "error": "old session unavailable",
        "next": "Use repo/wiki retrieval such as `./te wiki search` or `./te code map`.",
    }


def format_list(items: list[str], max_items: int = 8, max_chars: int = 140) -> str:
    if not items:
        return "- none captured"
    lines = []
    for item in items[:max_items]:
        value = item if len(item) <= max_chars else item[: max_chars - 15].rstrip() + " ...[trimmed]"
        lines.append(f"- `{value}`")
    if len(items) > max_items:
        lines.append(f"- `...[{len(items) - max_items} more omitted; ask old session or inspect transcript if needed]...`")
    return "\n".join(lines)
