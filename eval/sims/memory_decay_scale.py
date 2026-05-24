#!/usr/bin/env python3
"""memory-decay scale + correctness simulation.

Two passes:
  1. SCALE — generate synthetic wikis of N=10/100/1000/10000 pages, measure
     decay-pass runtime + per-page cost. Verifies linear scaling.
  2. CORRECTNESS — simulate 12 months of weekly decay on a small wiki, verify
     that confidences match the closed-form solution exactly and that
     protected pages stay flat.
"""
from __future__ import annotations

import datetime as dt
import json
import math
import sys
import tempfile
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "skills/memory-decay/tools"))
from decay import (  # noqa: E402
    DEFAULT_HALFLIFE_DAYS, EVIDENCE_PROTECT_THRESHOLD, PROTECTED_DIRS,
    PROTECTED_TYPES, decay_all, lambda_from_halflife,
)


def make_page(title: str, conf: float, updated: str, type_: str = "fact",
              evidence_count: int = 0) -> str:
    return (
        "---\n"
        "schema_version: 2\n"
        f"title: {title}\n"
        f"type: {type_}\n"
        f"confidence: {conf:.2f}\n"
        f"updated: {updated}\n"
        f"created: {updated}\n"
        + (f"evidence_count: {evidence_count}\n" if evidence_count else "")
        + "---\n\n# body\n"
    )


# --- Scale pass -----------------------------------------------------------

def make_wiki(root: Path, n: int) -> None:
    root.mkdir(parents=True, exist_ok=True)
    (root / "schema.md").write_text("schema\n")
    (root / "L2_facts").mkdir(exist_ok=True)
    (root / "L3_sops").mkdir(exist_ok=True)
    for i in range(n):
        # 80% fact, 10% error (protected), 10% in L3_sops (protected by dir)
        bucket = i % 10
        if bucket < 8:
            p = root / "L2_facts" / f"fact-{i:06d}.md"
            p.write_text(make_page(f"F{i}", 0.5 + (i % 5) * 0.1, "2024-01-01", "fact"))
        elif bucket == 8:
            p = root / "L2_facts" / f"error-{i:06d}.md"
            p.write_text(make_page(f"E{i}", 0.9, "2024-01-01", "error"))
        else:
            p = root / "L3_sops" / f"sop-{i:06d}.md"
            p.write_text(make_page(f"S{i}", 0.9, "2024-01-01", "procedure"))


def run_scale() -> dict:
    sizes = [10, 100, 1000, 10000]
    rows = []
    for n in sizes:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "wiki"
            make_wiki(root, n)
            today = dt.date(2026, 1, 1)
            t0 = time.time()
            report = decay_all(
                wiki_root=root, halflife_days=DEFAULT_HALFLIFE_DAYS,
                today=today, apply=False, archive_threshold=0.0,
                protected_types=PROTECTED_TYPES, protected_dirs=PROTECTED_DIRS,
                evidence_threshold=EVIDENCE_PROTECT_THRESHOLD,
            )
            t_dry = time.time() - t0

            t0 = time.time()
            decay_all(
                wiki_root=root, halflife_days=DEFAULT_HALFLIFE_DAYS,
                today=today, apply=True, archive_threshold=0.0,
                protected_types=PROTECTED_TYPES, protected_dirs=PROTECTED_DIRS,
                evidence_threshold=EVIDENCE_PROTECT_THRESHOLD,
            )
            t_apply = time.time() - t0

            rows.append({
                "n": n,
                "dry_ms": int(t_dry * 1000),
                "apply_ms": int(t_apply * 1000),
                "us_per_page_dry": round(t_dry * 1e6 / n, 1),
                "us_per_page_apply": round(t_apply * 1e6 / n, 1),
                "n_scanned": report.summary["scanned"],
                "n_protected": report.summary["protected"],
                "n_changed": report.summary["changed"],
                "n_errors": report.summary["errors"],
            })
    # Check linearity: us/page should be roughly constant across sizes.
    # Threshold is generous because small-N is FS-cache-bound (sub-ms timer noise
    # turns 50μs into 200μs and we'd false-fail on a flaky CI host).
    # If you suspect a real O(n²) regression, look at the n=10000 row alone.
    us_per_page = [r["us_per_page_dry"] for r in rows]
    ratio = max(us_per_page) / max(1e-9, min(us_per_page))
    linear = ratio < 8
    return {"rows": rows, "us_per_page_ratio": round(ratio, 2), "appears_linear": linear}


# --- Correctness pass -----------------------------------------------------

def run_correctness() -> dict:
    """Verify per-page decay = exp(-λ × days) exactly, and protected pages stay flat."""
    with tempfile.TemporaryDirectory() as td:
        root = Path(td) / "wiki"
        root.mkdir(parents=True, exist_ok=True)
        (root / "schema.md").write_text("schema\n")
        (root / "L2_facts").mkdir()

        cases = [
            ("fact-old.md", 0.9, "2024-01-01", "fact", 0),         # decays
            ("fact-recent.md", 0.9, "2025-12-01", "fact", 0),       # mild decay
            ("error-old.md", 0.9, "2024-01-01", "error", 0),        # protected
            ("cited-old.md", 0.9, "2024-01-01", "fact", 5),         # protected by evidence
        ]
        for fn, c, u, t, e in cases:
            (root / "L2_facts" / fn).write_text(make_page(fn, c, u, t, e))

        today = dt.date(2026, 1, 1)
        lam = lambda_from_halflife(DEFAULT_HALFLIFE_DAYS)
        expected = {}
        for fn, c, u, t, e in cases:
            d = (today - dt.date.fromisoformat(u)).days
            if t in PROTECTED_TYPES or e >= EVIDENCE_PROTECT_THRESHOLD:
                expected[fn] = round(c, 2)  # unchanged
            else:
                expected[fn] = round(c * math.exp(-lam * d), 2)

        report = decay_all(
            wiki_root=root, halflife_days=DEFAULT_HALFLIFE_DAYS,
            today=today, apply=True, archive_threshold=0.0,
            protected_types=PROTECTED_TYPES, protected_dirs=PROTECTED_DIRS,
            evidence_threshold=EVIDENCE_PROTECT_THRESHOLD,
        )
        # Read back actual values
        actual = {}
        for fn in [c[0] for c in cases]:
            text = (root / "L2_facts" / fn).read_text()
            # parse the confidence line
            import re as _re
            m = _re.search(r"^confidence:\s*([\d.]+)", text, _re.M)
            actual[fn] = float(m.group(1)) if m else None

        mismatches = []
        for fn, exp in expected.items():
            if actual[fn] != exp:
                mismatches.append({"page": fn, "expected": exp, "actual": actual[fn]})

        return {
            "n_pages": len(cases),
            "expected": expected,
            "actual": actual,
            "mismatches": mismatches,
            "all_correct": not mismatches,
        }


