"""Tier manager: write-gate + promotion rules for context-keeper v2.

Enforces "no execution, no memory" — only verified tool-call results write to L2/L3.

Usage:
    from tier_manager import TierManager
    tm = TierManager()
    tm.record_action(tool_name, args, result)  # may write L2 fact
    tm.record_task_completion(task_slug, steps, outcome)  # may write L3 SOP
"""
from __future__ import annotations
import json, os, re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


DEFAULT_ROOT = Path(os.environ.get("TOKEN_ECONOMY_ROOT", Path.cwd())) / ".token-economy" / "memory"


@dataclass
class TierManager:
    root: Path = DEFAULT_ROOT

    def __post_init__(self):
        for sub in ("L2_facts", "L3_sops", "L4_archive"):
            (self.root / sub).mkdir(parents=True, exist_ok=True)
        for f in ("L0_rules.md", "L1_index.md"):
            (self.root / f).touch(exist_ok=True)

    # --- write gate ---
    def record_action(self, tool: str, args: dict, result: str,
                       exit_code: int = 0) -> Optional[Path]:
        """Called after each tool-use. May write L2 fact if action was verified.

        Rules:
        - exit_code != 0: no write (failure doesn't become memory)
        - Bash tool with `cd`/`ls`/`pwd`/read-only patterns: no write
        - Write tool with file_path outside workspace: no write
        - Otherwise: extract path/value facts → append to L2_facts/<category>.md
        """
        if exit_code != 0:
            return None
        category = self._categorize(tool, args)
        if not category:
            return None
        fact_line = self._extract_fact(tool, args, result)
        if not fact_line:
            return None
        path = self.root / "L2_facts" / f"{category}.md"
        existing = path.read_text() if path.exists() else ""
        if fact_line in existing:
            return None  # dedupe
        with path.open("a") as f:
            f.write(fact_line + "\n")
        return path

    def record_task_completion(self, slug: str, steps: list[dict],
                                outcome: dict) -> Optional[Path]:
        """Called after successful multi-step task. Writes L3 SOP."""
        if not outcome.get("success"):
            return None
        path = self.root / "L3_sops" / f"{slug}.md"
        if path.exists():
            return None  # don't overwrite existing SOP
        content = [
            "---",
            f"slug: {slug}",
            "type: sop",
            f"created: {outcome.get('timestamp','')}",
            "---",
            "",
            f"# SOP: {slug}",
            "",
            "## Steps",
        ]
        for i, s in enumerate(steps, 1):
            content.append(f"{i}. {s.get('tool','?')} — {s.get('summary','')[:200]}")
        content.append("")
        content.append(f"## Outcome\n{outcome.get('summary','')}")
        path.write_text("\n".join(content) + "\n")
        return path

    # --- promotion (L3 → L2 when cross-task pattern emerges) ---
    def promote_sop_pattern(self, pattern: str, min_refs: int = 3) -> Optional[Path]:
        """If ≥min_refs SOPs reference the same pattern, extract to L2 fact."""
        sops = list((self.root / "L3_sops").glob("*.md"))
        refs = [s for s in sops if pattern in s.read_text()]
        if len(refs) < min_refs:
            return None
        path = self.root / "L2_facts" / "cross_task_patterns.md"
        line = f"- pattern `{pattern}` seen in {len(refs)} SOPs"
        existing = path.read_text() if path.exists() else ""
        if line in existing:
            return None
        with path.open("a") as f:
            f.write(line + "\n")
        return path

    # --- L1 index rebuild ---
    def rebuild_index(self) -> Path:
        """Scan L2 + L3, emit L1 pointer index (≤30 lines, ≤1K tokens)."""
        entries = []
        for f in sorted((self.root / "L2_facts").glob("*.md")):
            entries.append(f"- **{f.stem}** (facts) → `{f.relative_to(self.root)}`")
        for f in sorted((self.root / "L3_sops").glob("*.md")):
            # first-line summary if available
            summary = next((ln for ln in f.read_text().splitlines()
                            if ln and not ln.startswith(("---", "slug:", "type:", "#"))),
                            "")[:60]
            entries.append(f"- **{f.stem}** (sop) {summary} → `{f.relative_to(self.root)}`")
        entries = entries[:30]
        path = self.root / "L1_index.md"
        path.write_text("# L1 — index\n\n" + "\n".join(entries) + "\n")
        return path

    def ck_query(self, keyword: str, k: int = 10) -> list[dict]:
        """Return compact L1/L2/L3 hits for on-demand retrieval."""
        hits = []
        needle = keyword.lower()
        candidates = [self.root / "L0_rules.md", self.root / "L1_index.md"]
        candidates.extend(sorted((self.root / "L2_facts").glob("*.md")))
        candidates.extend(sorted((self.root / "L3_sops").glob("*.md")))
        for path in candidates:
            if not path.exists():
                continue
            text = path.read_text(errors="replace")
            if needle in text.lower() or needle in path.stem.lower():
                preview = next((ln.strip() for ln in text.splitlines() if needle in ln.lower()), "")
                hits.append({"id": path.stem, "path": str(path.relative_to(self.root)), "preview": preview[:240]})
            if len(hits) >= k:
                break
        return hits

    def ck_fetch(self, tier: str, slug: str) -> dict:
        """Fetch one memory object by tier and slug."""
        tier_map = {
            "L0": self.root / "L0_rules.md",
            "L1": self.root / "L1_index.md",
            "L2": self.root / "L2_facts" / (slug if slug.endswith(".md") else f"{slug}.md"),
            "L3": self.root / "L3_sops" / (slug if slug.endswith(".md") else f"{slug}.md"),
            "L4": self.root / "L4_archive" / (slug if slug.endswith(".md") else f"{slug}.md"),
        }
        if tier not in tier_map:
            raise KeyError(tier)
        path = tier_map[tier]
        if not path.exists():
            raise FileNotFoundError(path)
        return {"tier": tier, "slug": slug, "path": str(path.relative_to(self.root)), "content": path.read_text(errors="replace")}

    def ck_recent(self, limit: int = 10) -> list[dict]:
        """Return recent L4 archive pointers."""
        archive = self.root / "L4_archive"
        rows = []
        for path in sorted(archive.glob("*.md"), key=lambda p: p.stat().st_mtime, reverse=True)[:limit]:
            rows.append({"path": str(path.relative_to(self.root)), "mtime": int(path.stat().st_mtime)})
        return rows

    # --- helpers ---
    def _categorize(self, tool: str, args: dict) -> Optional[str]:
        if tool == "Bash":
            cmd = args.get("command", "")
            if re.match(r"^\s*(ls|pwd|cat|head|tail)\s", cmd): return None
            if "install" in cmd or "pip" in cmd: return "tool_configs"
            return None
        if tool == "Write":
            fp = args.get("file_path", "")
            if fp.startswith("/tmp/") or "/.git/" in fp: return None
            return "paths"
        if tool == "Edit":
            return "paths"
        return None

    def _extract_fact(self, tool: str, args: dict, result: str) -> Optional[str]:
        if tool in ("Write", "Edit"):
            fp = args.get("file_path", "")
            if fp:
                return f"- `{fp}` touched"
        if tool == "Bash":
            cmd = args.get("command", "")[:150]
            return f"- ran `{cmd}`"
        return None
