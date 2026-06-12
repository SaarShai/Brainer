#!/usr/bin/env python3
"""memory-decay — exponential confidence decay for wiki-memory pages.

Reads v2 YAML frontmatter, computes days_idle = today - max(verified, updated,
created), applies confidence *= exp(-λ * days_idle), protects error/lesson/sop/
procedure pages and high-evidence pages.

Defaults from ogham-mcp + doobidoo lineage (5%/30d half-life, protect mistakes).
"""
from __future__ import annotations

import argparse
import datetime as dt  # noqa: F401  (used in rewrite_confidence type hint)
import json
import math
import os
import re
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path

# --- Defaults -------------------------------------------------------------

DEFAULT_HALFLIFE_DAYS = 405  # half-life consistent with 5% per 30 idle days
PROTECTED_TYPES = {"error", "lesson", "sop", "procedure"}
PROTECTED_DIRS = {"L0_rules.md", "L3_sops", "raw"}
# Path components never treated as wiki content (VCS, build, vendored, host config,
# git worktrees). Mirrors token_economy/wiki.py SKIP_PARTS so decay scans exactly
# what `te wiki` indexes — not worktree clones or vendored copies.
SKIP_PARTS = {".git", ".token-economy", "__pycache__", ".pytest_cache",
              "vendor", ".claude", "node_modules"}
EVIDENCE_PROTECT_THRESHOLD = 3
def lambda_from_halflife(halflife_days: float) -> float:
    return math.log(2) / halflife_days


# Back-compat alias for any callers / tests using the old name
LAMBDA_FROM_HALFLIFE = lambda_from_halflife


# --- Frontmatter parse / write -------------------------------------------

# Accept both LF and CRLF line endings; tolerate a UTF-8 BOM prefix.
FRONTMATTER_RE = re.compile(r"^﻿?---\r?\n(.*?)\r?\n---\r?\n", re.DOTALL)


def parse_frontmatter(text: str) -> tuple[dict[str, str], str, tuple[int, int] | None]:
    """Return (fields, body, (fm_start, fm_end)) or ({}, text, None) if no fm.

    Robust to: leading BOM, CRLF line endings, quoted scalar values.
    """
    m = FRONTMATTER_RE.match(text)
    if not m:
        return {}, text, None
    fm_block = m.group(1)
    fm: dict[str, str] = {}
    for line in fm_block.splitlines():
        if ":" not in line:
            continue
        k, _, v = line.partition(":")
        # Strip wrapping quotes from scalar values
        val = v.strip()
        if (val.startswith('"') and val.endswith('"')) or (val.startswith("'") and val.endswith("'")):
            val = val[1:-1]
        fm[k.strip()] = val
    return fm, text[m.end():], (0, m.end())


# Match `confidence:` followed by optional quotes around the number.
_CONFIDENCE_REWRITE_RE = re.compile(
    r"""^(confidence:\s*)(['"]?)[\d.]+(['"]?)\s*$""", re.M
)
_VERIFIED_REWRITE_RE = re.compile(
    r"""^(verified:\s*)(['"]?)[\d\-/]+(['"]?)\s*$""", re.M
)


def rewrite_confidence(text: str, new_conf: float,
                       bump_verified_to: dt.date | None = None) -> str | None:
    """Return new text with `confidence:` set and `verified:` bumped, or None.

    Why bump verified? Without it, every subsequent decay pass measures days_idle
    from the original `updated:` date, so weekly cron compounds decay instead of
    just applying the delta since last run. Bumping verified to `today` after
    each decay-apply makes the next pass measure only the new interval.
    """
    fm, _, span = parse_frontmatter(text)
    if not fm or span is None or "confidence" not in fm:
        return None
    new_text, n = _CONFIDENCE_REWRITE_RE.subn(
        lambda m: f"{m.group(1)}{m.group(2)}{new_conf:.2f}{m.group(3)}",
        text,
        count=1,
    )
    if n != 1:
        return None
    # If verified field exists, bump it to keep decay an incremental delta.
    if bump_verified_to is not None and "verified" in fm:
        date_str = bump_verified_to.isoformat()
        new_text2, n2 = _VERIFIED_REWRITE_RE.subn(
            lambda m: f"{m.group(1)}{m.group(2)}{date_str}{m.group(3)}",
            new_text, count=1,
        )
        if n2 == 1:
            new_text = new_text2
    elif bump_verified_to is not None and "verified" not in fm:
        # No verified field — inject one before the closing ---
        date_str = bump_verified_to.isoformat()
        new_text = new_text.replace(
            "\n---\n",
            f"\nverified: {date_str}\n---\n",
            1,
        )
    return new_text


