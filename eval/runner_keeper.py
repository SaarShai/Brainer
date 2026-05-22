#!/usr/bin/env python3
"""Fidelity measurement for context-keeper extract.py.

Method:
  - Read a transcript JSONL.
  - Independently count distinct files / commands / errors / URLs that
    appear in the raw transcript (ground truth).
  - Run extract.py against the same transcript -> extracted markdown.
  - Count how many of those ground-truth items survive in the extracted
    markdown.
  - Compute recall (captured / ground-truth) per category.
  - Also report compression ratio: bytes/tokens in vs out.

This tells us, concretely:
  - How much state survives compaction when the hook runs (vs. nothing, which
    is the without-hook baseline since stock /compact summarisers drop
    structured detail).
  - How small the sidecar is relative to the transcript it summarises.

Usage:
  python3 eval/runner_keeper.py <transcript.jsonl> [--out path] [--llm 0]
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path

PATH_RE = re.compile(r"(?:~|\.{0,2})/[\w\-./]+\.(?:py|js|ts|tsx|jsx|rs|md|txt|json|yaml|yml|toml|sh|go|rb|java|c|cpp|h|hpp|css|html|sql|mjs|cjs|ini|conf)")
URL_RE = re.compile(r"https?://[^\s)\]'\"]+")
NUM_RE = re.compile(r"\b\d+(?:\.\d+)?\s*(?:%|ms|s|x|tokens?|tok|GB|MB|KB|B|bytes?|lines?|items?|calls?)\b", re.I)
ERROR_RE = re.compile(r"(?:Error|Exception|Traceback|fail(?:ed|ure)?|SIGKILL|exit code [1-9]|stderr)[^\n]{3,200}", re.I)
BASH_RE = re.compile(r'"name"\s*:\s*"Bash"[^}]*"command"\s*:\s*"([^"]+)"')


def iter_events(path):
    with open(path) as f:
        for line in f:
            try:
                yield json.loads(line)
            except Exception:
                continue


def extract_text(content):
    """Flatten a content block into plain text — same heuristic as extract.py."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for b in content:
            if isinstance(b, dict):
                if "text" in b:
                    parts.append(b["text"])
                elif b.get("type") == "tool_use":
                    parts.append(f"TOOL:{b.get('name','?')} INPUT:{json.dumps(b.get('input', {}))[:500]}")
                elif b.get("type") == "tool_result":
                    c = b.get("content", "")
                    if isinstance(c, list):
                        parts.append(extract_text(c))
                    elif isinstance(c, str):
                        parts.append(c)
        return "\n".join(parts)
    if isinstance(content, dict) and "text" in content:
        return content["text"]
    return ""


def ground_truth(jsonl_path: Path) -> dict:
    """Distinct files, commands, errors, URLs in the raw transcript."""
    files: set[str] = set()
    cmds: set[str] = set()
    errors: set[str] = set()
    urls: set[str] = set()
    nums: set[str] = set()
    n_events = 0
    raw_chars = 0
    for ev in iter_events(jsonl_path):
        n_events += 1
        msg = ev.get("message") or ev
        content = msg.get("content", "") if isinstance(msg, dict) else ""
        text = extract_text(content)
        raw_chars += len(text)
        for m in PATH_RE.findall(text):
            files.add(m)
        for m in URL_RE.findall(text):
            urls.add(m)
        for m in NUM_RE.findall(text):
            nums.add(m.strip().lower())
        for m in ERROR_RE.findall(text):
            errors.add(m.strip()[:120])
        # Bash commands are inside tool_use blocks
        text_for_bash = json.dumps(content) if isinstance(content, (list, dict)) else str(content)
        for m in BASH_RE.findall(text_for_bash):
            cmds.add(m.strip()[:200])
    return {
        "events": n_events,
        "raw_chars": raw_chars,
        "files": files,
        "cmds": cmds,
        "errors": errors,
        "urls": urls,
        "nums": nums,
    }


