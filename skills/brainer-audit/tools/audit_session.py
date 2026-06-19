#!/usr/bin/env python3
"""Start/status/finish markers for opt-in Brainer audit live collection."""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))
_SHARED = Path(__file__).resolve().parents[2] / "_shared"
if str(_SHARED) not in sys.path:
    sys.path.insert(0, str(_SHARED))

from audit_paths import PathConfinementError, safe_resolve_under  # noqa: E402
from detectors import load_events, run_detectors  # noqa: E402
from report import build_json_report, build_markdown_report, dump_json  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[3]
STORE_REL = Path(".brainer") / "brainer-audit"


class AuditSessionError(Exception):
    pass


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def slugify(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return (slug or "session")[:48]


def is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.resolve().relative_to(parent.resolve())
        return True
    except ValueError:
        return False


def ensure_write_allowed(root: Path) -> None:
    if os.environ.get("BRAINER_CHECK_NO_WRITE") == "1" and is_relative_to(root, REPO_ROOT):
        raise AuditSessionError(f"BRAINER_CHECK_NO_WRITE=1: refusing to write Brainer audit state inside {REPO_ROOT}")


def store(root: Path) -> Path:
    return root / STORE_REL


def current_path(root: Path) -> Path:
    return store(root) / "current.json"


def sessions(root: Path) -> Path:
    return store(root) / "sessions"


def atomic_write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    tmp.replace(path)


def confined(root: Path, raw: Any, field: str) -> Path:
    """Resolve a marker-derived path and confine it under the audit store root.

    A tampered marker could point events/report paths outside
    ``.brainer/brainer-audit``; every such path is gated here before use.
    """
    try:
        return safe_resolve_under(store(root), raw)
    except PathConfinementError as exc:
        raise AuditSessionError(f"marker {field} escapes audit store: {exc}") from exc


def load_current(root: Path) -> Dict[str, Any]:
    path = current_path(root)
    if not path.exists():
        raise AuditSessionError("brainer-audit is not active; run `audit_session.py start ...` first")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise AuditSessionError(f"malformed {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise AuditSessionError(f"malformed {path}: expected JSON object")
    # Confine every marker-derived path before any read/write uses it.
    for field in ("events_path", "report_path", "json_report_path"):
        if data.get(field):
            confined(root, data[field], field)
    return data


def event_count(path: Path) -> int:
    if not path.exists():
        return 0
    return sum(1 for line in path.read_text(encoding="utf-8").splitlines() if line.strip())


def summary(session: Dict[str, Any], active: bool) -> Dict[str, Any]:
    events_path = Path(session["events_path"])
    return {
        "active": active,
        "mode": "brainer-audit",
        "session_id": session.get("session_id"),
        "title": session.get("title"),
        "events_path": str(events_path),
        "report_path": session.get("report_path"),
        "json_report_path": session.get("json_report_path"),
        "event_count": event_count(events_path),
    }


def command_start(args: argparse.Namespace) -> int:
    root = Path(args.root).expanduser().resolve()
    ensure_write_allowed(root)
    cur = current_path(root)
    if cur.exists() and not args.force:
        raise AuditSessionError(f"brainer-audit already active at {cur}; finish it or pass --force")
    sid = args.session_id or f"{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}-{slugify(args.title)}"
    sdir = sessions(root) / sid
    session = {
        "schema_version": 1,
        "mode": "brainer-audit",
        "status": "active",
        "session_id": sid,
        "title": args.title,
        "host": args.host,
        "project_path": str(root),
        "started_at": utc_now(),
        "events_path": str(sdir / "events.jsonl"),
        "report_path": str(sdir / "report.md"),
        "json_report_path": str(sdir / "report.json"),
    }
    sdir.mkdir(parents=True, exist_ok=True)
    if args.force:
        Path(session["events_path"]).unlink(missing_ok=True)
    atomic_write_json(cur, session)
    print(json.dumps(summary(session, True), indent=2, sort_keys=True))
    return 0


def command_status(args: argparse.Namespace) -> int:
    root = Path(args.root).expanduser().resolve()
    cur = current_path(root)
    if not cur.exists():
        print(json.dumps({"active": False, "mode": "brainer-audit"}, indent=2, sort_keys=True))
        return 0
    print(json.dumps(summary(load_current(root), True), indent=2, sort_keys=True))
    return 0


def command_finish(args: argparse.Namespace) -> int:
    root = Path(args.root).expanduser().resolve()
    ensure_write_allowed(root)
    session = load_current(root)
    events_path = confined(root, session["events_path"], "events_path")
    events = load_events(events_path) if events_path.exists() else []
    findings = run_detectors(events)
    wrote_report = False
    if args.report:
        report_p = confined(root, session["report_path"], "report_path")
        json_report_p = confined(root, session["json_report_path"], "json_report_path")
        report_p.parent.mkdir(parents=True, exist_ok=True)
        report_p.write_text(build_markdown_report(events, findings), encoding="utf-8")
        json_report_p.parent.mkdir(parents=True, exist_ok=True)
        json_report_p.write_text(dump_json(build_json_report(events, findings)), encoding="utf-8")
        wrote_report = True
    current_path(root).unlink(missing_ok=True)
    out = summary(session, False)
    out.update({"finished": True, "report_written": wrote_report, "finding_count": len(findings)})
    print(json.dumps(out, indent=2, sort_keys=True))
    return 1 if any(f.severity == "error" for f in findings) else 0


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="audit_session.py", description=__doc__)
    ap.add_argument("--root", default=os.getcwd())
    sub = ap.add_subparsers(dest="cmd", required=True)
    start = sub.add_parser("start")
    start.add_argument("--title", required=True)
    start.add_argument("--host", default="unknown")
    start.add_argument("--session-id", default="")
    start.add_argument("--force", action="store_true")
    start.set_defaults(func=command_start)
    status = sub.add_parser("status")
    status.set_defaults(func=command_status)
    finish = sub.add_parser("finish")
    finish.add_argument("--report", action="store_true")
    finish.set_defaults(func=command_finish)
    return ap


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return int(args.func(args))
    except (AuditSessionError, OSError, ValueError) as exc:
        print(f"audit_session.py: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
