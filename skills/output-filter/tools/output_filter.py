from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from config import load_config


ANSI = re.compile(r"\x1b(?:\[[0-?]*[ -/]*[@-~]|\][^\x07\x1b]*(?:\x07|\x1b\\)|[@-Z\\-_])")
DEFAULT_KEEP = re.compile(r"(error|fail|fatal|traceback|exception)", re.I)
DEFAULT_COLLAPSE = [re.compile(r"\r"), re.compile(r"\d+%\s*$")]
SEARCH_LINE_RE = re.compile(r"^[^:\n]{1,220}:\d+(?::|-)")
DIFF_LINE_RE = re.compile(r"^(?:diff --git|index |--- |\+\+\+ |@@ )")
LOG_KEEP_RE = re.compile(
    r"(?:error|fail|fatal|traceback|exception|warning|warn|"
    r"\bpassed\b|\bfailed\b|\berrors?\b|collected|summary|"
    r"^=+|^-{3,}|^\s*File \".+\", line \d+)",
    re.I,
)
CONTENT_TYPES = ("auto", "plain", "search", "log", "diff")


@dataclass
class FilterRules:
    keep: list[re.Pattern[str]]
    drop: list[re.Pattern[str]]
    collapse: list[re.Pattern[str]]


def _compile(pattern: str) -> re.Pattern[str] | None:
    try:
        return re.compile(pattern)
    except re.error:
        return None


def load_rules(path: Path | None) -> FilterRules:
    rules = FilterRules(keep=[DEFAULT_KEEP], drop=[], collapse=list(DEFAULT_COLLAPSE))
    if not path or not path.exists():
        return rules
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or ":" not in line:
            continue
        kind, pattern = line.split(":", 1)
        compiled = _compile(pattern.strip())
        if not compiled:
            continue
        kind = kind.strip().lower()
        if kind in {"keep", "preserve"}:
            rules.keep.append(compiled)
        elif kind == "drop":
            rules.drop.append(compiled)
        elif kind == "collapse":
            rules.collapse.append(compiled)
    return rules


def _matches(patterns: list[re.Pattern[str]], line: str) -> bool:
    return any(pattern.search(line) for pattern in patterns)


def _session_id() -> str:
    raw = os.environ.get("TOKEN_ECONOMY_SESSION_ID") or os.environ.get("CLAUDE_CODE_SESSION_ID") or "default"
    return re.sub(r"[^A-Za-z0-9_.-]+", "-", raw)[:80] or "default"


def _now_id() -> tuple[str, str]:
    now = datetime.now(timezone.utc)
    stamp = now.strftime("%Y%m%dT%H%M%S.%fZ")
    return stamp, now.isoformat()


def _state_dir(repo_root: Path) -> Path:
    return repo_root / ".brainer" / "output-filter"


def _resolve_rewind_raw_path(repo_root: Path, raw_path: str) -> Path:
    """Resolve an archived raw output path without trusting index.jsonl blindly.

    Archive entries are metadata, not authority. A tampered `raw_path` must not
    allow rewind to read arbitrary files outside `.brainer/output-filter/raw`.
    Resolving the candidate also rejects symlink escapes from that archive root.
    """
    archive_raw_root = (_state_dir(repo_root) / "raw").resolve()
    raw_ref = Path(raw_path).expanduser()
    candidate = raw_ref if raw_ref.is_absolute() else repo_root / raw_ref
    resolved = candidate.resolve()
    try:
        resolved.relative_to(archive_raw_root)
    except ValueError as exc:
        raise SystemExit(f"unsafe output-filter raw_path outside archive root: {raw_path}") from exc
    if not resolved.is_file():
        raise SystemExit(f"output-filter raw archive is not a file: {raw_path}")
    return resolved


def _line_hash(line: str) -> str:
    return hashlib.sha256(line.encode("utf-8", errors="replace")).hexdigest()


def _load_seen(path: Path) -> set[str]:
    if not path.exists():
        return set()
    return set(path.read_text(encoding="utf-8", errors="replace").splitlines())


