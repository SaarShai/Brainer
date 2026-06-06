#!/usr/bin/env python3
"""Generate eval/exp3_classifiers/write_gate_labeled.jsonl.

40-60 labeled {text, kind, label: keep|reject, why, source} cases for the
write-gate keep-vs-reject discrimination eval.

  - SEED cases come from eval/sims/write_gate_corpus.py LABELED (29 cases) so
    we reuse the project's calibrated adversarial set.
  - NEW cases extend coverage: more real durable facts/decisions/errors/
    architecture WITH causal why-clauses (positives), and more filler /
    speculation / trivial-lookup / reasonless-decision / duplicate negatives,
    plus adversarial near-misses (decision missing its because → reject;
    borderline-signal fact right at the threshold).

label == "keep"   ⇔ should PASS the gate
label == "reject" ⇔ should be REJECTED by the gate
"""
from __future__ import annotations

import json
from pathlib import Path

# --- SEED: harvested verbatim from eval/sims/write_gate_corpus.py LABELED ----
# (kind, text, expected_pass, label) → re-tagged with label/why/source.
SEED = [
    ("decision", "We chose pgvector over Qdrant because dev parity matters and so that local == prod.", True, "pos_decision_with_why_1"),
    ("decision", "Decision: adopted Rust for the ingest path to avoid GIL contention on the parsing loop.", True, "pos_decision_with_why_2"),
    ("decision", "We're going with Postgres LISTEN/NOTIFY because Kafka is overkill for 50 events/sec.", True, "pos_decision_with_why_3"),
    ("decision", "Chose React Query over SWR because we already have its retry semantics in our test harness.", True, "pos_decision_with_why_4"),
    ("decision", "Settled on Fly.io rather than Render in order to avoid the cold-start tax on burst traffic.", True, "pos_decision_with_why_5"),
    ("decision", "We chose pgvector over Qdrant. Decision finalized in the Tuesday meeting.", False, "neg_decision_no_why_1"),
    ("decision", "Going with Rust for ingest. Rejected Python and Go.", False, "neg_decision_no_why_2"),
    ("decision", "We picked TypeScript over JavaScript. Done.", False, "neg_decision_no_why_3"),
    ("decision", "Decision: use Tailwind. Convention: never inline styles.", False, "neg_decision_no_why_4"),
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
    ("fact", "Basically what we did was some database work. In summary, things happened.", False, "neg_fact_pure_filler"),
    ("fact", "Maybe we should probably use Redis. I think it could work. Perhaps we'll try it.", False, "neg_fact_pure_speculation"),
    ("fact", "We did stuff yesterday.", False, "neg_fact_trivial_recap"),
    ("fact", "TL;DR: anyway, long story short, basically the thing worked out.", False, "neg_fact_only_meta"),
    ("fact", "It might be possible that the cache could maybe help us probably. Seems like a good idea.", False, "neg_fact_pure_uncertainty"),
    ("fact", "Migration ran in 14s. Index is 320MB. Reads are 12ms p50.", False, "neg_metrics_only_log_entry"),
    ("decision", "We're using PostgreSQL because we already have it deployed and operations knows it well.", True, "pos_decision_pragmatic_why"),
    ("fact",
     "Embeddings are produced by services/embed/worker.py which reads from kafka topic 'docs' "
     "and writes to the pgvector index. Throughput: 2000 docs/min on a single 4-core worker.",
     True, "pos_fact_pipeline_description"),
    ("decision", "We chose, in summary, basically, to do the thing. Decision: yes. Convention: probably.", False, "neg_adversarial_decisions_words_only"),
    ("fact", "The system might possibly maybe run on AWS or perhaps GCP. I think it could be either.", False, "neg_adversarial_arch_words_but_speculation"),
    ("error", "Fix: bumped timeout from 5s to 30s. Root cause: cold-start in lambda.", True, "pos_short_but_concrete_fix"),
    ("decision", "Adopted ESLint to avoid the styling debates that ate the last sprint.", True, "pos_short_decision_with_why"),
    ("fact",
     "The Postgres replica runs on db-replica-01.prod and lags primary by ~30ms p99. "
     "The lag is measured by the lag_seconds metric scraped every 15s. We page on lag > 5s.",
     True, "pos_fact_high_signal_with_numbers"),
    ("fact", "Failed.", False, "neg_one_word_no_signal"),
    ("fact", "Decision: TBD.", False, "neg_decision_marker_but_empty"),
]

