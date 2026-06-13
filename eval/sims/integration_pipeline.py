#!/usr/bin/env python3
"""End-to-end pipeline: candidate text → write-gate → wiki write → time-skip → decay.

Verifies cross-skill composition:
  1. write-gate REJECTS reasonless decisions (no wiki write happens).
  2. write-gate ACCEPTS reasoned decisions (page is written).
  3. After 365 simulated days, unprotected pages have decayed.
  4. Protected pages (errors, high-evidence) survive intact.
  5. cache-lint passes on the resulting wiki (no smells introduced).
"""
from __future__ import annotations

import datetime as dt
import json
import re
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "skills/write-gate/tools"))
sys.path.insert(0, str(REPO / "skills/wiki-memory/tools"))
sys.path.insert(0, str(REPO / "skills/cache-lint/tools"))

from write_gate import DEFAULT_THRESHOLD, decide, score_text  # noqa: E402
from decay import (  # noqa: E402
    DEFAULT_HALFLIFE_DAYS, EVIDENCE_PROTECT_THRESHOLD, PROTECTED_DIRS,
    PROTECTED_TYPES, decay_all,
)
from cache_lint import audit  # noqa: E402


@dataclass
class Candidate:
    title: str
    kind: str
    body: str
    expected_pass: bool
    is_protected: bool = False
    evidence_count: int = 0


CANDIDATES: list[Candidate] = [
    # Should pass and stay (protected by type)
    Candidate("postgres-deadlock-fix", "error",
              "Bug: race condition in queue worker — two consumers grabbed the same job because "
              "we forgot SELECT ... FOR UPDATE SKIP LOCKED. Fix: add the lock clause.",
              expected_pass=True, is_protected=True),

    # Should pass and decay
    Candidate("vector-index-architecture", "fact",
              "The vector index lives in PostgreSQL with pgvector extension. The schema stores "
              "384-dim embeddings in a 320MB index. Queries hit p50 at 12ms.",
              expected_pass=True, is_protected=False),

    # Should pass — decision with why-clause
    Candidate("pgvector-vs-qdrant", "decision",
              "We chose pgvector over Qdrant because dev parity matters and so that local == prod.",
              expected_pass=True, is_protected=False),

    # Should be REJECTED — decision without why-clause
    Candidate("language-choice", "decision",
              "We chose Rust over Go. Decision finalized in the Tuesday meeting.",
              expected_pass=False),

    # Should be REJECTED — pure filler
    Candidate("meta-recap", "fact",
              "Basically what we did was some database work. In summary, things happened.",
              expected_pass=False),

    # Should pass and stay (protected by evidence)
    Candidate("auth-flow-sop", "fact",
              "The auth flow runs on the gateway and calls oauth/token at /auth.\n"
              "Latency: 80ms p50, 250ms p99. Throughput: 5000 rps.\n",
              expected_pass=True, is_protected=True, evidence_count=5),
]


def make_page(c: Candidate) -> str:
    extra = f"evidence_count: {c.evidence_count}\n" if c.evidence_count else ""
    return (
        "---\n"
        "schema_version: 2\n"
        f"title: {c.title}\n"
        f"type: {c.kind}\n"
        "confidence: 0.85\n"
        f"updated: 2026-01-01\n"
        f"created: 2026-01-01\n"
        f"verified: 2026-01-01\n"
        f"{extra}"
        "---\n\n"
        f"# {c.title}\n\n{c.body}\n"
    )


def gate_decision(c: Candidate) -> bool:
    s = score_text(c.body, c.kind)
    ok, _ = decide(s, c.kind, DEFAULT_THRESHOLD, require_why=True)
    return ok


