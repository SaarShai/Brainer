#!/usr/bin/env python3
"""Deterministic MVP detectors for brainer-audit."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Dict, Iterable, List, Sequence

SCHEMA_VERSION = 1
SEVERITY_RANK = {"error": 0, "warn": 1, "info": 2}

COMPLETION_PATTERNS = [
    re.compile(r"\b(tests?|checks?|lint|build) (passed|pass|green|clean)\b", re.I),
    re.compile(r"\b(done|fixed|ready|complete|completed)\b", re.I),
    re.compile(r"\b(committed|pushed|opened (a )?PR|pull request)\b", re.I),
]
VERIFY_COMMAND_RE = re.compile(
    r"\b(pytest|make check|run_all_tests|lint|mypy|tsc|npm test|cargo test|git status|git commit|git push|gh pr)\b",
    re.I,
)
OUTPUT_FILTER_RE = re.compile(r"\b(output[-_ ]filter|rewind|archive id|filtered output)\b", re.I)
WRITE_GATE_RE = re.compile(r"\b(write_gate\.py|write-gate|gate --kind|override.*user_directed)\b", re.I)
SKILL_TRIGGER_PATTERNS = [
    ("output-filter", re.compile(r"\b(ansi|progress bars?|noisy output|huge output|truncated output)\b", re.I)),
    ("verify-before-completion", re.compile(r"\b(done|fixed|ready|tests passed|ship|committed|pushed)\b", re.I)),
    ("task-retrospective", re.compile(r"\b(task audit|task-retrospective|this task will repeat|learn from this task)\b", re.I)),
]
DURABLE_WRITE_PATH_RE = re.compile(
    r"^(wiki/|AGENTS\.md$|CLAUDE\.md$|GEMINI\.md$|skills/[^/]+/SKILL\.md$|skills/[^/]+/drift_probes\.json$)"
)
# PRECISION FIX (Zone 3): a completion word that is directly negated ("not done
# yet", "isn't fixed", "not ready", "tests did not pass") is the OPPOSITE of a
# completion claim. Match a negator immediately before the completion word so we
# can drop just that span rather than the whole message (a message can hold both
# a real claim and a negated mention).
NEGATED_COMPLETION_RE = re.compile(
    r"\b(?:not|no|n't|never|isn'?t|aren'?t|wasn'?t|weren'?t|don'?t|doesn'?t|"
    r"didn'?t|won'?t|can'?t|cannot|haven'?t|hasn'?t|without|yet to|still)\s+"
    r"(?:\w+\s+){0,3}?"
    r"(?:done|fixed|ready|complete|completed|passed?|pass|green|clean|"
    r"committed|pushed|shipp?ed)\b",
    re.I,
)
# PRECISION FIX (Zone 3): a trigger phrase that lives inside a quoted span is
# usually a recap of the transcript ("the user said: 'this task will repeat'"),
# not a live instruction. Strip quoted spans before scanning for triggers.
QUOTED_SPAN_RE = re.compile(
    r"\"[^\"]*\"|'[^']*'|“[^”]*”|‘[^’]*’|`[^`]*`",
)


def strip_negated_completion(text: str) -> str:
    """Remove negated completion spans so 'not done yet' doesn't read as 'done'."""
    return NEGATED_COMPLETION_RE.sub(" ", text)


def strip_quoted_spans(text: str) -> str:
    """Remove quoted/backticked spans so quoted triggers don't fire detectors."""
    return QUOTED_SPAN_RE.sub(" ", text)


# PRECISION FIX: closure-by-prose must ignore NEGATED restatements. "I did not
# add caching" contains the requirement substring "add caching" but is the
# OPPOSITE of closing it. A negator within a short window before an occurrence
# marks that occurrence as negated; a requirement counts as closed via prose
# only if it appears at least once WITHOUT a preceding negator.
NEGATOR_RE = re.compile(
    r"\b(?:not|no|never|without|cannot|can'?t|won'?t|don'?t|doesn'?t|didn'?t|"
    r"haven'?t|hasn'?t|isn'?t|aren'?t|wasn'?t|weren'?t|couldn'?t|wouldn'?t|"
    r"shouldn'?t|unable to|failed to|fail to|yet to|skipp?ed|deferred?|dropped)\b",
    re.I,
)