# --- NEW: authored to extend coverage & adversarial near-misses --------------
# Each: (kind, text, expected_pass, label)
NEW = [
    # --- POSITIVES: durable architecture facts with causal why ---
    ("fact",
     "The auth service runs on Cloud Run and talks to Redis for session storage "
     "because we needed sub-5ms session lookups that Postgres couldn't hit under load.",
     True, "new_pos_arch_why_redis"),
    ("fact",
     "Search is served by an OpenSearch cluster (3 data nodes) that reads from the "
     "ingest pipeline. We shard by tenant_id to avoid hot shards on our 12 largest customers.",
     True, "new_pos_arch_opensearch_shard"),
    ("architecture",
     "The webhook handler in services/webhooks/ writes to an SQS queue rather than "
     "processing inline, so that a downstream Stripe outage can't cascade into 504s on the API.",
     True, "new_pos_arch_sqs_decouple"),
    # --- POSITIVES: concrete errors / incidents with root cause ---
    ("error",
     "Bug: nightly export job OOM-killed at 2GB. Root cause: pandas loaded the full "
     "8M-row table into memory. Fix: switched to chunked read with chunksize=50000.",
     True, "new_pos_error_oom_chunk"),
    ("error",
     "Regression: p99 latency jumped from 80ms to 1200ms after the v2.3 deploy "
     "because the new ORM eager-loaded a 40-column join on every request. "
     "Fixed by adding .only() to the queryset.",
     True, "new_pos_error_n_plus_one"),
    ("error",
     "Incident: checkout 500s for 20 minutes. Root cause: feature flag eval threw "
     "when the flag store returned null, and we didn't have a default. "
     "Fix: default-to-off on store miss.",
     True, "new_pos_error_flag_null"),
    # --- POSITIVES: decisions with strong why ---
    ("decision",
     "We migrated to pnpm from npm because the monorepo install dropped from 4min to 40s "
     "and the strict node_modules caught three phantom-dependency bugs.",
     True, "new_pos_decision_pnpm"),
    ("decision",
     "Switched to Server-Sent Events over WebSockets for the notifications feed "
     "in order to avoid maintaining a sticky-session load balancer for 200k idle connections.",
     True, "new_pos_decision_sse"),
    ("decision",
     "We deprecated the v1 REST API in favor of GraphQL because mobile was making "
     "11 round-trips per screen and battery complaints spiked.",
     True, "new_pos_decision_graphql"),
    # --- POSITIVES: SOP / procedure ---
    ("sop",
     "Runbook for rotating the signing key:\n"
     "1. Generate the new key with `make gen-key`.\n"
     "2. Add it to the JWKS endpoint as a secondary key.\n"
     "3. Wait 24h for token TTL to expire so that no in-flight token is rejected.\n"
     "4. Promote the new key to primary and remove the old one.",
     True, "new_pos_sop_key_rotation"),
    # --- POSITIVE: borderline-signal fact that should still just pass ---
    ("fact",
     "The cron scheduler lives in infra/cron.tf and triggers the reconcile job "
     "every 15 min via EventBridge.",
     True, "new_pos_borderline_cron"),

    # --- NEGATIVES: filler / chatter ---
    ("fact", "Anyway, we touched a few files and moved on. To recap: it's fine now.", False, "new_neg_filler_recap"),
    ("fact", "As I mentioned, basically what we did was the usual stuff. Long story short, done.", False, "new_neg_filler_chatter"),
    # --- NEGATIVES: pure speculation ---
    ("fact", "We could maybe try caching the responses. It probably helps. Seems like a win.", False, "new_neg_spec_caching"),
    ("fact", "Perhaps the slowness is the database. I think it might be the index, possibly.", False, "new_neg_spec_slowness"),
    # --- NEGATIVES: trivial lookup / no durable value ---
    ("fact", "Ran the tests. They passed.", False, "new_neg_trivial_tests"),
    ("fact", "Updated the README.", False, "new_neg_trivial_readme"),
    ("fact", "Looked up the current time and it was 3pm.", False, "new_neg_trivial_time"),
    # --- NEGATIVES: reasonless decisions (decision markers, no why) ---
    ("decision", "We switched to Vite. Moved off Webpack.", False, "new_neg_decision_vite_no_why"),
    ("decision", "Adopted Kubernetes for everything going forward.", False, "new_neg_decision_k8s_no_why"),
    ("convention", "Convention: all services expose a /healthz endpoint.", False, "new_neg_convention_no_why"),
    # --- ADVERSARIAL near-miss: decision WITH arch words but NO because ---
    ("decision",
     "We chose Kafka over RabbitMQ. It runs on three brokers and talks to the "
     "ingest service. Decision finalized.",
     False, "new_neg_decision_arch_no_why"),
    # --- ADVERSARIAL: looks like an error report but is pure hedging ---
    ("error",
     "Something might have broken maybe. It could possibly be the cache. Not sure, perhaps.",
     False, "new_neg_error_all_hedge"),
    # --- ADVERSARIAL: number-only log line, no architecture/decision ---
    ("fact", "Build took 3min. Bundle is 1.2MB. 14 warnings.", False, "new_neg_numbers_only_log"),
    # --- ADVERSARIAL: duplicate-style restatement, no new signal ---
    ("fact", "We use Postgres. We use Postgres for our data. Postgres is our database.", False, "new_neg_duplicate_restate"),
    # --- ADVERSARIAL: convention WITH a real why → should keep ---
    ("convention",
     "Convention: every migration must be reversible because we roll back deploys "
     "on canary failure and a non-reversible migration would strand the cluster.",
     True, "new_pos_convention_reversible_why"),
    # --- ADVERSARIAL: decision whose 'because' is buried in a code fence only ---
    ("decision",
     "Decision: use bcrypt for password hashing.\n"
     "```python\n# because argon2 wasn't available in our runtime\nhash = bcrypt.hash(pw)\n```",
     False, "new_neg_decision_why_in_code_only"),
]


