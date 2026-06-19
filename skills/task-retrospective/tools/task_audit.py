#!/usr/bin/env python3
"""task_audit.py — lightweight evidence recorder for armed task-retrospective.

This tool records project-learning evidence only. It does not decide or write
persistent memory/SOP/skill updates; the task-retrospective skill and write-gate
own those decisions.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

_SHARED = Path(__file__).resolve().parents[2] / "_shared"
if str(_SHARED) not in sys.path:
    sys.path.insert(0, str(_SHARED))

from audit_paths import PathConfinementError, safe_resolve_under  # noqa: E402
from audit_redact import redact, redact_obj  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[3]
STORE_REL = Path(".brainer") / "task-retrospective"
SCHEMA_VERSION = 1
EVENT_TYPES = {
    "correction",
    "failure",
    "success",
    "decision",
    "evidence",
    "candidate_lesson",
}


class AuditError(Exception):
    pass


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def slugify(text: str, fallback: str = "task") -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    slug = re.sub(r"-+", "-", slug)
    return (slug or fallback)[:48].strip("-") or fallback


def is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.resolve().relative_to(parent.resolve())
        return True
    except ValueError:
        return False


def repo_root_from_args(args: argparse.Namespace) -> Path:
    return Path(args.root).expanduser().resolve()


def store_dir(root: Path) -> Path:
    return root / STORE_REL


def current_path(root: Path) -> Path:
    return store_dir(root) / "current.json"


def sessions_dir(root: Path) -> Path:
    return store_dir(root) / "sessions"


def ensure_write_allowed(root: Path) -> None:
    """Refuse canonical checkout writes during no-write checks, allow temp fixtures."""
    if os.environ.get("BRAINER_CHECK_NO_WRITE") == "1" and is_relative_to(root, REPO_ROOT):
        raise AuditError(
            "BRAINER_CHECK_NO_WRITE=1: refusing to write task-retrospective state "
            f"inside canonical Brainer checkout ({root})"
        )


# Marker keys that hold filesystem paths the tool round-trips on later reads.
# These must NOT be redacted (masking a /Users/<name>/ component would break the
# path); confinement, not redaction, protects them.
_PATH_KEYS = {"events_path", "report_path", "json_report_path", "project_path"}


def redact_marker(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Redact every string leaf of a marker EXCEPT round-tripped path fields.

    Covers start metadata (task, goal, constraints, repeat_trigger,
    definition_of_done) and any nested string. Path fields are left structurally
    intact so subsequent reads still resolve; they are guarded by confinement.
    """
    out: Dict[str, Any] = {}
    for key, value in payload.items():
        out[key] = value if key in _PATH_KEYS else redact_obj(value)
    return out