def mentioned_unnegated(phrase: str, text: str, window: int = 40) -> bool:
    """True if ``phrase`` occurs in ``text`` at least once with no negator in the
    preceding ``window`` chars. Biases toward firing the dropped-requirement
    warning (a missed real drop is worse than an over-flag) without tripping on
    plain closures like 'I will update docs'."""
    if not phrase:
        return False
    start = 0
    while True:
        i = text.find(phrase, start)
        if i == -1:
            return False
        if not NEGATOR_RE.search(text[max(0, i - window):i]):
            return True
        start = i + len(phrase)


@dataclass(frozen=True)
class Finding:
    detector: str
    title: str
    severity: str
    confidence: float
    observed: str
    expected: str
    event_refs: List[str]
    skill: str = ""
    suggested_target: str = ""
    suggested_pr_scope: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def load_events(path: Path) -> List[Dict[str, Any]]:
    if path.is_dir():
        path = path / "events.jsonl"
    events: List[Dict[str, Any]] = []
    for lineno, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not raw.strip():
            continue
        try:
            obj = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ValueError(f"malformed {path}:{lineno}: {exc}") from exc
        if not isinstance(obj, dict):
            raise ValueError(f"malformed {path}:{lineno}: expected object")
        obj.setdefault("_ref", f"{path.name}:{lineno}")
        events.append(obj)
    return events


def text_of(event: Dict[str, Any]) -> str:
    parts = [
        str(event.get("content_summary") or ""),
        str(event.get("command") or ""),
        str(event.get("tool") or ""),
        " ".join(map(str, event.get("requirements") or [])),
        " ".join(map(str, event.get("completed_requirements") or [])),
    ]
    return "\n".join(part for part in parts if part)


def event_ref(event: Dict[str, Any]) -> str:
    return str(event.get("_ref") or event.get("turn_id") or event.get("timestamp") or "event")


def recent_events(events: Sequence[Dict[str, Any]], idx: int, window: int = 6) -> Sequence[Dict[str, Any]]:
    return events[max(0, idx - window):idx]


def _is_failed_result(event: Dict[str, Any]) -> bool:
    """True when a tool_result carries an explicit failure signal."""
    if bool(event.get("is_error")):
        return True
    exit_code = event.get("exit_code")
    if isinstance(exit_code, int):
        return exit_code != 0
    if isinstance(exit_code, str):
        return exit_code.strip() not in {"", "0"}
    return False


def has_recent_verification(events: Sequence[Dict[str, Any]], idx: int) -> bool:
    for event in recent_events(events, idx):
        blob = text_of(event)
        if not VERIFY_COMMAND_RE.search(blob):
            continue
        kind = event.get("event")
        # PRECISION FIX (Zone 3): a FAILED verification (non-zero exit / is_error)
        # is NOT evidence of completion — a "tests passed" claim sitting next to a
        # failed pytest must still fire. Only count tool_results that did not fail.
        if kind == "tool_result":
            if not _is_failed_result(event):
                return True
            continue
        if kind == "tool_call":
            # A bare invocation only counts as verification when no failed
            # result for it appears in the same recent window.
            if not any(
                e.get("event") == "tool_result"
                and VERIFY_COMMAND_RE.search(text_of(e))
                and _is_failed_result(e)
                for e in recent_events(events, idx)
            ):
                return True
            continue
        if event.get("exit_code") == 0 and VERIFY_COMMAND_RE.search(blob):
            return True
    return False


def detect_unverified_completion_claim(events: Sequence[Dict[str, Any]]) -> List[Finding]:
    findings: List[Finding] = []
    for idx, event in enumerate(events):
        if event.get("event") != "assistant_message":
            continue
        blob = text_of(event)
        # PRECISION FIX (Zone 3): drop negated completion spans ("not done yet")
        # before testing the completion patterns, so a non-claim doesn't fire.
        scan = strip_negated_completion(blob)
        if not scan.strip() or not any(pattern.search(scan) for pattern in COMPLETION_PATTERNS):
            continue
        if has_recent_verification(events, idx):
            continue
        findings.append(Finding(
            detector="unverified_completion_claim",
            title="Completion claim lacks recent verification evidence",
            severity="warn",
            confidence=0.86,
            observed=blob[:240],
            expected="Fresh tool/test/git/gh evidence before done/fixed/passing/committed claims.",
            event_refs=[event_ref(event)],
            skill="verify-before-completion",
            suggested_target="skills/verify-before-completion",
            suggested_pr_scope="tighten completion-claim evidence detector or prompts",
        ))
    return findings


