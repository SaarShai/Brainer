from __future__ import annotations

import re
from datetime import date
from pathlib import Path
from typing import Any


def _text(event: Any) -> str:
    if isinstance(event, dict):
        return " ".join(str(v) for v in event.values())
    return str(event)


def _slug(text: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", text.lower()).strip("-")
    return slug[:80] or "completed-task"


def detect_task_completion(transcript_events) -> dict:
    """Detect verified task completion based on recent transcript events."""
    if not isinstance(transcript_events, list):
        return {"completed": False, "confidence": 0.0, "reason": "invalid_type"}
    if not transcript_events:
        return {"completed": False, "confidence": 0.0, "reason": "empty_input"}
    events = [_text(event).lower() for event in transcript_events[-30:]]
    joined = "\n".join(events)
    if re.search(r"\b(fail|failed|error|traceback|exit code [1-9])\b", joined) and not re.search(r"\b(fixed|passes|passed|ok|success)\b", joined):
        return {"completed": False, "confidence": 0.1, "reason": "recent_failure"}

    signals: list[str] = []
    score = 0
    if re.search(r"\b(done|works|ship|finished|complete|completed)\b", joined):
        score += 1
        signals.append("positive_close")
    if re.search(r"\b(pytest|unittest|npm test|make test|go test|mvn test|cargo test)\b", joined) and re.search(r"\b(pass|passed|ok|success|0 failed)\b", joined):
        score += 2
        signals.append("verified_test")
    if re.search(r"\b(doctor|lint|build|typecheck|smoke)\b", joined) and re.search(r"\b(ok|pass|passed|success|true)\b", joined):
        score += 2
        signals.append("verified_check")
    if re.search(r"\b(apply_patch|write|edit|created|updated|changed|implemented)\b", joined):
        score += 1
        signals.append("material_change")
    if re.search(r"\bgit commit\b", joined):
        score += 2
        signals.append("commit_detected")

    completed = score >= 3 and any(sig.startswith("verified") for sig in signals)
    return {"completed": completed, "confidence": min(1.0, score / 6.0), "reason": "; ".join(signals) if signals else "no_signals"}


def extract_sop_candidate(transcript_events, task: str | None = None) -> dict[str, Any]:
    events = [_text(event).strip() for event in transcript_events if _text(event).strip()]
    command_lines = [line for line in events if re.search(r"\b(pytest|unittest|npm test|make test|go test|doctor|lint|build|apply_patch)\b", line, re.IGNORECASE)]
    changed = sorted(set(re.findall(r"[\w./-]+\.(?:py|md|sh|yaml|yml|json|toml|ts|tsx|js)", "\n".join(events))))[:12]
    title = task or next((line for line in events if len(line) > 12), "Completed task")
    return {
        "title": title[:120],
        "slug": _slug(title),
        "steps": command_lines[:12],
        "changed_files": changed,
        "evidence": events[-12:],
    }


def crystallize_task(transcript_events, root: str | Path, task: str | None = None) -> dict[str, Any]:
    """Write an L3 SOP candidate after verified execution.

    This is intentionally conservative: unverified plans, failed attempts, and
    trivial read-only work return a skipped packet instead of persistent memory.
    """
    detection = detect_task_completion(transcript_events)
    if not detection["completed"]:
        return {"action": "skip", "reason": detection["reason"], "completed": False, "confidence": detection["confidence"]}

    repo = Path(root).expanduser().resolve()
    candidate = extract_sop_candidate(transcript_events, task=task)
    if len(candidate["steps"]) < 2:
        return {"action": "skip", "reason": "not_enough_reusable_steps", "completed": True, "confidence": detection["confidence"]}

    today = date.today().isoformat()
    target_dir = repo / "L3_sops"
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / f"{candidate['slug']}.md"
    if target.exists():
        return {"action": "skip", "reason": "sop_exists", "path": target.relative_to(repo).as_posix(), "completed": True, "confidence": detection["confidence"]}

    related = ["[[index]]", "[[schema]]"]
    changed_lines = [f"- `{path}`" for path in candidate["changed_files"]] or ["- None recorded."]
    step_lines = [f"{i}. {step[:220]}" for i, step in enumerate(candidate["steps"], 1)]
    evidence_lines = [f"- {line[:220]}" for line in candidate["evidence"]]
    content = "\n".join(
        [
            "---",
            "schema_version: 2",
            f'title: "{candidate["title"].replace(chr(34), chr(39))}"',
            "type: sop",
            "domain: framework",
            "tier: procedural",
            f"confidence: {round(detection['confidence'], 2)}",
            f"created: {today}",
            f"updated: {today}",
            f"verified: {today}",
            "sources: [\"transcript-events\"]",
            "supersedes: []",
            "superseded-by:",
            "tags: [skill-crystallizer, sop]",
            "---",
            "",
            f"# {candidate['title']}",
            "",
            "## Summary",
            "Reusable workflow crystallized from verified task completion.",
            "",
            "## Steps",
            *step_lines,
            "",
            "## Changed Files",
            *changed_lines,
            "",
            "## Evidence",
            *evidence_lines,
            "",
            "## Related",
            *[f"- {link}" for link in related],
            "",
        ]
    )
    target.write_text(content, encoding="utf-8")

    try:
        from token_economy.wiki import WikiStore

        wiki = WikiStore(repo)
        wiki.append_log("crystallize", candidate["title"], f"Created `{target.relative_to(repo).as_posix()}` from verified task completion.")
        wiki.index()
    except Exception as exc:  # pragma: no cover - best-effort index refresh
        return {
            "action": "created",
            "path": target.relative_to(repo).as_posix(),
            "completed": True,
            "confidence": detection["confidence"],
            "index_warning": str(exc),
        }

    return {
        "action": "created",
        "path": target.relative_to(repo).as_posix(),
        "completed": True,
        "confidence": detection["confidence"],
        "evidence_used": len(candidate["evidence"]),
        "changed_files": candidate["changed_files"],
    }