# --- Date parse -----------------------------------------------------------

def _parse_date(s: str) -> dt.date | None:
    s = s.strip().strip('"').strip("'")
    if not s:
        return None
    for fmt in ("%Y-%m-%d", "%Y/%m/%d"):
        try:
            return dt.datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None


def latest_date(fm: dict[str, str], path: Path) -> dt.date:
    candidates = []
    for key in ("verified", "updated", "created"):
        v = fm.get(key)
        d = _parse_date(v) if v else None
        if d:
            candidates.append(d)
    if candidates:
        return max(candidates)
    # fall back to mtime
    return dt.date.fromtimestamp(path.stat().st_mtime)


# --- Protection ----------------------------------------------------------

def is_protected(fm: dict[str, str], path: Path, wiki_root: Path,
                 protected_types: set[str], protected_dirs: set[str],
                 evidence_threshold: int) -> tuple[bool, str]:
    typ = fm.get("type", "").strip().lower()
    if typ in protected_types:
        return True, f"type={typ}"
    if fm.get("protected", "").lower() in ("true", "yes", "1"):
        return True, "protected:true"
    try:
        ev = int(re.sub(r"[^\d]", "", fm.get("evidence_count", "0")) or "0")
    except ValueError:
        ev = 0
    if ev >= evidence_threshold:
        return True, f"evidence_count={ev}"
    try:
        rel = path.relative_to(wiki_root)
    except ValueError:
        rel = path
    for d in protected_dirs:
        if rel.parts and (rel.parts[0] == d or rel.name == d):
            return True, f"dir={d}"
    return False, ""


# --- Core ----------------------------------------------------------------

@dataclass
class PageResult:
    path: str
    type: str = ""
    old_confidence: float | None = None
    new_confidence: float | None = None
    days_idle: int = 0
    decay_factor: float = 1.0
    protected: bool = False
    protection_reason: str = ""
    error: str = ""

    @property
    def changed(self) -> bool:
        if self.protected or self.error:
            return False
        if self.old_confidence is None or self.new_confidence is None:
            return False
        return round(self.old_confidence, 2) != round(self.new_confidence, 2)


@dataclass
class RunReport:
    root: str
    halflife_days: float
    today: str
    apply: bool
    archive_threshold: float
    pages: list[PageResult] = field(default_factory=list)
    summary: dict[str, int] = field(default_factory=dict)
    archive_candidates: list[str] = field(default_factory=list)

    def finalize(self) -> None:
        changed = [p for p in self.pages if p.changed]
        self.summary = {
            "scanned": len(self.pages),
            "protected": sum(1 for p in self.pages if p.protected),
            "changed": len(changed),
            "errors": sum(1 for p in self.pages if p.error),
        }
        if self.archive_threshold > 0:
            self.archive_candidates = sorted(
                p.path for p in self.pages
                if not p.protected and p.new_confidence is not None
                and p.new_confidence < self.archive_threshold
            )


def find_wiki_root(start: Path) -> Path | None:
    if (start / "schema.md").exists() or (start / "L1_index.md").exists():
        return start
    cand = start / "wiki"
    if cand.exists():
        return cand
    return None


