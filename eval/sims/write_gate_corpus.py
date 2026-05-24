#!/usr/bin/env python3
"""write-gate corpus calibration.

Two passes:
  1. REAL corpus — every page in wiki/ (Token Economy's own). Reports per-kind
     score distribution + acceptance rate. No labels; just calibration.
  2. ADVERSARIAL labeled corpus — 30 hand-curated should-pass / should-reject
     pairs. Reports accuracy, precision, recall, FP and FN cases.

Output: eval/sims/results/write_gate_corpus.json + console summary.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "skills/write-gate/tools"))
from write_gate import DEFAULT_THRESHOLD, decide, score_text  # noqa: E402


# --- 1. Real corpus pass --------------------------------------------------

def parse_frontmatter(text: str) -> dict[str, str]:
    if not text.startswith("---"):
        return {}
    end = text.find("\n---\n", 4)
    if end < 0:
        return {}
    fm: dict[str, str] = {}
    for line in text[4:end].splitlines():
        if ":" in line:
            k, _, v = line.partition(":")
            fm[k.strip()] = v.strip()
    return fm


def kind_from_frontmatter(fm: dict[str, str]) -> str:
    t = fm.get("type", "").lower()
    if t in ("decision",): return "decision"
    if t in ("error", "lesson"): return "error"
    if t in ("procedure", "sop", "pattern"): return "sop"
    return "fact"


def run_real_corpus() -> dict:
    wiki = REPO / "wiki"
    rows = []
    for p in sorted(wiki.rglob("*.md")):
        try:
            text = p.read_text(errors="ignore")
        except Exception as e:
            continue
        fm = parse_frontmatter(text)
        kind = kind_from_frontmatter(fm)
        body = text[text.find("\n---\n", 4) + 5:] if fm else text
        s = score_text(body, kind)
        ok, _ = decide(s, kind, DEFAULT_THRESHOLD, require_why=True)
        rows.append({
            "path": str(p.relative_to(wiki)),
            "kind": kind,
            "score": round(s.total, 2),
            "has_why": s.has_why,
            "passed": ok,
            "size": len(body),
        })
    # buckets
    by_kind: dict[str, dict[str, int]] = {}
    for r in rows:
        b = by_kind.setdefault(r["kind"], {"n": 0, "pass": 0, "score_sum": 0.0})
        b["n"] += 1
        b["pass"] += int(r["passed"])
        b["score_sum"] += r["score"]
    summary = {
        k: {
            "n": v["n"],
            "acceptance_rate": round(v["pass"] / v["n"], 3) if v["n"] else 0.0,
            "mean_score": round(v["score_sum"] / v["n"], 2) if v["n"] else 0.0,
        } for k, v in by_kind.items()
    }
    return {
        "n_pages": len(rows),
        "overall_acceptance": round(sum(r["passed"] for r in rows) / max(1, len(rows)), 3),
        "by_kind": summary,
        "rows": rows,
    }


# --- 2. Adversarial labeled corpus ---------------------------------------

LABELED: list[tuple[str, str, bool, str]] = [
    # (kind, text, expected_pass, label)

    # --- DECISIONS — should PASS (with why-clause) ---
    ("decision",
     "We chose pgvector over Qdrant because dev parity matters and so that local == prod.",
     True, "pos_decision_with_why_1"),
    ("decision",
     "Decision: adopted Rust for the ingest path to avoid GIL contention on the parsing loop.",
     True, "pos_decision_with_why_2"),
    ("decision",
     # Note: 'since' deliberately not relied on as causal — corpus reflects what
     # real authors write when they mean causal ("because"). See write_gate.py
     # comment on WHY_CLAUSES for the temporal-since rationale.
     "We're going with Postgres LISTEN/NOTIFY because Kafka is overkill for 50 events/sec.",
     True, "pos_decision_with_why_3"),
    ("decision",
     "Chose React Query over SWR because we already have its retry semantics in our test harness.",
     True, "pos_decision_with_why_4"),
    ("decision",
     "Settled on Fly.io rather than Render in order to avoid the cold-start tax on burst traffic.",
     True, "pos_decision_with_why_5"),

    # --- DECISIONS — should REJECT (no why-clause) ---
    ("decision",
     "We chose pgvector over Qdrant. Decision finalized in the Tuesday meeting.",
     False, "neg_decision_no_why_1"),
    ("decision",
     "Going with Rust for ingest. Rejected Python and Go.",
     False, "neg_decision_no_why_2"),
    ("decision",
     "We picked TypeScript over JavaScript. Done.",
     False, "neg_decision_no_why_3"),
    ("decision",
     "Decision: use Tailwind. Convention: never inline styles.",
     False, "neg_decision_no_why_4"),

    # --- FACTS — should PASS (signal-rich) ---
    ("fact",
     "The ingest worker lives in services/ingest/ and calls the embedding API at /embed.\n"
     "```python\nresult = embed(chunk)\n```\nLatency: 120ms p50, 450ms p99.",
     True, "pos_fact_arch_code_numbers"),
    ("fact",
     "Bug: deploy failed because PG_URL was unset in production env.\n"
     "Fix: added to vault and reloaded systemd unit.\n"
     "Root cause: env was set in .envrc which doesn't apply to systemd.",
     True, "pos_fact_concrete_failure"),
    ("fact",
     "The vector index lives in PostgreSQL with pgvector extension. The schema "
     "stores 384-dim embeddings in a 320MB index. Queries hit p50 at 12ms.",
     True, "pos_fact_arch_with_numbers"),
    ("error",
     "Bug: race condition in the queue worker — two consumers grabbed the same job\n"
     "because we forgot SELECT ... FOR UPDATE SKIP LOCKED. Fix: add the lock clause.",
     True, "pos_error_concrete"),
    ("sop",
     "To debug a stuck migration:\n1. Run `select * from pg_stat_activity where state='active'`.\n"
     "2. If a lock is held, find the blocker with `pg_blocking_pids()`.\n"
     "3. Cancel the blocker with `pg_cancel_backend(pid)`.",
     True, "pos_sop_concrete_procedure"),

    # --- FACTS — should REJECT (filler / speculation / thin) ---
    ("fact",
     "Basically what we did was some database work. In summary, things happened.",
     False, "neg_fact_pure_filler"),
    ("fact",
     "Maybe we should probably use Redis. I think it could work. Perhaps we'll try it.",
     False, "neg_fact_pure_speculation"),
    ("fact",
     "We did stuff yesterday.",
     False, "neg_fact_trivial_recap"),
    ("fact",
     "TL;DR: anyway, long story short, basically the thing worked out.",
     False, "neg_fact_only_meta"),
    ("fact",
     "It might be possible that the cache could maybe help us probably. Seems like a good idea.",
     False, "neg_fact_pure_uncertainty"),

    # --- MIXED — borderline cases (labels reflect ideal behavior) ---
    ("fact",
     "Migration ran in 14s. Index is 320MB. Reads are 12ms p50.",
     False, "neg_metrics_only_log_entry"),
    ("decision",
     "We're using PostgreSQL because we already have it deployed and operations knows it well.",
     True, "pos_decision_pragmatic_why"),
    ("fact",
     "Embeddings are produced by services/embed/worker.py which reads from kafka topic 'docs' "
     "and writes to the pgvector index. Throughput: 2000 docs/min on a single 4-core worker.",
     True, "pos_fact_pipeline_description"),

    # --- ADVERSARIAL — looks like signal but is filler ---
    ("decision",
     "We chose, in summary, basically, to do the thing. Decision: yes. Convention: probably.",
     False, "neg_adversarial_decisions_words_only"),
    ("fact",
     "The system might possibly maybe run on AWS or perhaps GCP. I think it could be either.",
     False, "neg_adversarial_arch_words_but_speculation"),

    # --- ADVERSARIAL — looks thin but has actual signal ---
    ("error",
     "Fix: bumped timeout from 5s to 30s. Root cause: cold-start in lambda.",
     True, "pos_short_but_concrete_fix"),
    ("decision",
     "Adopted ESLint to avoid the styling debates that ate the last sprint.",
     True, "pos_short_decision_with_why"),

    # --- HIGH-SCORE TRAPS — should still pass ---
    ("fact",
     "The Postgres replica runs on db-replica-01.prod and lags primary by ~30ms p99. "
     "The lag is measured by the lag_seconds metric scraped every 15s. We page on lag > 5s.",
     True, "pos_fact_high_signal_with_numbers"),

    # --- LOW-SCORE TRAPS — should be rejected even with one buzzword ---
    ("fact",
     "Failed.",
     False, "neg_one_word_no_signal"),
    ("fact",
     "Decision: TBD.",
     False, "neg_decision_marker_but_empty"),
]


def run_labeled() -> dict:
    results = []
    tp = tn = fp = fn = 0
    for kind, text, expected, label in LABELED:
        s = score_text(text, kind)
        actual, verdict = decide(s, kind, DEFAULT_THRESHOLD, require_why=True)
        correct = actual == expected
        if expected and actual:    tp += 1
        if not expected and not actual: tn += 1
        if not expected and actual: fp += 1
        if expected and not actual: fn += 1
        results.append({
            "label": label, "kind": kind,
            "expected": expected, "actual": actual, "correct": correct,
            "score": round(s.total, 2), "has_why": s.has_why,
            "text_preview": text[:80] + ("…" if len(text) > 80 else ""),
            "verdict": verdict,
        })
    n = len(LABELED)
    precision = tp / max(1, tp + fp)
    recall = tp / max(1, tp + fn)
    return {
        "n": n,
        "accuracy": round((tp + tn) / n, 3),
        "precision": round(precision, 3),
        "recall": round(recall, 3),
        "f1": round(2 * precision * recall / max(1e-9, precision + recall), 3),
        "tp": tp, "tn": tn, "fp": fp, "fn": fn,
        "wrong": [r for r in results if not r["correct"]],
        "all": results,
    }


# --- main ----------------------------------------------------------------

def main() -> int:
    t0 = time.time()
    real = run_real_corpus()
    labeled = run_labeled()
    elapsed = round(time.time() - t0, 3)

    out = {
        "threshold": DEFAULT_THRESHOLD,
        "elapsed_s": elapsed,
        "real_corpus": real,
        "labeled_corpus": labeled,
    }

    out_path = REPO / "eval/sims/results/write_gate_corpus.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(out, indent=2))

    # console summary
    print(f"=== write-gate corpus calibration (threshold={DEFAULT_THRESHOLD}, t={elapsed}s) ===\n")
    print(f"REAL CORPUS — {real['n_pages']} wiki pages")
    print(f"  overall acceptance: {real['overall_acceptance']:.1%}")
    for kind, stats in sorted(real["by_kind"].items()):
        print(f"  {kind:>8}: n={stats['n']:>3}  accept={stats['acceptance_rate']:.1%}  mean_score={stats['mean_score']:.2f}")

    print(f"\nLABELED CORPUS — {labeled['n']} cases")
    print(f"  accuracy:  {labeled['accuracy']:.1%}")
    print(f"  precision: {labeled['precision']:.1%}")
    print(f"  recall:    {labeled['recall']:.1%}")
    print(f"  F1:        {labeled['f1']:.1%}")
    print(f"  TP={labeled['tp']}  TN={labeled['tn']}  FP={labeled['fp']}  FN={labeled['fn']}")
    if labeled["wrong"]:
        print(f"\nMISCLASSIFICATIONS ({len(labeled['wrong'])}):")
        for w in labeled["wrong"]:
            arrow = "fp" if w["actual"] else "fn"
            print(f"  [{arrow}] {w['label']:<40}  score={w['score']:.2f}  why={w['has_why']}")
            print(f"       {w['text_preview']}")

    print(f"\nfull JSON: {out_path}")
    # exit 1 if labeled accuracy under target
    return 0 if labeled["accuracy"] >= 0.85 else 1


if __name__ == "__main__":
    sys.exit(main())