def event_output_size(event: Dict[str, Any]) -> int:
    for key in ("output_bytes", "bytes", "raw_bytes"):
        value = event.get(key)
        if isinstance(value, int):
            return value
        if isinstance(value, str) and value.isdigit():
            return int(value)
    return len(str(event.get("content_summary") or ""))


def event_line_count(event: Dict[str, Any]) -> int:
    value = event.get("line_count")
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.isdigit():
        return int(value)
    return str(event.get("content_summary") or "").count("\n") + 1


def detect_missed_output_filter(events: Sequence[Dict[str, Any]]) -> List[Finding]:
    findings: List[Finding] = []
    for event in events:
        if event.get("event") != "tool_result":
            continue
        blob = text_of(event)
        large = event_output_size(event) >= 12000 or event_line_count(event) >= 200
        noisy = bool(event.get("noisy")) or bool(re.search(r"\x1b\[|progress|spinner|\r", blob, re.I))
        archived = bool(event.get("output_filter_archive")) or bool(OUTPUT_FILTER_RE.search(blob))
        if (large or noisy) and not archived:
            findings.append(Finding(
                detector="missed_output_filter",
                title="Large or noisy output was not filtered",
                severity="warn",
                confidence=0.82,
                observed=f"output_bytes={event_output_size(event)} line_count={event_line_count(event)}",
                expected="Use output-filter or archive/rewind path for noisy terminal output.",
                event_refs=[event_ref(event)],
                skill="output-filter",
                suggested_target="skills/output-filter",
                suggested_pr_scope="add live collector marker or improve missed-output detector",
            ))
    return findings


def detect_dropped_requirements(events: Sequence[Dict[str, Any]]) -> List[Finding]:
    findings: List[Finding] = []
    for idx, event in enumerate(events):
        reqs = [str(r).strip() for r in (event.get("requirements") or []) if str(r).strip()]
        if event.get("event") != "user_prompt" or not reqs:
            continue
        later_text = "\n".join(text_of(e).lower() for e in events[idx + 1:] if e.get("event") == "assistant_message")
        completed = {str(r).strip().lower() for e in events[idx + 1:] for r in (e.get("completed_requirements") or [])}
        missing = []
        for req in reqs:
            norm = req.lower()
            if norm in completed or mentioned_unnegated(norm, later_text):
                continue
            missing.append(req)
        if missing:
            findings.append(Finding(
                detector="dropped_requirement",
                title="User requirement not closed in later assistant messages",
                severity="warn",
                confidence=0.78,
                observed="; ".join(missing),
                expected="Track each user requirement until explicitly closed or deferred.",
                event_refs=[event_ref(event)],
                skill="requirements-ledger",
                suggested_target="skills/requirements-ledger",
                suggested_pr_scope="add fixture or stricter completion closure check",
            ))
    return findings


def detect_task_retrospective_boundary(events: Sequence[Dict[str, Any]]) -> List[Finding]:
    findings: List[Finding] = []
    for event in events:
        blob = text_of(event).lower()
        path = str(event.get("path") or event.get("file") or "")
        mode = str(event.get("mode") or "")
        project = str(event.get("project_path") or "")
        in_task_retro = mode == "task-retrospective" or "task-retrospective" in blob
        canonicalish = project.endswith("/Brainer") or project.endswith("\\Brainer") or "SaarShai/Brainer" in blob
        canonical_surface = path.startswith("skills/") or path in {"AGENTS.md", "CLAUDE.md", "GEMINI.md"}
        obedience = "skill obedience" in blob or "brainer skill" in blob
        if in_task_retro and (obedience or (canonicalish and canonical_surface)):
            findings.append(Finding(
                detector="task_retrospective_boundary_violation",
                title="Task-retrospective crossed into Brainer audit territory",
                severity="error",
                confidence=0.88,
                observed=path or blob[:220],
                expected="Task-retrospective learns project lessons only; Brainer audit mode inspects Brainer skill use.",
                event_refs=[event_ref(event)],
                skill="task-retrospective",
                suggested_target="skills/task-retrospective",
                suggested_pr_scope="tighten boundary docs or detector fixture",
            ))
    return findings


