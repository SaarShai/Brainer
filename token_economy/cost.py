from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from .context import current_codex_transcript, meter
from .output_filter import stats as output_filter_stats
from .tokens import estimate_tokens


BYPASS_RE = re.compile(r"\bNO\s+COST\s+PREFLIGHT\b", re.IGNORECASE)
HIGH_RISK_RE = re.compile(r"\b(security|credential|secret|delete|destructive|migration|architect|architecture|privacy)\b", re.IGNORECASE)
BROAD_CODE_RE = re.compile(r"\b(implement|build|debug|bug|refactor|review|code review|fix failing|stack trace|endpoint|api|component|cross[- ]?file)\b", re.IGNORECASE)
TRIVIAL_RE = re.compile(r"\b(typo|one[- ]?line|format|lint|rename variable|small fix|summari[sz]e|classify|extract)\b", re.IGNORECASE)
RESEARCH_RE = re.compile(r"\b(research|survey|compare|find repos?|literature|web)\b", re.IGNORECASE)
PATH_RE = re.compile(r"(?P<path>(?:/|\.{1,2}/|[\w.-]+/)[\w./ @+-]+\.[A-Za-z_][A-Za-z0-9_+-]*)")
READ_COMMAND_RE = re.compile(r"\b(cat|sed|nl|less|head|tail|open|read_file|view_image)\b", re.IGNORECASE)
SEARCH_COMMAND_RE = re.compile(r"\b(rg|grep|code map|wiki context|wiki search)\b", re.IGNORECASE)
VERIFY_RE = re.compile(r"\b(pytest|unittest|npm test|make test|go test|cargo test|doctor|lint|build|typecheck|smoke)\b", re.IGNORECASE)
MUTATION_RE = re.compile(r"\b(apply_patch|write|edit|created|updated|changed|implemented)\b", re.IGNORECASE)


CONTEXT_PLAN = [
    'run `./te code map "<task/symbol>"` before broad file reads',
    "use `rg` for exact symbols/errors before opening files",
    "load only directly relevant files plus nearby tests",
    "ask for missing files instead of volunteering just-in-case context",
]
TOOL_PLAN = [
    "batch related reads/searches in one tool round",
    "summarize large outputs before feeding them back into context",
    "use deterministic helpers for repeated workflows",
]
SESSION_PLAN = [
    "check `./te context status` or `./te context meter` on long sessions",
    "write `./te context checkpoint --handoff-template` before context gets noisy",
    "crystallize repeated verified workflows into L3 SOPs",
]


def task_kind(task: str) -> str:
    if BYPASS_RE.search(task):
        return "bypass"
    if TRIVIAL_RE.search(task) and not BROAD_CODE_RE.search(task):
        return "trivial"
    if BROAD_CODE_RE.search(task):
        return "broad_code"
    if RESEARCH_RE.search(task):
        return "research"
    return "general"


def risk_for(task: str, kind: str) -> str:
    if HIGH_RISK_RE.search(task):
        return "high"
    if kind in {"broad_code", "research"}:
        return "medium"
    return "low"


def should_nudge(packet: dict[str, Any]) -> bool:
    return bool(packet.get("task_kind") in {"broad_code", "research"} and not packet.get("bypass", {}).get("active"))


def preflight(task: str) -> dict[str, Any]:
    kind = task_kind(task)
    bypass_reason = ""
    if kind == "bypass":
        bypass_reason = "explicit NO COST PREFLIGHT"
    elif kind == "trivial":
        bypass_reason = "small task; hook stays quiet"
    warnings: list[str] = []
    if kind in {"broad_code", "research"} and not PATH_RE.search(task):
        warnings.append("No path or symbol named; search/map before reading files.")
    if risk_for(task, kind) == "high":
        warnings.append("High-risk task; keep context precise and verify before acting.")
    return {
        "mode": "cost_preflight",
        "task_kind": kind,
        "risk": risk_for(task, kind),
        "context_plan": [] if kind == "bypass" else CONTEXT_PLAN,
        "tool_plan": [] if kind == "bypass" else TOOL_PLAN,
        "session_plan": [] if kind == "bypass" else SESSION_PLAN,
        "bypass": {"active": bool(bypass_reason), "reason": bypass_reason},
        "warnings": warnings,
    }


def preflight_nudge(task: str) -> str:
    packet = preflight(task)
    if not should_nudge(packet):
        return ""
    lines = [
        "[token-economy:cost] preflight nudge",
        '- run `./te code map "<task/symbol>"` before broad reads',
        "- use `rg` for exact symbols/errors first",
        "- load only relevant files + nearby tests; batch reads; summarize large outputs",
        "- checkpoint/refresh if context grows; bypass with `NO COST PREFLIGHT`",
    ]
    if packet["warnings"]:
        lines.append(f"- warning: {packet['warnings'][0]}")
    return "\n".join(lines) + "\n"