def _save_seen(path: Path, seen: set[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(sorted(seen)) + ("\n" if seen else ""), encoding="utf-8")


def _token_estimate(text: str) -> int:
    return max(1, len(text) // 4) if text else 0


def detect_content_type(text: str) -> str:
    lines = text.splitlines()
    if not lines:
        return "plain"
    sample = lines[:400]
    if any(DIFF_LINE_RE.search(line) for line in sample) and any(line.startswith("@@ ") for line in sample):
        return "diff"
    search_hits = sum(1 for line in sample if SEARCH_LINE_RE.match(line))
    if search_hits >= 12 and search_hits / max(len(sample), 1) >= 0.45:
        return "search"
    if len(lines) >= 120 and sum(1 for line in sample if LOG_KEEP_RE.search(line)) >= 3:
        return "log"
    return "plain"


def _ordered_keep(lines: list[str], keep_indexes: set[int], note: str) -> list[str]:
    if not keep_indexes or len(keep_indexes) >= len(lines):
        return lines
    kept = [line for i, line in enumerate(lines) if i in keep_indexes]
    return [note, *kept]


def _compress_search(text: str) -> tuple[str, dict[str, Any]]:
    lines = text.splitlines()
    match_indexes = [i for i, line in enumerate(lines) if SEARCH_LINE_RE.match(line)]
    if len(match_indexes) <= 80:
        return text, {"content_lines_removed": 0, "transforms": []}
    keep: set[int] = set(match_indexes[:12]) | set(match_indexes[-12:])
    seen_files: set[str] = set()
    for i in match_indexes:
        file_name = lines[i].split(":", 1)[0]
        if file_name not in seen_files:
            seen_files.add(file_name)
            keep.add(i)
        if len(seen_files) >= 40:
            break
    for i, line in enumerate(lines):
        if DEFAULT_KEEP.search(line):
            keep.add(i)
    note = f"[output-filter: search results compressed; kept {len(keep)}/{len(lines)} lines across {len(seen_files)} files]"
    kept = _ordered_keep(lines, keep, note)
    if len(kept) >= len(lines):
        return text, {"content_lines_removed": 0, "transforms": []}
    return "\n".join(kept) + "\n", {"content_lines_removed": len(lines) - len(kept), "transforms": ["search-summary"]}


def _compress_log(text: str) -> tuple[str, dict[str, Any]]:
    lines = text.splitlines()
    if len(lines) <= 220:
        return text, {"content_lines_removed": 0, "transforms": []}
    keep: set[int] = set(range(min(20, len(lines)))) | set(range(max(0, len(lines) - 50), len(lines)))
    for i, line in enumerate(lines):
        if LOG_KEEP_RE.search(line):
            keep.add(i)
    note = f"[output-filter: log compressed; kept {len(keep)}/{len(lines)} signal lines]"
    kept = _ordered_keep(lines, keep, note)
    if len(kept) >= len(lines):
        return text, {"content_lines_removed": 0, "transforms": []}
    return "\n".join(kept) + "\n", {"content_lines_removed": len(lines) - len(kept), "transforms": ["log-summary"]}


def _compress_diff(text: str) -> tuple[str, dict[str, Any]]:
    lines = text.splitlines()
    if len(lines) <= 300:
        return text, {"content_lines_removed": 0, "transforms": []}
    keep: set[int] = set()
    for i, line in enumerate(lines):
        if DIFF_LINE_RE.search(line) or line.startswith(("+", "-")):
            keep.add(i)
    note = f"[output-filter: diff compressed; kept {len(keep)}/{len(lines)} headers and changed lines]"
    kept = _ordered_keep(lines, keep, note)
    if len(kept) >= len(lines) or len("\n".join(kept)) >= len(text):
        return text, {"content_lines_removed": 0, "transforms": []}
    return "\n".join(kept) + "\n", {"content_lines_removed": len(lines) - len(kept), "transforms": ["diff-hunks"]}


def _compress_content(text: str, content_type: str) -> tuple[str, dict[str, Any]]:
    detected = detect_content_type(text) if content_type == "auto" else content_type
    if detected == "search":
        out, meta = _compress_search(text)
    elif detected == "log":
        out, meta = _compress_log(text)
    elif detected == "diff":
        out, meta = _compress_diff(text)
    else:
        out, meta = text, {"content_lines_removed": 0, "transforms": []}
    meta["content_type"] = detected
    return out, meta


def filter_text(
    text: str,
    *,
    rules: FilterRules,
    session_aware: bool = False,
    seen_path: Path | None = None,
    content_type: str = "auto",
) -> tuple[str, dict[str, Any]]:
    prev: str | None = None
    repeat = 0
    output: list[str] = []
    seen = _load_seen(seen_path) if session_aware and seen_path else set()
    stats = {
        "raw_lines": 0,
        "filtered_lines": 0,
        "deduped_lines": 0,
        "collapsed_lines": 0,
        "dropped_lines": 0,
        "session_suppressed_lines": 0,
        "raw_tokens_est": _token_estimate(text),
    }

    def flush_repeat() -> None:
        nonlocal repeat
        if repeat:
            output.append(f"[deduped {repeat} repeated lines]")
            stats["deduped_lines"] += repeat
            repeat = 0

    for raw in text.splitlines():
        stats["raw_lines"] += 1
        line = ANSI.sub("", raw)
        keep = _matches(rules.keep, line)
        if not keep and _matches(rules.collapse, line):
            stats["collapsed_lines"] += 1
            continue
        if not keep and _matches(rules.drop, line):
            stats["dropped_lines"] += 1
            continue
        if not keep and line == prev:
            repeat += 1
            continue
        line_digest = _line_hash(line)
        if not keep and session_aware and line_digest in seen:
            stats["session_suppressed_lines"] += 1
            continue
        flush_repeat()
        output.append(line)
        prev = line
        if session_aware:
            seen.add(line_digest)
    flush_repeat()
    if session_aware and seen_path:
        _save_seen(seen_path, seen)
    stats["filtered_lines"] = len(output)
    filtered = "\n".join(output) + ("\n" if output else "")
    try:
        filtered, content_stats = _compress_content(filtered, content_type)
    except Exception as exc:
        content_stats = {"content_type": "plain", "content_lines_removed": 0, "transforms": [], "content_filter_error": str(exc)}
    stats.update(content_stats)
    stats["filtered_tokens_est"] = _token_estimate(filtered)
    return filtered, stats


def archive_event(repo_root: Path, raw: str, filtered: str, stats: dict[str, Any], session_id: str) -> dict[str, Any]:
    event_id, timestamp = _now_id()
    root = _state_dir(repo_root)
    raw_dir = root / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    raw_path = raw_dir / f"{event_id}-{session_id}.txt"
    raw_path.write_text(raw, encoding="utf-8", errors="replace")
    record = {
        "id": f"{event_id}-{session_id}",
        "timestamp": timestamp,
        "session_id": session_id,
        "raw_path": str(raw_path.relative_to(repo_root)),
        "raw_chars": len(raw),
        "filtered_chars": len(filtered),
        "char_savings": 1 - (len(filtered) / max(len(raw), 1)),
        "recover_command": f"python3 skills/output-filter/tools/output_filter.py --repo {repo_root} rewind {event_id}-{session_id}",
        **stats,
    }
    index = root / "index.jsonl"
    with index.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, sort_keys=True) + "\n")
    return record