def run() -> dict:
    results = {"candidates": [], "decay_trajectory": {}, "cache_lint": {}}

    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        wiki = root / "wiki"
        wiki.mkdir()
        (wiki / "schema.md").write_text("schema\n")
        (wiki / "L2_facts").mkdir()
        (wiki / "L3_sops").mkdir()
        (root / "CLAUDE.md").write_text("# Project\n\n" + ("Rules. " * 500))

        # Phase 1: gate every candidate
        written: list[Candidate] = []
        for c in CANDIDATES:
            gate_passed = gate_decision(c)
            correct = gate_passed == c.expected_pass
            results["candidates"].append({
                "title": c.title,
                "kind": c.kind,
                "expected_pass": c.expected_pass,
                "actually_passed": gate_passed,
                "correct": correct,
            })
            if gate_passed:
                target_dir = wiki / "L2_facts"
                (target_dir / f"{c.title}.md").write_text(make_page(c))
                written.append(c)

        # Phase 2: snapshot confidence before decay
        before = {}
        for c in written:
            text = (wiki / "L2_facts" / f"{c.title}.md").read_text()
            m = re.search(r"^confidence:\s*([\d.]+)", text, re.M)
            before[c.title] = float(m.group(1))

        # Phase 3: simulate 1 full year of weekly decay
        for week in range(52):
            today = dt.date(2026, 1, 8) + dt.timedelta(weeks=week)
            decay_all(
                wiki_root=wiki, halflife_days=DEFAULT_HALFLIFE_DAYS,
                today=today, apply=True, archive_threshold=0.0,
                protected_types=PROTECTED_TYPES, protected_dirs=PROTECTED_DIRS,
                evidence_threshold=EVIDENCE_PROTECT_THRESHOLD,
            )

        # Phase 4: snapshot confidence after decay
        after = {}
        for c in written:
            text = (wiki / "L2_facts" / f"{c.title}.md").read_text()
            m = re.search(r"^confidence:\s*([\d.]+)", text, re.M)
            after[c.title] = float(m.group(1))

        # Trajectory verdicts
        for c in written:
            results["decay_trajectory"][c.title] = {
                "before": before[c.title],
                "after_52w": after[c.title],
                "protected": c.is_protected,
                # Protected pages must be unchanged; unprotected must drop ≥ 30%
                "behavior_correct":
                    (after[c.title] == before[c.title]) if c.is_protected
                    else (after[c.title] < before[c.title] * 0.7),
            }

        # Phase 5: cache-lint on the project root (CLAUDE.md was set up)
        lint_report = audit(root)
        results["cache_lint"] = {
            "n_targets": len(lint_report.targets),
            "FAIL": lint_report.summary["FAIL"],
            "WARN": lint_report.summary["WARN"],
        }

    # Verdicts
    gate_correct = sum(1 for r in results["candidates"] if r["correct"])
    trajectory_correct = sum(1 for v in results["decay_trajectory"].values() if v["behavior_correct"])
    results["summary"] = {
        "gate_correct": f"{gate_correct}/{len(results['candidates'])}",
        "trajectory_correct": f"{trajectory_correct}/{len(results['decay_trajectory'])}",
        "cache_lint_fails": results["cache_lint"]["FAIL"],
    }
    results["passed"] = (
        gate_correct == len(results["candidates"])
        and trajectory_correct == len(results["decay_trajectory"])
        and results["cache_lint"]["FAIL"] == 0
    )
    return results


def main() -> int:
    out = run()
    out_path = REPO / "eval/sims/results/integration_pipeline.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(out, indent=2))

    print("=== end-to-end integration: write-gate → wiki → memory-decay → cache-lint ===\n")
    print("PHASE 1 — gate decisions:")
    for r in out["candidates"]:
        mark = "ok" if r["correct"] else "FAIL"
        exp = "PASS" if r["expected_pass"] else "REJECT"
        act = "passed" if r["actually_passed"] else "rejected"
        print(f"  [{mark}] {r['title']:<35} expected={exp:<6} actual={act}")

    print(f"\nPHASE 2-4 — 52-week decay trajectory:")
    for title, v in out["decay_trajectory"].items():
        mark = "ok" if v["behavior_correct"] else "FAIL"
        prot = "protected" if v["protected"] else "unprotected"
        print(f"  [{mark}] {title:<35} {v['before']:.2f} → {v['after_52w']:.2f}  ({prot})")

    print(f"\nPHASE 5 — cache-lint on resulting project:")
    cl = out["cache_lint"]
    print(f"  targets={cl['n_targets']}  FAIL={cl['FAIL']}  WARN={cl['WARN']}")

    print(f"\nSUMMARY: {out['summary']}")
    print(f"OVERALL: {'PASSED' if out['passed'] else 'FAILED'}")
    print(f"\nfull JSON: {out_path}")
    return 0 if out["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
