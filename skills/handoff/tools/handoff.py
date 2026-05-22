#!/usr/bin/env python3
"""Pure write-doc handoff. Calls context-refresh's checkpoint() and writes
the packet to $TMPDIR/handoff-<timestamp>.md. Prints the absolute path.

No successor launch, no wiki write, no API calls. Local only.

Usage:
  python3 handoff.py [--goal "focus argument"] [--out PATH]

If --out is omitted, writes to $TMPDIR/handoff-YYYYMMDD-HHMMSS.md.
"""
from __future__ import annotations

import argparse
import os
import sys
import tempfile
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[2]
sys.path.insert(0, str(REPO_ROOT / "skills" / "context-refresh" / "tools"))

from context import checkpoint  # noqa: E402


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--goal", default="", help="focus argument; tailors the handoff doc")
    p.add_argument("--out", default=None, help="output path (default: $TMPDIR/handoff-<ts>.md)")
    p.add_argument("--print-only", action="store_true", help="print packet to stdout instead of writing a file")
    args = p.parse_args()

    result = checkpoint(REPO_ROOT, goal=args.goal)
    packet = result.get("packet") or result.get("contents") or str(result)

    if args.print_only:
        sys.stdout.write(packet)
        return 0

    out_path = Path(args.out) if args.out else Path(tempfile.gettempdir()) / f"handoff-{datetime.now().strftime('%Y%m%d-%H%M%S')}.md"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(packet)
    print(str(out_path.resolve()))
    return 0


if __name__ == "__main__":
    sys.exit(main())