def read_index(repo_root: Path) -> list[dict[str, Any]]:
    index = _state_dir(repo_root) / "index.jsonl"
    if not index.exists():
        return []
    rows = []
    for line in index.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return rows


def stats(repo_root: Path, limit: int | None = None) -> dict[str, Any]:
    rows = read_index(repo_root)
    scoped = rows[-limit:] if limit else rows
    raw_chars = sum(int(row.get("raw_chars", 0)) for row in scoped)
    filtered_chars = sum(int(row.get("filtered_chars", 0)) for row in scoped)
    return {
        "events": len(scoped),
        "raw_chars": raw_chars,
        "filtered_chars": filtered_chars,
        "char_savings": 1 - filtered_chars / max(raw_chars, 1),
        "deduped_lines": sum(int(row.get("deduped_lines", 0)) for row in scoped),
        "collapsed_lines": sum(int(row.get("collapsed_lines", 0)) for row in scoped),
        "dropped_lines": sum(int(row.get("dropped_lines", 0)) for row in scoped),
        "session_suppressed_lines": sum(int(row.get("session_suppressed_lines", 0)) for row in scoped),
        "last_id": scoped[-1]["id"] if scoped else None,
    }


def rewind(repo_root: Path, event_id: str = "last", grep: str | None = None) -> str:
    rows = read_index(repo_root)
    if not rows:
        raise SystemExit("no output-filter archive entries")
    row = rows[-1] if event_id == "last" else next((item for item in rows if item.get("id") == event_id), None)
    if row is None:
        raise SystemExit(f"unknown output-filter event: {event_id}")
    raw_path = row.get("raw_path")
    if not isinstance(raw_path, str) or not raw_path.strip():
        raise SystemExit(f"output-filter event has no raw_path: {row.get('id', event_id)}")
    path = _resolve_rewind_raw_path(repo_root, raw_path)
    raw = path.read_text(encoding="utf-8", errors="replace")
    if not grep:
        return raw
    try:
        rx = re.compile(grep)
    except re.error as exc:
        raise SystemExit(f"invalid grep regex: {exc}") from exc
    return "\n".join(line for line in raw.splitlines() if rx.search(line)) + "\n"