def _finding(kind: str, severity: str, estimated_tokens: int, reason: str, evidence: str, recommendation: str) -> dict[str, Any]:
    return {
        "kind": kind,
        "severity": severity,
        "estimated_tokens": estimated_tokens,
        "reason": reason,
        "evidence": evidence[:240],
        "recommendation": recommendation,
    }


def _line_path(line: str) -> str | None:
    match = PATH_RE.search(line)
    if not match:
        return None
    return match.group("path").strip().rstrip(".,);]")


def profile(transcript: str | Path | None = None, *, max_tokens: int | str | None = None, refresh_threshold: float = 0.20) -> dict[str, Any]:
    path = Path(transcript).expanduser() if transcript else current_codex_transcript()
    if not path or not path.exists():
        return {
            "mode": "cost_profile",
            "transcript": str(path) if path else None,
            "ok": False,
            "reason": "transcript_unavailable",
            "findings": [],
        }

    text = path.read_text(encoding="utf-8", errors="replace")
    lines = text.splitlines()
    findings: list[dict[str, Any]] = []

    for idx, line in enumerate(lines, 1):
        tokens = estimate_tokens(line)
        if tokens >= 2000:
            findings.append(
                _finding(
                    "oversized_tool_output",
                    "high" if tokens >= 5000 else "medium",
                    tokens,
                    "one transcript line is large enough to bloat model context",
                    f"line {idx}: {line[:160]}",
                    "summarize or filter this tool output before continuing",
                )
            )

    read_counts: dict[str, int] = {}
    first_read: tuple[int, str] | None = None
    first_search_idx: int | None = None
    for idx, line in enumerate(lines, 1):
        if first_search_idx is None and SEARCH_COMMAND_RE.search(line):
            first_search_idx = idx
        if READ_COMMAND_RE.search(line):
            path_hit = _line_path(line)
            if path_hit:
                read_counts[path_hit] = read_counts.get(path_hit, 0) + 1
                if first_read is None:
                    first_read = (idx, path_hit)

    for path_hit, count in sorted(read_counts.items(), key=lambda item: (-item[1], item[0])):
        if count >= 2:
            findings.append(
                _finding(
                    "repeated_file_read",
                    "medium",
                    0,
                    f"same file appears in read-style commands {count} times",
                    path_hit,
                    "cache the relevant excerpt or use a semantic/code-map summary",
                )
            )

    if first_read and (first_search_idx is None or first_read[0] < first_search_idx):
        findings.append(
            _finding(
                "read_before_search",
                "medium",
                0,
                "file read happened before an `rg`/grep/code-map/wiki-search signal",
                f"line {first_read[0]}: {first_read[1]}",
                "run `rg` or `./te code map` before broad reads",
            )
        )

    context_status = meter(path, max_tokens=max_tokens, threshold=refresh_threshold)
    if context_status["action"] == "refresh":
        findings.append(
            _finding(
                "long_session_refresh",
                "high",
                int(context_status["estimated_tokens"]),
                f"context estimate is {context_status['pct']}% of max",
                str(path),
                "write a checkpoint and continue with a fresh/compact context",
            )
        )

    joined = "\n".join(lines[-80:])
    if MUTATION_RE.search(joined) and VERIFY_RE.search(joined):
        findings.append(
            _finding(
                "workflow_candidate",
                "low",
                0,
                "recent transcript includes both mutation and verification signals",
                "last 80 lines",
                "consider crystallizing the verified workflow into an L3 SOP",
            )
        )

    severity_order = {"high": 0, "medium": 1, "low": 2}
    findings.sort(key=lambda row: (severity_order.get(str(row["severity"]), 9), -int(row.get("estimated_tokens", 0))))
    return {
        "mode": "cost_profile",
        "transcript": str(path),
        "ok": True,
        "estimated_tokens": estimate_tokens(text),
        "line_count": len(lines),
        "context": context_status,
        "findings": findings,
    }


def report(repo_root: str | Path, transcript: str | Path | None = None, *, max_tokens: int | str | None = None, refresh_threshold: float = 0.20) -> dict[str, Any]:
    repo = Path(repo_root).expanduser().resolve()
    prof = profile(transcript, max_tokens=max_tokens, refresh_threshold=refresh_threshold)
    try:
        out_stats = output_filter_stats(repo)
    except Exception as exc:  # pragma: no cover - defensive for partial installs
        out_stats = {"error": str(exc)}
    return {
        "mode": "cost_report",
        "repo_root": str(repo),
        "profile": prof,
        "output_filter": out_stats,
        "summary": {
            "profile_findings": len(prof.get("findings", [])),
            "output_filter_events": out_stats.get("events") if isinstance(out_stats, dict) else None,
            "token_counts_are_estimates": True,
        },
    }
