#!/usr/bin/env python3
"""Best-effort Antigravity sidecar evidence helpers.

This module does not assume native Antigravity hooks. It records lower-fidelity
signals from git state and optional artifact/log folders supplied by the user or
found locally.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Sequence

_SHARED = Path(__file__).resolve().parents[2] / "_shared"
if str(_SHARED) not in sys.path:
    sys.path.insert(0, str(_SHARED))

from audit_redact import redact, redact_obj  # noqa: E402

SCHEMA_VERSION = 1
TEXT_SUFFIXES = {".txt", ".md", ".json", ".jsonl", ".log", ".yaml", ".yml"}
KNOWN_DIRS = [
    ".antigravity",
    ".google-antigravity",
    "antigravity-artifacts",
    "artifacts",
    "logs",
]


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def run_git(root: Path, args: Sequence[str]) -> str:
    try:
        proc = subprocess.run(["git", *args], cwd=str(root), text=True, capture_output=True, timeout=5)
    except Exception:
        return ""
    if proc.returncode != 0:
        return ""
    return redact(proc.stdout.strip())


def base_event(root: Path, session_id: str, kind: str) -> Dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "mode": "brainer-audit",
        "session_id": session_id,
        "turn_id": "",
        "host": "antigravity",
        "project_path": str(root),
        "event": kind,
        "timestamp": utc_now(),
        "evidence_fidelity": "lower-sidecar",
        "collector": "antigravity_sidecar",
    }


def git_events(root: Path, session_id: str) -> List[Dict[str, Any]]:
    status = run_git(root, ["status", "--short"])
    diff_names = run_git(root, ["diff", "--name-status"])
    events: List[Dict[str, Any]] = []
    if status or diff_names:
        ev = base_event(root, session_id, "git_snapshot")
        ev.update({
            "content_summary": f"git status --short:\n{status or '(clean)'}\n\ngit diff --name-status:\n{diff_names or '(no unstaged diff)'}",
            "command": "git status --short && git diff --name-status",
        })
        events.append(ev)
    for raw in diff_names.splitlines():
        parts = raw.split("\t")
        if not parts:
            continue
        path = parts[-1]
        ev = base_event(root, session_id, "file_change")
        ev.update({"path": path, "content_summary": raw})
        events.append(ev)
    return events


def discover_artifact_dirs(root: Path, supplied: Iterable[str]) -> List[Path]:
    dirs: List[Path] = []
    for raw in supplied:
        if not raw:
            continue
        path = Path(raw).expanduser()
        if not path.is_absolute():
            path = root / path
        if path.exists() and path.is_dir():
            dirs.append(path.resolve())
    for rel in KNOWN_DIRS:
        path = root / rel
        if path.exists() and path.is_dir():
            dirs.append(path.resolve())
    # preserve order while deduping
    seen = set()
    out: List[Path] = []
    for path in dirs:
        if path in seen:
            continue
        seen.add(path)
        out.append(path)
    return out


def safe_preview(path: Path, include_content: bool, limit: int = 500) -> str:
    if not include_content or path.suffix.lower() not in TEXT_SUFFIXES:
        return ""
    try:
        data = path.read_text(encoding="utf-8", errors="replace")[:limit]
    except OSError:
        return ""
    return redact(data)


def artifact_events(root: Path, session_id: str, artifact_dirs: Iterable[str], *, max_files: int = 50, include_content: bool = False) -> List[Dict[str, Any]]:
    dirs = discover_artifact_dirs(root, artifact_dirs)
    events: List[Dict[str, Any]] = []
    if not dirs:
        ev = base_event(root, session_id, "session_end")
        ev.update({"content_summary": "No Antigravity artifact/log directories found or supplied; sidecar evidence is git-only."})
        return [ev]
    count = 0
    for directory in dirs:
        for path in sorted(p for p in directory.rglob("*") if p.is_file()):
            if count >= max_files:
                break
            try:
                stat = path.stat()
            except OSError:
                continue
            rel = str(path.relative_to(root)) if path.is_relative_to(root) else str(path)
            preview = safe_preview(path, include_content)
            ev = base_event(root, session_id, "file_change")
            ev.update({
                "path": rel,
                "raw_ref": str(path),
                "content_summary": preview or f"Antigravity sidecar artifact: {rel} ({stat.st_size} bytes)",
                "artifact_kind": "antigravity-sidecar",
                "bytes": stat.st_size,
            })
            events.append(ev)
            count += 1
        if count >= max_files:
            break
    if not events:
        ev = base_event(root, session_id, "session_end")
        ev.update({"content_summary": "Antigravity artifact/log directories exist but contain no files."})
        events.append(ev)
    return events


def build_sidecar_events(root: Path, session_id: str, artifact_dirs: Iterable[str], *, max_files: int = 50, include_content: bool = False) -> List[Dict[str, Any]]:
    return [
        *git_events(root, session_id),
        *artifact_events(root, session_id, artifact_dirs, max_files=max_files, include_content=include_content),
    ]


def append_jsonl(path: Path, events: Iterable[Dict[str, Any]]) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with path.open("a", encoding="utf-8") as fh:
        for event in events:
            # Final redaction gate: scrub every string leaf (content previews,
            # artifact paths, raw_ref) before it hits disk.
            fh.write(json.dumps(redact_obj(event), sort_keys=True) + "\n")
            count += 1
    return count