def cmd_filter(args: argparse.Namespace) -> int:
    cfg = load_config(args.repo)
    raw = sys.stdin.read()
    session_id = _session_id()
    seen_path = _state_dir(cfg.repo_root) / "seen" / f"{session_id}.txt"
    session_aware = args.session_aware or bool(cfg.output_filter_session_aware)
    filtered, filter_stats = filter_text(
        raw,
        rules=load_rules(cfg.output_filter_rules),
        session_aware=session_aware,
        seen_path=seen_path,
        content_type=args.content_type,
    )
    marker = ""
    if cfg.output_filter_archive and not args.no_archive:
        record = archive_event(cfg.repo_root, raw, filtered, filter_stats, session_id)
        if args.show_marker and raw != filtered:
            marker = (
                f"\n[output-filter: raw archived id={record['id']}; "
                f"recover: python3 skills/output-filter/tools/output_filter.py --repo {cfg.repo_root} rewind {record['id']}]\n"
            )
    sys.stdout.write(filtered + marker)
    return 0


def cmd_stats(args: argparse.Namespace) -> int:
    cfg = load_config(args.repo)
    print(json.dumps(stats(cfg.repo_root, limit=args.limit), indent=2, sort_keys=True))
    return 0


def cmd_rewind(args: argparse.Namespace) -> int:
    cfg = load_config(args.repo)
    sys.stdout.write(rewind(cfg.repo_root, args.id, grep=args.grep))
    return 0


def cmd_rules(args: argparse.Namespace) -> int:
    cfg = load_config(args.repo)
    path = cfg.output_filter_rules
    if args.init:
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists():
            path.write_text(
                "# One rule per line: keep:<regex>, drop:<regex>, collapse:<regex>\n"
                "# keep rules override drop/collapse and dedupe.\n"
                "keep:(error|fail|fatal|traceback|exception)\n"
                "collapse:\\d+%\\s*$\n",
                encoding="utf-8",
            )
    print(json.dumps({"path": str(path), "exists": path.exists()}, indent=2, sort_keys=True))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="output-filter")
    parser.add_argument("--repo", default=None)
    sub = parser.add_subparsers(dest="cmd", required=True)
    flt = sub.add_parser("filter")
    flt.add_argument("--no-archive", action="store_true")
    flt.add_argument("--session-aware", action="store_true")
    flt.add_argument("--content-type", choices=CONTENT_TYPES, default="auto")
    flt.add_argument("--show-marker", action="store_true", help="print a raw-output recovery marker when archived output is compressed")
    flt.set_defaults(func=cmd_filter)
    st = sub.add_parser("stats")
    st.add_argument("--limit", type=int)
    st.set_defaults(func=cmd_stats)
    rw = sub.add_parser("rewind")
    rw.add_argument("id", nargs="?", default="last")
    rw.add_argument("--grep", help="return only archived raw lines matching this regex")
    rw.set_defaults(func=cmd_rewind)
    rules = sub.add_parser("rules")
    rules.add_argument("--init", action="store_true")
    rules.set_defaults(func=cmd_rules)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
