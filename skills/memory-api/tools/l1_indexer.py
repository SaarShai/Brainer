#!/usr/bin/env python3
"""Rebuild context-keeper v2 L1 pointer index."""
from __future__ import annotations

import argparse
import os
from pathlib import Path


def rebuild(root: Path) -> Path:
    root = root.expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    lines = ["# L1 Index", "", "Compact memory pointers. Fetch details on demand.", ""]
    for subdir, label in (("L2_facts", "fact"), ("L3_sops", "sop")):
        d = root / subdir
        d.mkdir(exist_ok=True)
        for path in sorted(d.glob("*.md")):
            preview = ""
            for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
                line = line.strip()
                if line and not line.startswith(("---", "#", "type:", "slug:")):
                    preview = line[:100]
                    break
            lines.append(f"- {path.stem} ({label}) {preview} -> `{path.relative_to(root).as_posix()}`")
    out = root / "L1_index.md"
    out.write_text("\n".join(lines[:80]) + "\n", encoding="utf-8")
    return out


def main() -> int:
    parser = argparse.ArgumentParser()
    default_root = Path(os.environ.get("TOKEN_ECONOMY_ROOT", Path.cwd())) / ".token-economy" / "memory"
    parser.add_argument("--root", default=str(default_root))
    args = parser.parse_args()
    print(rebuild(Path(args.root)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