def decay_all(wiki_root: Path, halflife_days: float, today: dt.date,
              apply: bool, archive_threshold: float,
              protected_types: set[str], protected_dirs: set[str],
              evidence_threshold: int) -> RunReport:
    report = RunReport(
        root=str(wiki_root),
        halflife_days=halflife_days,
        today=today.isoformat(),
        apply=apply,
        archive_threshold=archive_threshold,
    )
    lam = lambda_from_halflife(halflife_days)

    for p in sorted(wiki_root.rglob("*.md")):
        rel_parts = p.relative_to(wiki_root).parts
        if any(part in SKIP_PARTS for part in rel_parts):
            continue
        res = PageResult(path=str(p.relative_to(wiki_root)))
        # Capture mtime BEFORE reading so the concurrent-write race window only
        # covers the read itself, not the entire decay-compute phase. Previous
        # code captured mtime after rewriting the temp file, by which point a
        # concurrent edit could have happened mid-compute and gone undetected.
        try:
            pre_mtime = p.stat().st_mtime
        except OSError as e:
            res.error = f"stat: {e}"
            report.pages.append(res)
            continue
        try:
            text = p.read_text(errors="ignore")
        except Exception as e:
            res.error = f"read: {e}"
            report.pages.append(res)
            continue
        fm, _, _ = parse_frontmatter(text)
        if not fm:
            continue  # silent skip — v1 / no-frontmatter pages
        res.type = fm.get("type", "")

        # confidence parsing
        if "confidence" not in fm:
            continue
        try:
            old = float(re.sub(r"[^\d.]", "", fm["confidence"]) or "0")
        except ValueError:
            res.error = f"bad confidence: {fm['confidence']!r}"
            report.pages.append(res)
            continue
        res.old_confidence = old

        # protection
        prot, why = is_protected(fm, p, wiki_root, protected_types,
                                  protected_dirs, evidence_threshold)
        if prot:
            res.protected = True
            res.protection_reason = why
            res.new_confidence = old  # unchanged
            res.days_idle = (today - latest_date(fm, p)).days
            res.decay_factor = 1.0
            report.pages.append(res)
            continue

        # decay
        last = latest_date(fm, p)
        days = max(0, (today - last).days)
        factor = math.exp(-lam * days)
        new = round(old * factor, 2)
        res.days_idle = days
        res.decay_factor = round(factor, 4)
        res.new_confidence = new

        if apply and res.changed:
            # bump verified to today so next decay pass measures delta, not total
            new_text = rewrite_confidence(text, new, bump_verified_to=today)
            if new_text is None:
                res.error = "rewrite failed (could not locate confidence field)"
            else:
                try:
                    # Atomic write: write to sibling temp + rename. Prevents the
                    # partial-write window where a concurrent reader sees half
                    # the file. Uses pre_mtime captured BEFORE the read so the
                    # race window covers read+compute+write, not just the write.
                    tmp = p.with_suffix(p.suffix + f".decay.{os.getpid()}.tmp")
                    tmp.write_text(new_text, encoding="utf-8")
                    current_mtime = p.stat().st_mtime
                    if current_mtime != pre_mtime:
                        tmp.unlink(missing_ok=True)
                        res.error = (
                            f"concurrent-write detected (mtime changed during decay); "
                            f"skipped to avoid clobbering"
                        )
                    else:
                        os.replace(tmp, p)
                        os.utime(p, (pre_mtime, pre_mtime))  # preserve mtime
                except Exception as e:
                    res.error = f"write: {e}"

        report.pages.append(res)

    report.finalize()
    return report


# --- Config --------------------------------------------------------------