def atomic_write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(redact_marker(payload), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    tmp.replace(path)


def append_jsonl(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        # Final redaction gate: scrub every string leaf before the event is written.
        fh.write(json.dumps(redact_obj(payload), sort_keys=True) + "\n")


def load_json(path: Path) -> Dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise AuditError(f"malformed {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise AuditError(f"malformed {path}: expected JSON object")
    return data


def confined(root: Path, raw: Any, field: str) -> Path:
    """Resolve a marker-derived path and confine it under the task-retro store.

    A tampered marker could redirect events/report writes outside
    ``.brainer/task-retrospective``; every such path is gated here before use.
    """
    try:
        return safe_resolve_under(store_dir(root), raw)
    except PathConfinementError as exc:
        raise AuditError(f"marker {field} escapes task-retrospective store: {exc}") from exc


def load_current(root: Path) -> Dict[str, Any]:
    path = current_path(root)
    if not path.exists():
        raise AuditError("task-retrospective is not armed; run `task_audit.py start ...` first")
    data = load_json(path)
    # Confine every marker-derived path before any read/write uses it.
    for field in ("events_path", "report_path"):
        if data.get(field):
            confined(root, data[field], field)
    return data


def event_path(session: Dict[str, Any]) -> Path:
    return Path(session["events_path"])


def report_path(session: Dict[str, Any]) -> Path:
    return Path(session["report_path"])


def git_value(root: Path, *cmd: str) -> str:
    try:
        proc = subprocess.run(
            ["git", *cmd],
            cwd=str(root),
            text=True,
            capture_output=True,
            timeout=3,
        )
    except Exception:
        return ""
    if proc.returncode != 0:
        return ""
    return proc.stdout.strip()


def read_events(path: Path) -> List[Dict[str, Any]]:
    events: List[Dict[str, Any]] = []
    if not path.exists():
        return events
    for lineno, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not raw.strip():
            continue
        try:
            obj = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise AuditError(f"malformed {path}:{lineno}: {exc}") from exc
        if isinstance(obj, dict):
            events.append(obj)
    return events


def session_summary(session: Dict[str, Any], active: bool, event_count: int) -> Dict[str, Any]:
    return {
        "active": active,
        "mode": "task-retrospective",
        "task_id": session.get("task_id"),
        "task": session.get("task"),
        "repeat_trigger": session.get("repeat_trigger"),
        "project_path": session.get("project_path"),
        "events_path": session.get("events_path"),
        "report_path": session.get("report_path"),
        "event_count": event_count,
    }


def make_event(kind: str, **fields: Any) -> Dict[str, Any]:
    event = {
        "schema_version": SCHEMA_VERSION,
        "mode": "task-retrospective",
        "timestamp": utc_now(),
        "type": kind,
    }
    for key, value in fields.items():
        if value is None:
            continue
        event[key] = redact(str(value)) if key in {"text", "implication", "evidence_ref"} else value
    return event


def command_start(args: argparse.Namespace) -> int:
    root = repo_root_from_args(args)
    ensure_write_allowed(root)
    cur = current_path(root)
    if cur.exists() and not args.force:
        raise AuditError(f"task-retrospective already armed at {cur}; finish it or pass --force")

    task_id = args.task_id or f"{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}-{slugify(args.task)}"
    sdir = sessions_dir(root) / task_id
    events = sdir / "events.jsonl"
    report = sdir / "report.md"
    branch = args.branch or git_value(root, "branch", "--show-current")
    start_commit = args.start_commit or git_value(root, "rev-parse", "HEAD")
    session = {
        "schema_version": SCHEMA_VERSION,
        "mode": "task-retrospective",
        "status": "armed",
        "task_id": task_id,
        "task": args.task,
        "goal": args.goal or "",
        "repeat_trigger": args.repeat_trigger,
        "definition_of_done": args.definition_of_done or "",
        "constraints": args.constraint or [],
        "project_path": str(root),
        "branch": branch,
        "start_commit": start_commit,
        "after_the_fact": bool(args.after_the_fact),
        "started_at": utc_now(),
        "events_path": str(events),
        "report_path": str(report),
    }
    sdir.mkdir(parents=True, exist_ok=True)
    if args.force and events.exists():
        events.unlink()
    append_jsonl(events, make_event("start", task=args.task, repeat_trigger=args.repeat_trigger))
    atomic_write_json(cur, session)
    print(json.dumps(redact_marker(session_summary(session, True, 1)), indent=2, sort_keys=True))
    return 0


def command_note(args: argparse.Namespace) -> int:
    root = repo_root_from_args(args)
    ensure_write_allowed(root)
    session = load_current(root)
    event = make_event(
        args.type,
        task_id=session.get("task_id"),
        text=args.text,
        implication=args.implication,
        evidence_ref=args.evidence_ref,
    )
    append_jsonl(confined(root, session["events_path"], "events_path"), event)
    # Redact the echoed event the same way it was written to disk.
    print(json.dumps({"ok": True, "event": redact_obj(event)}, indent=2, sort_keys=True))
    return 0


def command_status(args: argparse.Namespace) -> int:
    root = repo_root_from_args(args)
    cur = current_path(root)
    if not cur.exists():
        print(json.dumps({"active": False, "mode": "task-retrospective"}, indent=2, sort_keys=True))
        return 0
    session = load_json(cur)
    events = read_events(confined(root, session["events_path"], "events_path"))
    print(json.dumps(redact_marker(session_summary(session, True, len(events))), indent=2, sort_keys=True))
    return 0


def bullet_events(events: Iterable[Dict[str, Any]], kind: str) -> List[str]:
    out = []
    for event in events:
        if event.get("type") != kind:
            continue
        text = event.get("text") or event.get("task") or ""
        if text:
            out.append(f"- {text}")
    return out


def infer_evidence_quality(events: List[Dict[str, Any]], explicit: str) -> str:
    if explicit:
        return explicit
    event_types = {event.get("type") for event in events}
    substantive = event_types - {"start", "finish"}
    if {"evidence", "success"} & event_types:
        return "high"
    if substantive:
        return "medium"
    return "low"


def render_report(session: Dict[str, Any], events: List[Dict[str, Any]], evidence_quality: str) -> str:
    corrections = bullet_events(events, "correction") or ["- None recorded."]
    failures = bullet_events(events, "failure") or ["- None recorded."]
    successes = bullet_events(events, "success") or ["- None recorded."]
    evidence = bullet_events(events, "evidence") or ["- No verification evidence recorded by the tool."]
    candidates = bullet_events(events, "candidate_lesson") or ["- No durable project lesson nominated by the tool."]
    decisions = bullet_events(events, "decision") or ["- None recorded."]

    missing = []
    if evidence == ["- No verification evidence recorded by the tool."]:
        missing.append("verification evidence")
    if not session.get("definition_of_done"):
        missing.append("definition of done")
    if not session.get("goal"):
        missing.append("task goal")
    missing_line = ", ".join(missing) if missing else "None obvious from recorded events."

    def section(lines: List[str]) -> str:
        return "\n".join(lines)

    return f"""# Task-retrospective report

## Task
- Goal: {session.get('goal') or '(not recorded)'}
- Task: {session.get('task') or '(not recorded)'}
- Future trigger: {session.get('repeat_trigger') or '(not recorded)'}
- Definition of done: {session.get('definition_of_done') or '(not recorded)'}
- Evidence quality: {evidence_quality}
- Mode: {'retrospective reconstruction' if session.get('after_the_fact') else 'armed before/during task'}

## What happened
- Project path: `{session.get('project_path')}`
- Branch: `{session.get('branch') or 'unknown'}`
- Start commit: `{session.get('start_commit') or 'unknown'}`
- Events recorded: {len(events)}

## Verification evidence
{section(evidence)}

## User corrections
{section(corrections)}

## Failures
{section(failures)}

## Successful tactics
{section(successes)}

## Decisions
{section(decisions)}

## Reusable learnings
{section(candidates)}

## Project updates
- None written by `task_audit.py`.
- Route any accepted durable lesson through task-retrospective's target ladder and write-gate.
- Read back any durable update before claiming it persisted.

## Rejected learnings
- Not evaluated by this evidence recorder. Decide during the task-retrospective review.

## Remaining risks
- Missing evidence: {missing_line}
- This report is scaffolding, not proof that a lesson deserves persistence.
"""


def command_finish(args: argparse.Namespace) -> int:
    root = repo_root_from_args(args)
    ensure_write_allowed(root)
    session = load_current(root)
    events_p = confined(root, session["events_path"], "events_path")
    finish_event = make_event("finish", task_id=session.get("task_id"))
    append_jsonl(events_p, finish_event)
    events = read_events(events_p)
    evidence_quality = infer_evidence_quality(events, args.evidence_quality or "")

    wrote_report = False
    if args.report:
        # session came from a redacted marker, but redact the rendered report
        # again so no secret can leak via interpolated metadata.
        text = redact(render_report(session, events, evidence_quality))
        path = confined(root, session["report_path"], "report_path")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        wrote_report = True

    current_path(root).unlink(missing_ok=True)
    result = session_summary(session, False, len(events))
    result.update({"finished": True, "report_written": wrote_report, "evidence_quality": evidence_quality})
    print(json.dumps(redact_marker(result), indent=2, sort_keys=True))
    return 0


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="task_audit.py", description=__doc__)
    ap.add_argument("--root", default=os.getcwd(), help="Project root that owns .brainer/task-retrospective")
    sub = ap.add_subparsers(dest="cmd", required=True)

    start = sub.add_parser("start", help="Arm task-retrospective evidence capture")
    start.add_argument("--task", required=True)
    start.add_argument("--repeat-trigger", required=True)
    start.add_argument("--goal", default="")
    start.add_argument("--definition-of-done", default="")
    start.add_argument("--constraint", action="append", default=[])
    start.add_argument("--branch", default="")
    start.add_argument("--start-commit", default="")
    start.add_argument("--task-id", default="", help="Optional deterministic session id for tests/imports")
    start.add_argument("--after-the-fact", action="store_true")
    start.add_argument("--force", action="store_true", help="Replace an existing active marker")
    start.set_defaults(func=command_start)

    note = sub.add_parser("note", help="Append an evidence note to the armed session")
    note.add_argument("--type", required=True, choices=sorted(EVENT_TYPES))
    note.add_argument("--text", required=True)
    note.add_argument("--implication", default="")
    note.add_argument("--evidence-ref", default="")
    note.set_defaults(func=command_note)

    status = sub.add_parser("status", help="Show current armed/unarmed state")
    status.set_defaults(func=command_status)

    finish = sub.add_parser("finish", help="Close the armed session")
    finish.add_argument("--report", action="store_true", help="Write report.md before closing")
    finish.add_argument("--evidence-quality", choices=["high", "medium", "low"], default="")
    finish.set_defaults(func=command_finish)
    return ap


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.func(args))
    except AuditError as exc:
        print(f"task_audit.py: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