# --- 12-month weekly simulation -----------------------------------------

def run_trajectory() -> dict:
    """Simulate weekly decay over 12 months. Track confidence trajectories."""
    with tempfile.TemporaryDirectory() as td:
        root = Path(td) / "wiki"
        root.mkdir(parents=True, exist_ok=True)
        (root / "schema.md").write_text("schema\n")
        (root / "L2_facts").mkdir()

        # 3 pages: fresh fact, fresh error (protected), fresh cited (protected)
        (root / "L2_facts" / "fact.md").write_text(make_page("F", 0.9, "2026-01-01", "fact"))
        (root / "L2_facts" / "error.md").write_text(make_page("E", 0.9, "2026-01-01", "error"))
        (root / "L2_facts" / "cited.md").write_text(make_page("C", 0.9, "2026-01-01", "fact", evidence_count=5))

        start = dt.date(2026, 1, 8)
        trajectory: dict[str, list[float]] = {"fact.md": [], "error.md": [], "cited.md": []}
        for week in range(52):
            today = start + dt.timedelta(weeks=week)
            decay_all(
                wiki_root=root, halflife_days=DEFAULT_HALFLIFE_DAYS,
                today=today, apply=True, archive_threshold=0.0,
                protected_types=PROTECTED_TYPES, protected_dirs=PROTECTED_DIRS,
                evidence_threshold=EVIDENCE_PROTECT_THRESHOLD,
            )
            for fn in trajectory:
                text = (root / "L2_facts" / fn).read_text()
                import re as _re
                m = _re.search(r"^confidence:\s*([\d.]+)", text, _re.M)
                trajectory[fn].append(float(m.group(1)) if m else 0.0)

        return {
            "weeks": 52,
            "final": {fn: t[-1] for fn, t in trajectory.items()},
            "fact_decayed": trajectory["fact.md"][-1] < 0.9,
            "error_unchanged": trajectory["error.md"][-1] == 0.9,
            "cited_unchanged": trajectory["cited.md"][-1] == 0.9,
            # NB: After updating frontmatter, `updated:` field is unchanged
            # because decay only rewrites `confidence:`. So days_idle keeps
            # growing on the same baseline; trajectory should be exp.
            "trajectory_samples": {
                fn: [t[0], t[12], t[26], t[51]]  # weeks 1, 13, 27, 52
                for fn, t in trajectory.items()
            },
        }


def main() -> int:
    print("=== memory-decay scale + correctness ===\n")
    scale = run_scale()
    print("SCALE:")
    for r in scale["rows"]:
        print(f"  n={r['n']:>6}  dry={r['dry_ms']:>5}ms  apply={r['apply_ms']:>5}ms  "
              f"per-page={r['us_per_page_dry']:>6.1f}μs  "
              f"({r['n_changed']} changed, {r['n_protected']} protected)")
    print(f"  per-page ratio across sizes: {scale['us_per_page_ratio']}× "
          f"({'linear' if scale['appears_linear'] else 'NON-LINEAR'})")

    corr = run_correctness()
    print(f"\nCORRECTNESS ({corr['n_pages']} pages, vs closed-form exp(-λd)):")
    for fn in corr["expected"]:
        marker = "ok" if corr["actual"][fn] == corr["expected"][fn] else "FAIL"
        print(f"  [{marker}] {fn:<20}  expected={corr['expected'][fn]:.2f}  actual={corr['actual'][fn]:.2f}")
    if corr["mismatches"]:
        print("  MISMATCHES:", corr["mismatches"])

    traj = run_trajectory()
    print(f"\nTRAJECTORY (52 weekly decay passes):")
    print(f"  fact (unprotected)  final={traj['final']['fact.md']:.2f}  decayed={traj['fact_decayed']}")
    print(f"  error (protected)   final={traj['final']['error.md']:.2f}  unchanged={traj['error_unchanged']}")
    print(f"  cited (protected)   final={traj['final']['cited.md']:.2f}  unchanged={traj['cited_unchanged']}")
    for fn, samples in traj["trajectory_samples"].items():
        print(f"  {fn:<20}  weeks 1,13,27,52 → {samples}")

    out = {"scale": scale, "correctness": corr, "trajectory": traj}
    out_path = REPO / "eval/sims/results/memory_decay_scale.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(out, indent=2))
    print(f"\nfull JSON: {out_path}")

    failures = (
        (0 if scale["appears_linear"] else 1)
        + (0 if corr["all_correct"] else 1)
        + (0 if traj["fact_decayed"] and traj["error_unchanged"] and traj["cited_unchanged"] else 1)
    )
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
