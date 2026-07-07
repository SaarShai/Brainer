#!/usr/bin/env python3
"""Skill-corpus audit: cross-skill conflicts (#3) + instruction redundancy (#2).

Deterministic, stdlib-only. Two analyses over the SKILL.md bodies:

  --conflicts  Tag each skill's directive units on policy AXES (verbosity,
               planning, delegation, addition, evidence). Report pairs of skills
               that take OPPOSING positions on the same axis, quoting the lines.
               Flags whether a clashing skill self-qualifies (carve-out) and
               whether either side is ALWAYS-ON (output_style/hook) — those are
               the real runtime collisions, not merely textual ones.

  --redundancy Cross-skill near-duplicate directive detection (token-set
               Jaccard). A directive restated near-verbatim in 2+ bodies is a
               consolidation / inert-token candidate. Reports the duplicate
               clusters and their on-invocation token cost.

This SURFACES candidates with evidence; it does not auto-edit. Verdicts on
whether a flagged conflict is a true runtime collision, or a flagged duplicate
is genuinely inert, are made by a human/agent reading the quoted lines — the
prior false-positive lesson (a textual clash with a carve-out is not a bug).
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SKILLS = ROOT / "skills"

# Always-in-context bodies: caveman is output_style (resident from turn 1). The
# hooks (skill-pulse/compliance-canary/prompt-triage/context-keeper) are
# process-level, not prose-in-context, so they don't textually collide.
ALWAYS_ON = {"caveman-ultra"}

# Policy axes: pos vs neg keyword lexicons. Tight phrases only (NO `.*` spans —
# those matched across whole sentences and flagged skill *descriptions* of each
# other, the over-broad-regex defect this repo keeps fixing).
AXES = {
    "verbosity": {
        "pos": [r"\bterse\b", r"\bbe brief\b", r"\bconcise\b", r"prefer fragment", r"drop filler",
                r"keep (replies|it) short", r"fewer words"],
        # "elaborate" only in its VERB/output sense ("elaborate on X"); bare
        # "elaborate" is over-broad — it false-matched the ADJECTIVE ("elaborate
        # frontmatter / schema", i.e. config-complexity, not output verbosity).
        "neg": [r"\bbe thorough\b", r"\bcomprehensive\b", r"\belaborate (on|upon|further)\b",
                r"in[- ]depth", r"explain (fully|in detail)"],
    },
    "planning": {
        "pos": [r"plan first", r"plan before", r"design before (you )?(execut|implement|cod)",
                r"write a plan", r"plan the steps"],
        "neg": [r"skip the plan", r"don.?t over[- ]?plan", r"\bact now\b", r"avoid ceremony"],
    },
    "delegation": {
        "pos": [r"\bdelegate\b", r"spawn a sub-?agent", r"hand off to", r"dispatch to a"],
        "neg": [r"do it inline", r"do it yourself", r"avoid delegat", r"don.?t spawn", r"single context"],
    },
    "evidence": {
        "pos": [r"show .{0,12}evidence", r"quote .{0,18}(output|result)", r"paste .{0,12}output",
                r"evidence before", r"run .{0,12}verif"],
        "neg": [r"drop .{0,12}evidence", r"omit .{0,12}output", r"skip .{0,12}verif"],
    },
}

# Lines that describe ANOTHER skill (cross-references) are not self-directives —
# this, plus the tight no-`.*` lexicons, is what removes the false flags. A
# separate imperative-verb gate was tried and removed: it dropped valid
# directives ("Be thorough…") → vacuous "clean" verdicts (mutation-caught).
CROSSREF = re.compile(r"/SKILL\.md|\bsee\b[^.]*`[a-z-]+`|→ |routes to|flags this|\badopt", re.I)


def split_body(text: str) -> str:
    """Return body with YAML frontmatter stripped."""
    if text.startswith("---"):
        parts = text.split("\n---", 2)
        if len(parts) >= 2:
            # everything after the closing fence
            rest = text.split("---", 2)
            if len(rest) == 3:
                return rest[2]
    return text


def units(body: str) -> list[str]:
    """Directive-bearing units: non-empty, non-heading lines + sentences."""
    out: list[str] = []
    for raw in body.splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or line.startswith("```"):
            continue
        line = re.sub(r"^[-*\d.)\s]+", "", line)  # strip bullet/number markers
        if len(line) < 8:
            continue
        out.append(line)
    return out


def load_skills() -> dict[str, list[str]]:
    skills: dict[str, list[str]] = {}
    for d in sorted(SKILLS.iterdir()):
        sm = d / "SKILL.md"
        if not sm.is_file():
            continue
        body = split_body(sm.read_text(encoding="utf-8", errors="replace"))
        skills[d.name] = units(body)
    return skills


def tag_axes(unit_list: list[str]) -> dict[str, dict[str, list[str]]]:
    """{axis: {'pos':[quotes], 'neg':[quotes]}} for one skill. Only self-directive
    lines count (imperative, not a cross-reference to another skill)."""
    directives = [u for u in unit_list if not CROSSREF.search(u)]
    tags: dict[str, dict[str, list[str]]] = {}
    for axis, kw in AXES.items():
        pos = [u for u in directives if any(re.search(p, u, re.I) for p in kw["pos"])]
        neg = [u for u in directives if any(re.search(n, u, re.I) for n in kw["neg"])]
        if pos or neg:
            tags[axis] = {"pos": pos, "neg": neg}
    return tags


def analyze_conflicts(skills: dict[str, list[str]]) -> list[dict]:
    per = {name: tag_axes(u) for name, u in skills.items()}
    names = sorted(skills)
    findings: list[dict] = []
    for axis in AXES:
        pos_skills = {n for n in names if per[n].get(axis, {}).get("pos")}
        neg_skills = {n for n in names if per[n].get(axis, {}).get("neg")}
        for a in sorted(pos_skills):
            for b in sorted(neg_skills):
                if a == b:
                    continue
                always = bool({a, b} & ALWAYS_ON)
                # self-qualified = the pos skill ALSO states the neg (carve-out)
                a_carveout = bool(per[a].get(axis, {}).get("neg"))
                b_carveout = bool(per[b].get(axis, {}).get("pos"))
                findings.append({
                    "axis": axis,
                    "pos_skill": a, "neg_skill": b,
                    "always_on_involved": always,
                    "pos_has_carveout": a_carveout, "neg_has_carveout": b_carveout,
                    "risk": "high" if (always and not (a_carveout or b_carveout)) else
                            ("med" if always else "low"),
                    "pos_quote": per[a][axis]["pos"][0][:160],
                    "neg_quote": per[b][axis]["neg"][0][:160],
                })
    findings.sort(key=lambda f: {"high": 0, "med": 1, "low": 2}[f["risk"]])
    return findings


def _norm_tokens(s: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", s.lower()))


def analyze_redundancy(skills: dict[str, list[str]], thresh: float = 0.7) -> list[dict]:
    # Skip file-tree / code-comment boilerplate (├── └── │  install.sh # ...): it
    # is incidentally identical across skills but is not a directive.
    boiler = re.compile(r"[├└│]|^\S+\.\w+\s+#|^#|`{3}")
    # Skip pure canon-pointer lines: LEARNING_CONTRACT §1 mandates skills carry
    # POINTERS to _shared canon rather than restating it, so an identical
    # one-line link into LEARNING_CONTRACT.md/ORCHESTRATION.md appearing in N
    # skills is the sanctioned pattern, not a consolidation candidate. Only a
    # line that is essentially just the pointer is exempt — restated canon
    # PROSE around a link still counts toward redundancy.
    canon_ptr = re.compile(
        r"\(\.\./_shared/(?:LEARNING_CONTRACT|ORCHESTRATION)\.md[^)]*\)")
    def _is_pure_pointer(u: str) -> bool:
        return bool(canon_ptr.search(u)) and len(_norm_tokens(canon_ptr.sub("", u))) < 8
    items = [(name, u, _norm_tokens(u)) for name, uu in skills.items() for u in uu
             if len(_norm_tokens(u)) >= 5 and not boiler.search(u)
             and not _is_pure_pointer(u)]
    clusters: list[dict] = []
    used = set()
    for i in range(len(items)):
        if i in used:
            continue
        ni, ui, ti = items[i]
        group = [(ni, ui)]
        for j in range(i + 1, len(items)):
            if j in used:
                continue
            nj, uj, tj = items[j]
            if nj == ni:
                continue
            inter = len(ti & tj)
            union = len(ti | tj)
            if union and inter / union >= thresh:
                group.append((nj, uj))
                used.add(j)
        if len({g[0] for g in group}) >= 2:  # spans ≥2 distinct skills
            used.add(i)
            est_tokens = sum(len(u) for _, u in group[1:]) // 4  # dup cost (~4 ch/tok)
            clusters.append({
                "skills": sorted({g[0] for g in group}),
                "count": len(group),
                "dup_token_est": est_tokens,
                "samples": [f"[{n}] {u[:120]}" for n, u in group[:4]],
            })
    clusters.sort(key=lambda c: -c["dup_token_est"])
    return clusters


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--conflicts", action="store_true")
    ap.add_argument("--redundancy", action="store_true")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--check", action="store_true",
                    help="exit 1 if any conflict or near-duplicate directive is found "
                         "(standing regression guard; suite is currently clean)")
    args = ap.parse_args()
    if not (args.conflicts or args.redundancy):
        args.conflicts = args.redundancy = True

    skills = load_skills()
    out: dict = {"n_skills": len(skills)}
    if args.conflicts:
        out["conflicts"] = analyze_conflicts(skills)
    if args.redundancy:
        out["redundancy"] = analyze_redundancy(skills)

    if args.json:
        print(json.dumps(out, indent=2))
        return 0

    if args.conflicts:
        print(f"=== CROSS-SKILL CONFLICTS (axes over {len(skills)} skills) ===")
        for f in out["conflicts"]:
            print(f"[{f['risk'].upper():4}] {f['axis']}: {f['pos_skill']}(+) vs {f['neg_skill']}(-)"
                  f"  always_on={f['always_on_involved']} carveout={f['pos_has_carveout'] or f['neg_has_carveout']}")
            print(f"        +{f['pos_skill']}: {f['pos_quote']}")
            print(f"        -{f['neg_skill']}: {f['neg_quote']}")
    if args.redundancy:
        print(f"\n=== CROSS-SKILL DIRECTIVE REDUNDANCY (Jaccard≥0.7) ===")
        if not out["redundancy"]:
            print("  none above threshold")
        for c in out["redundancy"]:
            print(f"  ~{c['dup_token_est']} dup tok  across {c['skills']} (x{c['count']})")
            for s in c["samples"]:
                print(f"      {s}")

    if args.check:
        n_conf = len(out.get("conflicts", []))
        n_dup = len(out.get("redundancy", []))
        if n_conf or n_dup:
            print(f"\nskill-audit: FAIL — {n_conf} conflict(s), {n_dup} duplicate cluster(s)")
            return 1
        print("\nskill-audit: clean (0 conflicts, 0 duplicate directives)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