def extracted_recall(extracted_md: str, gt: dict) -> dict:
    """For each ground-truth set, what fraction appears in the extracted markdown?"""
    md = extracted_md
    def hits(items: set[str]) -> int:
        return sum(1 for x in items if x in md)
    return {
        "files_recall": round(hits(gt["files"]) / max(len(gt["files"]), 1), 3),
        "cmds_recall": round(hits(gt["cmds"]) / max(len(gt["cmds"]), 1), 3),
        "errors_recall": round(hits(gt["errors"]) / max(len(gt["errors"]), 1), 3),
        "urls_recall": round(hits(gt["urls"]) / max(len(gt["urls"]), 1), 3),
        "nums_recall": round(hits(gt["nums"]) / max(len(gt["nums"]), 1), 3),
    }


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("transcript")
    p.add_argument("--out", default="eval/results/context-keeper.json")
    p.add_argument("--llm", default="0", help="set to a model name to enable LLM pass (default off)")
    args = p.parse_args()

    transcript = Path(args.transcript)
    if not transcript.exists():
        print(f"not found: {transcript}", file=sys.stderr)
        return 2

    print(f"[1/3] ground truth from {transcript.name}")
    gt = ground_truth(transcript)
    print(f"      events={gt['events']} raw_chars={gt['raw_chars']}")
    print(f"      files={len(gt['files'])} cmds={len(gt['cmds'])} errors={len(gt['errors'])} urls={len(gt['urls'])} nums={len(gt['nums'])}")

    print(f"[2/3] run extract.py")
    extract_script = Path(__file__).resolve().parents[1] / "skills/context-keeper/tools/extract.py"
    with tempfile.NamedTemporaryFile(suffix=".md", delete=False) as f:
        out_path = Path(f.name)
    cmd = [sys.executable, str(extract_script), str(transcript), "--out", str(out_path)]
    if args.llm and args.llm != "0":
        cmd.extend(["--llm", args.llm])
    t0 = time.time()
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
    extract_ms = int((time.time() - t0) * 1000)
    if proc.returncode != 0:
        print(f"extract failed: {proc.stderr[:500]}", file=sys.stderr)
        return 1
    extracted = out_path.read_text()
    extracted_chars = len(extracted)

    print(f"      extracted {extracted_chars} chars in {extract_ms} ms")

    print(f"[3/3] recall")
    recall = extracted_recall(extracted, gt)
    for k, v in recall.items():
        print(f"      {k}: {v:.1%}")

    summary = {
        "transcript": str(transcript),
        "extract_ms": extract_ms,
        "raw_chars": gt["raw_chars"],
        "raw_chars_kb": round(gt["raw_chars"] / 1024, 1),
        "extracted_chars": extracted_chars,
        "extracted_chars_kb": round(extracted_chars / 1024, 1),
        "compression_ratio": round(extracted_chars / max(gt["raw_chars"], 1), 4),
        "events": gt["events"],
        "counts": {
            "files": len(gt["files"]),
            "cmds": len(gt["cmds"]),
            "errors": len(gt["errors"]),
            "urls": len(gt["urls"]),
            "nums": len(gt["nums"]),
        },
        "recall": recall,
        "extracted_preview": extracted[:1500],
    }

    out_path_results = Path(args.out)
    out_path_results.parent.mkdir(parents=True, exist_ok=True)
    out_path_results.write_text(json.dumps(summary, indent=2))

    print(f"\n=== summary ===")
    print(f"  raw transcript: {summary['raw_chars_kb']} KB")
    print(f"  extracted:      {summary['extracted_chars_kb']} KB ({summary['compression_ratio'] * 100:.1f}% of raw)")
    print(f"  files captured: {recall['files_recall']:.1%} of {summary['counts']['files']}")
    print(f"  cmds captured:  {recall['cmds_recall']:.1%} of {summary['counts']['cmds']}")
    print(f"  errors:         {recall['errors_recall']:.1%} of {summary['counts']['errors']}")
    print(f"  results: {out_path_results}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
