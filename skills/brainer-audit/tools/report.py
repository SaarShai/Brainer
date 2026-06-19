#!/usr/bin/env python3
"""Stable JSON/markdown reports for brainer-audit."""
from __future__ import annotations

import json
from typing import Any, Dict, List, Sequence

from detectors import Finding


def _event_source(event: Dict[str, Any]) -> str:
    """Classify a single event by how it was collected.

    - ``sidecar``: best-effort Antigravity sidecar snapshot (lower fidelity).
    - ``live-hook``: emitted by a host hook adapter (normalize.py sets
      ``hook_event_name``; hook sessions default ``session_id`` to ``hook``).
    - ``offline``: hand-ingested fixture (ingest_event.py), no live provenance.
    """
    if event.get("collector") == "antigravity_sidecar" or event.get("evidence_fidelity") == "lower-sidecar":
        return "sidecar"
    if event.get("hook_event_name") or event.get("session_id") == "hook":
        return "live-hook"
    return "offline"


def derive_audit_mode(events: Sequence[Dict[str, Any]]) -> str:
    """Derive the audit mode from the ACTUAL collection sources present.

    Returns one of ``offline``, ``live-hook``, ``sidecar``, ``mixed``, or
    ``offline-report-only`` when there are no events to classify.
    """
    if not events:
        return "offline-report-only"
    sources = {_event_source(event) for event in events}
    if len(sources) == 1:
        return next(iter(sources))
    return "mixed"


def session_summary(events: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    first = events[0] if events else {}
    hosts = sorted({str(e.get("host")) for e in events if e.get("host")})
    projects = sorted({str(e.get("project_path")) for e in events if e.get("project_path")})
    sessions = sorted({str(e.get("session_id")) for e in events if e.get("session_id")})
    event_types: Dict[str, int] = {}
    for event in events:
        kind = str(event.get("event") or "unknown")
        event_types[kind] = event_types.get(kind, 0) + 1
    return {
        "audit_mode": derive_audit_mode(events),
        "schema_version": 1,
        "host": ", ".join(hosts) or str(first.get("host") or "unknown"),
        "project": ", ".join(projects) or str(first.get("project_path") or "unknown"),
        "session": ", ".join(sessions) or str(first.get("session_id") or "unknown"),
        "event_count": len(events),
        "event_types": dict(sorted(event_types.items())),
        "evidence_quality": "high" if len(events) >= 5 else ("medium" if events else "low"),
    }


def build_json_report(events: Sequence[Dict[str, Any]], findings: Sequence[Finding]) -> Dict[str, Any]:
    counts: Dict[str, int] = {}
    for finding in findings:
        counts[finding.severity] = counts.get(finding.severity, 0) + 1
    return {
        "schema_version": 1,
        "mode": "brainer-audit",
        "summary": session_summary(events),
        "finding_counts": dict(sorted(counts.items())),
        "findings": [finding.to_dict() for finding in findings],
    }


def _table(findings: Sequence[Finding]) -> str:
    rows = ["| Skill | Finding | Observed | Severity |", "|---|---|---|---|"]
    if not findings:
        rows.append("| — | No findings. | — | info |")
    for finding in findings:
        observed = (finding.observed or "").replace("|", "\\|").replace("\n", " ")[:120]
        rows.append(f"| {finding.skill or '—'} | {finding.title} | {observed} | {finding.severity} |")
    return "\n".join(rows)


def build_markdown_report(events: Sequence[Dict[str, Any]], findings: Sequence[Finding]) -> str:
    summary = session_summary(events)
    lines: List[str] = [
        "# Brainer audit report",
        "",
        "## Session summary",
        f"- Host: {summary['host']}",
        f"- Project: {summary['project']}",
        f"- Session: {summary['session']}",
        f"- Audit mode: {summary['audit_mode']}",
        f"- Evidence quality: {summary['evidence_quality']}",
        f"- Events: {summary['event_count']}",
        "",
        "## Skill trigger opportunities",
        _table(findings),
        "",
        "## Findings",
    ]
    if findings:
        for finding in findings:
            lines.extend([
                f"- **{finding.title}** ({finding.severity}, {finding.detector})",
                f"  - Expected: {finding.expected}",
                f"  - Evidence: {', '.join(finding.event_refs)}",
            ])
    else:
        lines.append("- No findings.")

    lines.extend(["", "## Candidate Brainer improvements"])
    if findings:
        for idx, finding in enumerate(findings, 1):
            lines.extend([
                f"{idx}. Change: investigate `{finding.detector}` finding.",
                f"   Evidence: {', '.join(finding.event_refs)}",
                f"   Target skill/tool/test: {finding.suggested_target or finding.skill or 'unknown'}",
                f"   Suggested PR scope: {finding.suggested_pr_scope or 'add or tune a deterministic fixture'}",
            ])
    else:
        lines.append("1. No candidate Brainer improvement from this fixture.")

    lines.extend(["", "## Evidence appendix"])
    for event in events:
        ref = event.get("_ref") or event.get("turn_id") or event.get("timestamp") or "event"
        kind = event.get("event", "unknown")
        text = str(event.get("content_summary") or event.get("command") or event.get("path") or "")[:160]
        fidelity = event.get("evidence_fidelity")
        suffix = f" [{fidelity}]" if fidelity else ""
        lines.append(f"- {ref}: {kind}{suffix} — {text}")

    lines.extend(["", "## Remaining risks"])
    lines.append(
        f"- Collection source for this run: {summary['audit_mode']}. "
        "Offline fixtures and sidecar snapshots are lower fidelity than live host hooks."
    )
    lines.append("- This report is advisory and does not apply canonical Brainer edits.")
    return "\n".join(lines) + "\n"


def dump_json(report: Dict[str, Any]) -> str:
    return json.dumps(report, indent=2, sort_keys=True) + "\n"