def load_config(wiki_root: Path) -> dict:
    """Load memory_decay_config.yaml if present.

    PyYAML is preferred. Fallback parser ONLY handles scalar (k: v) values
    — nested keys (e.g. list/dict) are silently skipped with a stderr warning,
    NOT mis-parsed as strings. Callers should treat missing keys as "use default".
    """
    cfg_path = wiki_root / "memory_decay_config.yaml"
    if not cfg_path.exists():
        return {}
    try:
        import yaml  # type: ignore
        return yaml.safe_load(cfg_path.read_text()) or {}
    except ImportError:
        print(
            f"memory-decay: PyYAML not installed; nested config keys in "
            f"{cfg_path} will be ignored. Install pyyaml or use scalar-only config.",
            file=sys.stderr,
        )
        out: dict = {}
        for line in cfg_path.read_text().splitlines():
            line = line.split("#", 1)[0].rstrip()
            if not line or ":" not in line:
                continue
            # Skip indented lines (these belong to a nested key we can't parse)
            if line[0] in (" ", "\t"):
                continue
            k, _, v = line.partition(":")
            v = v.strip()
            # Only scalar values — skip block-list / block-dict starts
            if not v or v in ("[]", "{}", "|", ">"):
                continue
            if v.startswith(("[", "{")):
                continue
            out[k.strip()] = v
        return out


# --- CLI -----------------------------------------------------------------

def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="memory-decay")
    ap.add_argument("--root", default=".", help="wiki root or project root (auto-detects ./wiki)")
    ap.add_argument("--apply", action="store_true", help="rewrite frontmatter (default: dry-run)")
    ap.add_argument("--halflife-days", type=float, default=DEFAULT_HALFLIFE_DAYS)
    ap.add_argument("--archive-candidates", type=float, default=0.0,
                    help="list pages whose decayed confidence falls below this threshold")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--today", help="override today's date (YYYY-MM-DD), for testing")
    args = ap.parse_args(argv)

    start = Path(args.root).resolve()
    wiki_root = find_wiki_root(start)
    if not wiki_root:
        print(f"error: no wiki/ found at {start} (expected schema.md or L1_index.md, or ./wiki)", file=sys.stderr)
        return 2

    cfg = load_config(wiki_root)
    halflife = float(cfg.get("halflife_days", args.halflife_days))
    protected_types = set(cfg.get("protected_types", list(PROTECTED_TYPES)))
    protected_dirs = set(cfg.get("protected_dirs", list(PROTECTED_DIRS)))
    ev_threshold = int(cfg.get("evidence_count_threshold", EVIDENCE_PROTECT_THRESHOLD))

    today = _parse_date(args.today) if args.today else dt.date.today()
    if today is None:
        print(f"error: bad --today {args.today!r}", file=sys.stderr)
        return 2

    report = decay_all(
        wiki_root=wiki_root,
        halflife_days=halflife,
        today=today,
        apply=args.apply,
        archive_threshold=args.archive_candidates,
        protected_types=protected_types,
        protected_dirs=protected_dirs,
        evidence_threshold=ev_threshold,
    )

    if args.json:
        out = {
            "root": report.root,
            "halflife_days": report.halflife_days,
            "today": report.today,
            "apply": report.apply,
            "summary": report.summary,
            "archive_candidates": report.archive_candidates,
            "pages": [asdict(p) for p in report.pages if p.changed or p.error],
        }
        print(json.dumps(out, indent=2))
    else:
        mode = "APPLY" if args.apply else "DRY-RUN"
        print(f"memory-decay {mode}  root={report.root}  halflife={halflife:g}d  today={report.today}")
        print(f"  scanned: {report.summary['scanned']}  protected: {report.summary['protected']}  "
              f"changed: {report.summary['changed']}  errors: {report.summary['errors']}")
        for p in report.pages:
            if p.error:
                print(f"  ERR  {p.path}: {p.error}")
            elif p.protected and p.days_idle > 90:
                print(f"  pro  {p.path}  (idle {p.days_idle}d, {p.protection_reason})")
            elif p.changed:
                print(f"  dec  {p.path}  {p.old_confidence:.2f} → {p.new_confidence:.2f}  "
                      f"(idle {p.days_idle}d, ×{p.decay_factor:.3f})")
        if report.archive_candidates:
            print("archive candidates (confidence below threshold):")
            for path in report.archive_candidates:
                print(f"  arc  {path}")

    return 0 if report.summary["errors"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
