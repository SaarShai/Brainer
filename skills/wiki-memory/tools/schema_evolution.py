#!/usr/bin/env python3
"""schema_evolution — turn RECURRING write failures into PROPOSED schema/template
amendments. The autonomous version of Karpathy's "the human's primary job is
refining the schema": instead of fixing the same defect page-by-page forever, a
recurring defect class becomes a proposed rule change to `schema.md` / the page
templates so future writes don't reproduce it.

Signal source = the wiki's own `lint --strict` warning histogram (always available)
plus an optional append-only reject log at `<root>/.brainer/schema_signals.jsonl`
(one JSON object per line with a `code` key — e.g. write-gate rejections logged by
the caller). A defect class that recurs at/above the threshold (default 3 — the
codebase's rule-of-three) yields one proposal.

REPORT-ONLY by hard rule: this NEVER edits `schema.md`. `schema.md` is a canonical
contract co-owned by human + agent; an autonomous agent may *propose* an amendment
(with evidence) but a human approves and applies it. That gate is what keeps the
loop from silently rewriting its own rules — the same separation `write-gate` and
the trust tiers enforce for facts.

Run:  python3 skills/wiki-memory/tools/wiki.py --root <wiki> schema-evolution
 or:  python3 skills/wiki-memory/tools/schema_evolution.py --root <wiki>
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

DEFAULT_THRESHOLD = 3  # rule of three: fix once, fix twice, on the third change the rule

# lint warning code -> (proposed schema/template amendment, target schema section)
REMEDIATION: dict[str, tuple[str, str]] = {
    "missing_provenance": (
        "Require a non-empty `sources:` on every non-raw page; add a sources prompt "
        "to the page template so the field is filled at creation.",
        "Frontmatter v2 / page template",
    ),
    "missing_trigger_cue": (
        "Require a `Trigger / symptom:` body line on every error/lesson/sop page; bake "
        "it into those templates (search indexes the body, not frontmatter).",
        "Page types / templates",
    ),
    "trigger_in_frontmatter_only": (
        "Forbid a symptom that lives only in a frontmatter key; the retrieval cue must "
        "be in the body. State this in the page-type rules.",
        "Page types",
    ),
    "missing_backlinks": (
        "Require >=1 wikilink on every new page; seed a `Related:` stub in the templates "
        "so a page is never created orphaned.",
        "Write protocol / templates",
    ),
    "orphan": (
        "After creating a page, add a backlink FROM a related page; make linking-in a "
        "required step in the write protocol, not optional.",
        "Write protocol",
    ),
    "duplicate_title": (
        "Run `overlap` before `new` and treat high overlap as update-not-create; "
        "strengthen the dedup-before-write step in the schema.",
        "Write protocol",
    ),
    "legacy_frontmatter_v1": (
        "Migrate remaining v1 pages to v2 and sanction only v2 templates for new pages; "
        "name v1 as deprecated in the schema.",
        "Frontmatter v2",
    ),
    "stale_verified": (
        "Name a max `verified:` age before a page must be re-checked, and schedule decay/"
        "refresh; encode the cadence in the schema.",
        "Aging & reconcile",
    ),
    "hub_gravity_well": (
        "Add an inbound-link cap convention and a split-the-hub rule so junk-drawer pages "
        "are broken up.",
        "Lint / conventions",
    ),
}


def propose_amendments(signal_counts: dict[str, int],
                       threshold: int = DEFAULT_THRESHOLD) -> list[dict[str, Any]]:
    """Pure: recurring defect classes -> proposed schema amendments. Report-only.

    A class at/above `threshold` yields one proposal. Classes with no canned
    remediation are still surfaced (recurring, needs manual review) so nothing is
    silently dropped. Never returns an 'apply' action — proposals only.
    """
    out: list[dict[str, Any]] = []
    for code, count in sorted(signal_counts.items(), key=lambda kv: (-kv[1], kv[0])):
        if count < threshold:
            continue
        rem = REMEDIATION.get(code)
        if rem is None:
            out.append({
                "defect_class": code, "count": count,
                "proposed_rule": None, "target_section": None,
                "note": "recurring defect with no canned remediation — review manually",
            })
            continue
        rule, section = rem
        out.append({
            "defect_class": code, "count": count,
            "proposed_rule": rule, "target_section": section,
        })
    return out


def collect_signals(root: str | Path) -> dict[str, int]:
    """Build the defect-class histogram from `lint --strict` warnings + an optional
    persisted reject log (`<root>/.brainer/schema_signals.jsonl`)."""
    from wiki import WikiStore  # sibling module
    counts: dict[str, int] = {}
    try:
        report = WikiStore(root).lint_pages(strict=True)
        for w in report.get("warnings", []):
            code = w.get("code")
            if code and code != "contradiction":  # contradiction is content, not a write-defect class
                counts[code] = counts.get(code, 0) + 1
    except Exception:
        pass
    log = Path(root) / ".brainer" / "schema_signals.jsonl"
    if log.exists():
        for line in log.read_text(encoding="utf-8", errors="replace").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                code = json.loads(line).get("code")
            except (ValueError, AttributeError):
                continue
            if code:
                counts[code] = counts.get(code, 0) + 1
    return counts


def run(root: str | Path, threshold: int = DEFAULT_THRESHOLD) -> dict[str, Any]:
    signals = collect_signals(root)
    proposals = propose_amendments(signals, threshold=threshold)
    return {
        "proposals": proposals,
        "threshold": threshold,
        "signals_scanned": signals,
        "applied": False,
        "note": ("REPORT-ONLY: proposals amend schema.md / templates only after a HUMAN "
                 "approves them — never auto-applied (schema.md is a canonical contract). "
                 "0 proposals = no recurring write-defect class crossed the threshold."),
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="schema-evolution", description=__doc__)
    ap.add_argument("--root", default="wiki", help="Wiki root (default ./wiki).")
    ap.add_argument("--threshold", type=int, default=DEFAULT_THRESHOLD,
                    help=f"Min recurrences to propose an amendment (default {DEFAULT_THRESHOLD}).")
    ap.add_argument("--json", action="store_true", help="Full JSON (default: same).")
    args = ap.parse_args(argv)
    print(json.dumps(run(args.root, threshold=args.threshold), indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