def build_rows():
    rows = []
    for kind, text, exp, label in SEED:
        rows.append({
            "text": text,
            "kind": kind,
            "label": "keep" if exp else "reject",
            "why": _why_for(label, exp),
            "source": "write_gate_corpus.py",
        })
    for kind, text, exp, label in NEW:
        rows.append({
            "text": text,
            "kind": kind,
            "label": "keep" if exp else "reject",
            "why": _why_for(label, exp),
            "source": "authored",
        })
    return rows


def _why_for(label: str, exp: bool) -> str:
    """Short rationale for the gold label (documentation, not scored)."""
    pos_reasons = {
        "default_keep": "durable signal (decision/error/architecture/code/numbers) with grounding",
    }
    neg_reasons = {
        "default_reject": "low/negative signal: filler, speculation, trivial, or reasonless decision",
    }
    # Specific overrides for the most instructive cases.
    specific = {
        "neg_decision_no_why_1": "decision marker present but no causal why-clause → must reject",
        "neg_decision_no_why_2": "reasonless decision (rejected X, chose Y) without because → reject",
        "new_neg_decision_arch_no_why": "adversarial: arch words + decision marker but no because → reject",
        "new_neg_decision_why_in_code_only": "because lives only inside a code fence; gate strips fences → reject",
        "new_pos_convention_reversible_why": "convention WITH explicit because → keep",
        "new_pos_borderline_cron": "borderline durable arch fact near threshold → keep",
        "neg_metrics_only_log_entry": "numbers only, no decision/arch/error context → reject",
        "new_neg_numbers_only_log": "build metrics only, no durable context → reject",
        "new_neg_duplicate_restate": "duplicate restatement, no new signal → reject",
    }
    if label in specific:
        return specific[label]
    return pos_reasons["default_keep"] if exp else neg_reasons["default_reject"]


def main():
    out = Path(__file__).resolve().parent / "write_gate_labeled.jsonl"
    rows = build_rows()
    with out.open("w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    n_keep = sum(1 for r in rows if r["label"] == "keep")
    n_reject = len(rows) - n_keep
    n_seed = sum(1 for r in rows if r["source"] == "write_gate_corpus.py")
    n_new = len(rows) - n_seed
    print(f"wrote {len(rows)} cases -> {out}")
    print(f"  keep={n_keep}  reject={n_reject}")
    print(f"  from corpus={n_seed}  authored={n_new}")


if __name__ == "__main__":
    main()
