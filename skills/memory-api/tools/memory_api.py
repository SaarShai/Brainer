"""context-keeper v2 retrieval API: ck_query, ck_fetch, ck_recent."""
from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Any


DEFAULT_ROOT = Path(os.environ.get("TOKEN_ECONOMY_ROOT", Path.cwd())) / ".token-economy" / "memory"
ALLOWED_TIERS = {"L0": "L0_rules.md", "L1": "L1_index.md", "L2": "L2_facts", "L3": "L3_sops", "L4": "L4_archive"}


def memory_root(root: str | Path | None = None) -> Path:
    return Path(root).expanduser().resolve() if root else DEFAULT_ROOT


def ck_query(keyword: str, root: str | Path | None = None, k: int = 10) -> list[dict[str, Any]]:
    base = memory_root(root)
    hits: list[dict[str, Any]] = []
    needle = keyword.lower()
    candidates = []
    for rel in ("L1_index.md", "L0_rules.md"):
        p = base / rel
        if p.exists():
            candidates.append(p)
    for sub in ("L2_facts", "L3_sops"):
        d = base / sub
        if d.exists():
            candidates.extend(sorted(d.glob("*.md")))
    for path in candidates:
        text = path.read_text(encoding="utf-8", errors="replace")
        if needle in text.lower() or needle in path.stem.lower():
            preview = next((ln.strip() for ln in text.splitlines() if needle in ln.lower()), "")
            hits.append({"id": path.stem, "path": path.relative_to(base).as_posix(), "preview": preview[:240]})
        if len(hits) >= k:
            break
    return hits


def ck_fetch(tier: str, slug: str, root: str | Path | None = None) -> dict[str, Any]:
    base = memory_root(root)
    if tier not in ALLOWED_TIERS:
        raise KeyError(f"unknown tier: {tier}")
    rel = ALLOWED_TIERS[tier]
    path = base / rel
    if path.is_dir():
        slug_path = slug if slug.endswith(".md") else f"{slug}.md"
        path = path / slug_path
    if not path.exists():
        raise FileNotFoundError(path)
    return {"tier": tier, "slug": slug, "path": path.relative_to(base).as_posix(), "content": path.read_text(encoding="utf-8", errors="replace")}


def ck_recent(days: int = 7, root: str | Path | None = None) -> list[dict[str, Any]]:
    base = memory_root(root)
    archive = base / "L4_archive"
    if not archive.exists():
        return []
    cutoff = time.time() - days * 86400
    rows = []
    for path in sorted(archive.glob("*.md"), key=lambda p: p.stat().st_mtime, reverse=True):
        if path.stat().st_mtime >= cutoff:
            rows.append({"path": path.relative_to(base).as_posix(), "mtime": int(path.stat().st_mtime)})
    return rows