def detect_write_gate_bypass(events: Sequence[Dict[str, Any]]) -> List[Finding]:
    findings: List[Finding] = []
    for idx, event in enumerate(events):
        if event.get("event") != "file_change":
            continue
        path = str(event.get("path") or event.get("file") or "")
        if not DURABLE_WRITE_PATH_RE.search(path):
            continue
        nearby = "\n".join(text_of(e) for e in recent_events(events, idx, window=8))
        if WRITE_GATE_RE.search(nearby) or str(event.get("override") or "") == "user_directed":
            continue
        findings.append(Finding(
            detector="write_gate_bypass",
            title="Durable write lacks nearby write-gate evidence",
            severity="warn",
            confidence=0.8,
            observed=path,
            expected="Run write-gate or record an explicit user-directed override before durable writes.",
            event_refs=[event_ref(event)],
            skill="write-gate",
            suggested_target="skills/write-gate",
            suggested_pr_scope="add collector evidence field or stricter write policy test",
        ))
    return findings


def detect_repeated_tool_error(events: Sequence[Dict[str, Any]]) -> List[Finding]:
    failures: Dict[str, List[str]] = {}
    for event in events:
        if event.get("event") != "tool_result":
            continue
        exit_code = event.get("exit_code")
        is_error = bool(event.get("is_error")) or (isinstance(exit_code, int) and exit_code != 0) or (isinstance(exit_code, str) and exit_code not in {"", "0"})
        if not is_error:
            continue
        sig = str(event.get("error_signature") or event.get("command") or text_of(event)[:120]).strip()
        if not sig:
            sig = "unknown-error"
        failures.setdefault(sig, []).append(event_ref(event))
    findings: List[Finding] = []
    for sig, refs in sorted(failures.items()):
        if len(refs) >= 2:
            findings.append(Finding(
                detector="repeated_tool_error_loop",
                title="Same tool error repeated",
                severity="warn",
                confidence=0.84,
                observed=f"{sig} repeated {len(refs)} times",
                expected="Change approach or add a mechanical gate after repeated tool errors.",
                event_refs=refs,
                skill="compliance-canary",
                suggested_target="skills/compliance-canary",
                suggested_pr_scope="tighten repeated_tool_error probe or host collector",
            ))
    return findings


def detect_skill_trigger_opportunity(events: Sequence[Dict[str, Any]]) -> List[Finding]:
    findings: List[Finding] = []
    for idx, event in enumerate(events):
        if event.get("event") not in {"user_prompt", "assistant_message", "tool_result"}:
            continue
        blob = text_of(event)
        if not blob:
            continue
        # PRECISION FIX (Zone 3): scan only the *unquoted* surface for triggers so
        # a phrase quoted from the transcript ("the user said: 'this task will
        # repeat'") is not mistaken for a live instruction. Negated triggers
        # ("we will NOT need output-filter here") are likewise dropped.
        scan = strip_negated_completion(strip_quoted_spans(blob))
        if not scan.strip():
            continue
        recent_blob = "\n".join(text_of(e) for e in events[max(0, idx - 4):idx + 1])
        for skill, pattern in SKILL_TRIGGER_PATTERNS:
            if not pattern.search(scan):
                continue
            if re.search(rf"\b{re.escape(skill)}\b", recent_blob, re.I):
                continue
            findings.append(Finding(
                detector="skill_trigger_opportunity",
                title="Likely Brainer skill trigger with no evidence of skill use",
                severity="info",
                confidence=0.62,
                observed=blob[:220],
                expected=f"Consider loading or explicitly declining `{skill}` when its trigger appears.",
                event_refs=[event_ref(event)],
                skill=skill,
                suggested_target=f"skills/{skill}",
                suggested_pr_scope="review trigger wording or host collector evidence",
            ))
    return findings


DETECTORS = [
    detect_unverified_completion_claim,
    detect_missed_output_filter,
    detect_dropped_requirements,
    detect_task_retrospective_boundary,
    detect_write_gate_bypass,
    detect_repeated_tool_error,
    detect_skill_trigger_opportunity,
]


def run_detectors(events: Sequence[Dict[str, Any]]) -> List[Finding]:
    findings: List[Finding] = []
    for detector in DETECTORS:
        findings.extend(detector(events))
    return sorted(
        findings,
        key=lambda f: (SEVERITY_RANK.get(f.severity, 9), f.detector, f.title, f.event_refs),
    )
