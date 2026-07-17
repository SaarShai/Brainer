#!/usr/bin/env python3
"""Static skill-cost measurement.

For each skill, computes:
  - description tokens (always-resident in agent context per agentskills.io)
  - body tokens (loaded on trigger)
  - tools/ payload size (loaded only when scripts run)

Token estimates use tiktoken (cl100k_base) if available, else char/3.5 heuristic.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any


def count_tokens(text: str) -> int:
    try:
        import tiktoken
        enc = tiktoken.get_encoding("cl100k_base")
        return len(enc.encode(text))
    except ImportError:
        # Heuristic fallback: ~3.5 chars per token for English prose.
        return max(1, round(len(text) / 3.5))


def parse_frontmatter(text: str) -> tuple[dict, str]:
    m = re.match(r"^---\n(.*?)\n---\n(.*)$", text, re.DOTALL)
    if not m:
        return {}, text
    fm: dict = {}
    for line in m.group(1).splitlines():
        if ":" in line:
            k, _, v = line.partition(":")
            fm[k.strip()] = v.strip()
    return fm, m.group(2)


def dir_size(p: Path) -> int:
    # Generated caches (__pycache__/*.pyc) are runtime noise, not shipped
    # payload — counting them makes the size claim drift with whichever
    # Python version last imported the tools (H6a false-FAIL, 2026-07-17).
    return sum(f.stat().st_size for f in p.rglob("*")
               if f.is_file() and "__pycache__" not in f.parts and f.suffix != ".pyc")


def measure(skill_dir: Path) -> dict[str, Any]:
    skill_md = skill_dir / "SKILL.md"
    if not skill_md.exists():
        return {}
    text = skill_md.read_text()
    fm, body = parse_frontmatter(text)
    desc = fm.get("description", "")
    tools_dir = skill_dir / "tools"
    tools_bytes = dir_size(tools_dir) if tools_dir.exists() else 0
    eval_md = skill_dir / "EVAL.md"
    has_eval = eval_md.exists()

    return {
        "name": skill_dir.name,
        "description_tokens": count_tokens(desc),
        "description_chars": len(desc),
        "body_tokens": count_tokens(body),
        "body_chars": len(body),
        "tools_bytes": tools_bytes,
        "tools_kb": round(tools_bytes / 1024, 1),
        "has_eval_template": has_eval,
        "model_pin": fm.get("model", ""),
        "effort_pin": fm.get("effort", ""),
    }


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--skills", default="skills", help="path to skills/ root")
    p.add_argument("--json", action="store_true")
    args = p.parse_args()

    root = Path(args.skills)
    if not root.is_dir():
        print(f"{root}: not a directory", file=sys.stderr)
        return 2

    rows = []
    for d in sorted(root.iterdir()):
        if not d.is_dir() or d.name.startswith("_"):
            continue
        m = measure(d)
        if m:
            rows.append(m)

    if args.json:
        print(json.dumps(rows, indent=2))
        return 0

    # Markdown table
    print("| skill | desc tokens | body tokens | tools KB | model | effort |")
    print("|---|---:|---:|---:|---|---|")
    desc_total = body_total = tools_total = 0
    for r in rows:
        desc_total += r["description_tokens"]
        body_total += r["body_tokens"]
        tools_total += r["tools_bytes"]
        print(f"| {r['name']} | {r['description_tokens']} | {r['body_tokens']} | {r['tools_kb']} | {r['model_pin'] or '-'} | {r['effort_pin'] or '-'} |")
    print(f"| **TOTAL** | **{desc_total}** | **{body_total}** | **{round(tools_total/1024, 1)}** | | |")
    print(f"\n_Always-resident context tax (descriptions only): **{desc_total} tokens** for {len(rows)} skills._")
    print(f"_Worst case all-loaded body cost: **{body_total} tokens**._")
    return 0


if __name__ == "__main__":
    sys.exit(main())
