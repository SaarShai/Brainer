#!/usr/bin/env python3
"""Unified handoff CLI.

Three modes, all local (no API, no successor launch):

  default        write a conversation handoff doc to $TMPDIR
  --full         write the doc AND route durable facts to wiki/L2_facts/
  --ask QUESTION query the most recent handoff doc for one specific fact

Usage:
  python3 handoff.py [--goal "focus"]                       # default
  python3 handoff.py [--goal "focus"] --full                # also wiki
  python3 handoff.py --ask "what was the auth bug about?"   # retrieval
  python3 handoff.py --print-only                           # to stdout
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import tempfile
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[2]
sys.path.insert(0, str(HERE / "_lib"))

from context import (  # noqa: E402
    checkpoint,
    extract_transcript_facts,
    ask_old_from_transcript,
)


def write_doc(goal: str, out: Path | None) -> Path:
    """Build the handoff packet via checkpoint() and write to disk."""
    result = checkpoint(REPO_ROOT, goal=goal)
    packet = result.get("packet") or result.get("contents") or str(result)
    out_path = out or (
        Path(tempfile.gettempdir())
        / f"handoff-{datetime.now().strftime('%Y%m%d-%H%M%S')}.md"
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(packet, encoding="utf-8")
    return out_path


def route_to_wiki(packet_path: Path, goal: str) -> Path | None:
    """Extract durable facts from the packet and append to wiki/L2_facts/.

    Conservative: writes ONE small markdown file per handoff with the
    extracted facts. Does not modify existing wiki pages. The slug uses
    the focus argument so multiple handoffs in a day don't collide.

    Emits v2 frontmatter so `wiki.py lint --strict` accepts the page
    (missing_v2_field / legacy_missing_frontmatter / missing_provenance
    would otherwise fire on every routed handoff).
    """
    wiki_root = REPO_ROOT / "wiki" / "L2_facts"
    wiki_root.mkdir(parents=True, exist_ok=True)
    packet_text = packet_path.read_text(encoding="utf-8", errors="replace")
    facts = extract_transcript_facts(packet_text)
    if not any(facts.values()):
        return None
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", (goal or "session").lower()).strip("-")[:40] or "session"
    today = datetime.now().strftime("%Y-%m-%d")
    out = wiki_root / f"{datetime.now().strftime('%Y%m%d-%H%M')}-{slug}.md"
    title = (goal or slug).replace('"', '\\"')[:80]
    packet_ref = str(packet_path).replace('"', '\\"')
    lines = [
        "---",
        "schema_version: 2",
        f'title: "Handoff facts — {title}"',
        "type: handoff",
        "domain: framework",
        "tier: episodic",
        "confidence: 0.7",
        f"created: {today}",
        f"updated: {today}",
        f"verified: {today}",
        f'sources: ["{packet_ref}"]',
        "supersedes: []",
        "superseded-by:",
        "contradicts: []",
        "tags: [handoff, routed]",
        "---",
        "",
        f"# Handoff facts — {slug}",
        f"_source: {packet_path}_",
        "",
    ]
    for category, items in facts.items():
        if not items:
            continue
        lines.append(f"## {category.replace('_', ' ')}")
        for it in items[:30]:
            lines.append(f"- {it}")
        lines.append("")
    out.write_text("\n".join(lines), encoding="utf-8")
    return out


def find_latest_handoff() -> Path | None:
    """Return the most recent handoff-*.md from $TMPDIR or the runtime dir."""
    candidates: list[Path] = []
    tmp = Path(tempfile.gettempdir())
    candidates.extend(tmp.glob("handoff-*.md"))
    candidates.extend((REPO_ROOT / ".token-economy" / "checkpoints").glob("*-fresh-session.md"))
    if not candidates:
        return None
    return max(candidates, key=lambda p: p.stat().st_mtime)


def ask_last(question: str) -> dict:
    """Find the most recent handoff and pull a targeted answer from it."""
    latest = find_latest_handoff()
    if not latest:
        return {
            "ok": False,
            "reason": "no handoff doc found in $TMPDIR or .token-economy/checkpoints/",
        }
    result = ask_old_from_transcript(latest, question)
    result["source"] = str(latest)
    return result


def main() -> int:
    p = argparse.ArgumentParser(
        prog="handoff",
        description="Unified session-handoff CLI (write / full / ask).",
    )
    p.add_argument("--goal", default="", help="focus argument; tailors the doc")
    p.add_argument("--out", default=None, help="output path (default: $TMPDIR/handoff-<ts>.md)")
    p.add_argument("--print-only", action="store_true", help="print packet to stdout instead of writing")
    p.add_argument("--full", action="store_true", help="also route durable facts to wiki/L2_facts/")
    p.add_argument("--ask", metavar="QUESTION", default=None, help="query the most recent handoff for a specific fact")
    args = p.parse_args()

    # Mode 3: ask
    if args.ask:
        result = ask_last(args.ask)
        json.dump(result, sys.stdout, indent=2, default=str)
        sys.stdout.write("\n")
        return 0 if result.get("ok", True) else 1

    # Mode 1 / 2: write doc (always); optionally also route to wiki
    if args.print_only:
        result = checkpoint(REPO_ROOT, goal=args.goal)
        sys.stdout.write(result.get("packet") or result.get("contents") or "")
        return 0

    out_path = Path(args.out) if args.out else None
    packet_path = write_doc(args.goal, out_path)
    print(str(packet_path.resolve()))

    if args.full:
        wiki_path = route_to_wiki(packet_path, args.goal)
        if wiki_path:
            print(f"wiki: {wiki_path.resolve()}", file=sys.stderr)
        else:
            print("wiki: no durable facts extracted (skipped)", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
