#!/usr/bin/env python3
"""Analyze injected reminder cost across one or more raw transcript JSONL files.

Only real attachment records are counted; reminder strings quoted in tool
output are excluded. Reports contain hashes and measurements, never transcript
content. Optional human labels are joined by stable event ID.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any

REMINDER_RE = re.compile(r"<system-reminder>[\s\S]*?</system-reminder>")
PROBE_RE = re.compile(r"(?m)^-\s+([\w-]+)\[([\w-]+)\]:")
SECTION_PATTERNS = {
    "ledger": re.compile(r"compliance-canary ledger \(turn \d+\):"),
    "re-anchor": re.compile(r"compliance-canary re-anchor \(turn \d+\):"),
    "escalation": re.compile(r"compliance-canary ESCALATION \(turn \d+\):"),
    "correction-ledger": re.compile(r"compliance-canary correction ledger \(turn \d+\):"),
}
LABELS = {"ACTED", "ALREADY_COMPLIANT", "IGNORED", "UNCLEAR"}
LABEL_KEYS = {"event_id", "label", "rationale", "reviewer"}


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _attachment_content(record: dict) -> str:
    if record.get("type") != "attachment":
        return ""
    attachment = record.get("attachment")
    if not isinstance(attachment, dict):
        return ""
    content = attachment.get("content")
    return content if isinstance(content, str) else ""


def _usage(record: Any, out: Counter) -> None:
    if isinstance(record, dict):
        for key, value in record.items():
            lower = key.lower()
            if isinstance(value, (int, float)) and ("token" in lower or key in {"input", "output"}):
                out[key] += value
            elif key in {"usage", "usage_metadata", "usageMetadata"}:
                _usage(value, out)
            elif isinstance(value, (dict, list)):
                _usage(value, out)
    elif isinstance(record, list):
        for value in record:
            _usage(value, out)


def load_labels(path: Path | None) -> dict[str, dict]:
    if path is None:
        return {}
    result = {}
    for n, line in enumerate(path.read_text().splitlines(), 1):
        if not line.strip():
            continue
        row = json.loads(line)
        extra = set(row) - LABEL_KEYS
        if extra:
            raise ValueError(f"label line {n}: forbidden keys {sorted(extra)}; transcript content is not allowed")
        if row.get("label") not in LABELS or not all(row.get(k) for k in LABEL_KEYS):
            raise ValueError(f"label line {n}: event_id, valid label, rationale, reviewer required")
        result[row["event_id"]] = row
    return result


def analyze_source(path: Path, labels: dict[str, dict]) -> dict:
    source_sha = sha256_file(path)
    events = []
    usage = Counter()
    decode_errors = 0
    with path.open("rb") as fh:
        for line_index, raw in enumerate(fh, 1):
            try:
                record = json.loads(raw)
            except (json.JSONDecodeError, UnicodeDecodeError):
                decode_errors += 1
                continue
            _usage(record, usage)
            content = _attachment_content(record)
            for block_index, match in enumerate(REMINDER_RE.finditer(content)):
                block = match.group(0)
                encoded = block.encode("utf-8")
                event_id = f"{source_sha[:12]}:{line_index}:{block_index}"
                probes = sorted({f"{a}:{b}" for a, b in PROBE_RE.findall(block)})
                sections = [name for name, regex in SECTION_PATTERNS.items() if regex.search(block)]
                event = {"event_id": event_id, "event_index": len(events),
                         "jsonl_line_index": line_index, "block_index": block_index,
                         "unicode_codepoints": len(block), "utf8_bytes": len(encoded),
                         "content_sha256": hashlib.sha256(encoded).hexdigest(),
                         "token_estimate": {"method": "utf8_bytes_div_4", "tokens": (len(encoded) + 3) // 4},
                         "probes": probes, "sections": sections}
                if event_id in labels:
                    event["human_label"] = labels[event_id]
                events.append(event)
    return {"path": str(path.resolve()), "source_sha256": source_sha,
            "source_utf8_bytes": path.stat().st_size, "records_with_decode_errors": decode_errors,
            "available_usage_telemetry": dict(usage), "reminder_events": len(events),
            "legacy_codepoint_count": sum(e["unicode_codepoints"] for e in events),
            "injected_utf8_bytes": sum(e["utf8_bytes"] for e in events),
            "token_estimate": {"method": "utf8_bytes_div_4",
                               "tokens": sum(e["token_estimate"]["tokens"] for e in events)},
            "events": events}


def markdown(report: dict) -> str:
    lines = ["# Fire-vs-value transcript analysis", "",
             "Observational injection measurements; labels are immediate-action correlation, not causal outcome lift.", "",
             "| source | SHA-256 | reminders | UTF-8 bytes | token estimate |", "|---|---:|---:|---:|---:|"]
    for source in report["sources"]:
        lines.append(f"| `{source['path']}` | `{source['source_sha256']}` | {source['reminder_events']} | "
                     f"{source['injected_utf8_bytes']} | {source['token_estimate']['tokens']} |")
    totals = report["totals"]
    lines += ["", f"Total: **{totals['reminder_events']} reminders**, "
              f"**{totals['injected_utf8_bytes']} exact UTF-8 bytes**; "
              f"{totals['token_estimate']['tokens']} estimated tokens "
              f"(`{totals['token_estimate']['method']})."]
    if totals["legacy_codepoint_count"] != totals["injected_utf8_bytes"]:
        lines += ["",
            f"Legacy reports may call `{totals['legacy_codepoint_count']}` bytes; that is the Unicode "
            "code-point count. Exact UTF-8 measurement is reported above."]
    lines += ["", "## Labels", ""]
    counts = totals["label_counts"]
    lines.append(", ".join(f"{name}: {counts.get(name, 0)}" for name in sorted(LABELS)) or "No labels supplied.")
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("transcripts", nargs="+", type=Path)
    ap.add_argument("--labels", type=Path)
    ap.add_argument("--json-out", type=Path, required=True)
    ap.add_argument("--markdown-out", type=Path, required=True)
    args = ap.parse_args()
    labels = load_labels(args.labels)
    sources = [analyze_source(path, labels) for path in args.transcripts]
    label_counts = Counter(e["human_label"]["label"] for s in sources for e in s["events"] if "human_label" in e)
    report = {"schema_version": 1, "sources": sources,
              "totals": {"reminder_events": sum(s["reminder_events"] for s in sources),
                         "legacy_codepoint_count": sum(s["legacy_codepoint_count"] for s in sources),
                         "injected_utf8_bytes": sum(s["injected_utf8_bytes"] for s in sources),
                         "token_estimate": {"method": "utf8_bytes_div_4",
                                            "tokens": sum(s["token_estimate"]["tokens"] for s in sources)},
                         "label_counts": dict(label_counts)}}
    args.json_out.parent.mkdir(parents=True, exist_ok=True)
    args.markdown_out.parent.mkdir(parents=True, exist_ok=True)
    args.json_out.write_text(json.dumps(report, indent=2) + "\n")
    args.markdown_out.write_text(markdown(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
