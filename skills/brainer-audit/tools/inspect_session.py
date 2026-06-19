#!/usr/bin/env python3
"""Inspect normalized brainer-audit events and emit a report."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import List, Optional

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from detectors import load_events, run_detectors  # noqa: E402
from report import build_json_report, build_markdown_report, dump_json  # noqa: E402


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(prog="inspect_session.py", description=__doc__)
    ap.add_argument("--events", required=True)
    ap.add_argument("--format", choices=["json", "markdown"], default="markdown")
    args = ap.parse_args(argv)
    try:
        events = load_events(Path(args.events).expanduser().resolve())
        findings = run_detectors(events)
        json_report = build_json_report(events, findings)
        markdown_report = build_markdown_report(events, findings)
        if args.format == "json":
            print(dump_json(json_report), end="")
        else:
            print(markdown_report, end="")
        return 1 if any(f.severity == "error" for f in findings) else 0
    except (OSError, ValueError) as exc:
        print(f"inspect_session.py: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
