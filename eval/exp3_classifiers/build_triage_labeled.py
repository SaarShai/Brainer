#!/usr/bin/env python3
"""Generate eval/exp3_classifiers/triage_labeled.jsonl.

30-50 labeled triage cases. Each row:
  {prompt, expected_tier, expected_model, expect_bypass, source}

where:
  - expected_tier   ∈ {simple, medium, hard, unknown}  (None to skip tier grading)
  - expected_model  ∈ {haiku, sonnet, opus, local:qwen3:8b, not_haiku}
                      "not_haiku" = any model except haiku is acceptable (cost-floor guard)
  - expect_bypass   bool — should is_bypass() fire (NO TRIAGE / /opus)?

Coverage:
  - simple / medium / complex tiers
  - the NO-TRIAGE bypass (and /opus) + anti-bypass (path/url decoys)
  - local-vs-frontier routing (summarize/cheap/local -> local:qwen3:8b)
  - the regex-fast-path vs LLM-fallback split (some prompts hit no regex rule)

Seeds from eval/sims/prompt_triage_corpus.py CASES and the L3 bypass block,
plus eval/tasks/prompt-triage-corpus.yaml; the rest are authored.
"""
from __future__ import annotations

import json
from pathlib import Path

# (prompt, expected_tier, expected_model, expect_bypass, source)
# expected_tier None => tier not graded (e.g. bypass cases never run classify)
CASES = [
    # ---- SEED from prompt_triage_corpus.py CASES (model-graded) ----
    ("fix this typo in the readme", "simple", "haiku", False, "triage_corpus.py"),
    ("commit and push", "simple", "haiku", False, "triage_corpus.py"),
    ("what is the gini coefficient", "simple", "haiku", False, "triage_corpus.py"),
    ("add a note to wiki that we use pgvector", "simple", "haiku", False, "triage_corpus.py"),
    ("install ruff", "simple", "haiku", False, "triage_corpus.py"),
    ("summarize this paragraph for me", "simple", "local:qwen3:8b", False, "triage_corpus.py"),
    ("git stash", "simple", "haiku", False, "triage_corpus.py"),
    ("use ollama to translate this string", "simple", "local:qwen3:8b", False, "triage_corpus.py"),
    ("refactor the auth module across all services", "hard", "opus", False, "triage_corpus.py"),
    ("design the new event-bus architecture for our backend", "hard", "opus", False, "triage_corpus.py"),
    ("write me a comprehensive markdown audit of my codebase", None, "not_haiku", False, "triage_corpus.py"),
    ("review and critique the PR I just opened", None, "not_haiku", False, "triage_corpus.py"),
    ("debug why the production queue is hanging", None, "not_haiku", False, "triage_corpus.py"),
    ("do a thorough analysis of the failure modes in our auth flow", None, "not_haiku", False, "triage_corpus.py"),
    ("investigate the root cause of the data inconsistency", None, "not_haiku", False, "triage_corpus.py"),
    ("research the best vector DB options for our scale", "medium", "sonnet", False, "triage_corpus.py"),
    ("tldr this log please", "simple", "local:qwen3:8b", False, "triage_corpus.py"),
    ("condense this article", "simple", "local:qwen3:8b", False, "triage_corpus.py"),

    # ---- SEED from prompt-triage-corpus.yaml (tier-graded) ----
    ("What is a binary search tree?", "simple", "haiku", False, "triage-corpus.yaml"),
    ("Summarize this short paragraph: Foo. Bar. Baz.", "simple", "local:qwen3:8b", False, "triage-corpus.yaml"),
    ("Commit the staged files with message 'wip'.", "simple", "haiku", False, "triage-corpus.yaml"),
    ("Define 'idempotent'.", "simple", "haiku", False, "triage-corpus.yaml"),
    ("Research the current state of LLM prompt compression in 2026.", "medium", "sonnet", False, "triage-corpus.yaml"),
    ("Survey GitHub for repos that implement RAG over markdown notes.", "medium", "sonnet", False, "triage-corpus.yaml"),
    ("Design a multi-tenant storage architecture for our SaaS.", "hard", "opus", False, "triage-corpus.yaml"),
    ("Implement a distributed lock service across three microservices.", "hard", "opus", False, "triage-corpus.yaml"),

    # ---- SEED bypass block from triage_corpus.py _extra_regression_checks ----
    ("fix this NO TRIAGE", None, None, True, "triage_corpus.py"),
    ("NO-TRIAGE just run", None, None, True, "triage_corpus.py"),
    ("/opus help me think", None, None, True, "triage_corpus.py"),
    ("git log /opus/file.md", "simple", None, False, "triage_corpus.py"),   # anti-bypass: path decoy
    ("see https://x.com/opus/page", None, None, False, "triage_corpus.py"),  # anti-bypass: url decoy

    # ---- AUTHORED: simple ----
    ("fix the import in utils.py", "simple", "haiku", False, "authored"),
    ("who is Ada Lovelace", "simple", "haiku", False, "authored"),
    ("git add -A and commit", "simple", "haiku", False, "authored"),
    ("rewrite this sentence to be shorter", "simple", "local:qwen3:8b", False, "authored"),
    ("configure pre-commit hooks", "simple", "haiku", False, "authored"),

    # ---- AUTHORED: local-vs-frontier (explicit cheap/local hints) ----
    ("do this on a cheap local model, no api", "simple", "local:qwen3:8b", False, "authored"),
    ("abstract the key points from this transcript", "simple", "local:qwen3:8b", False, "authored"),

    # ---- AUTHORED: medium (research/investigate) ----
    ("investigate which dependency bumped our bundle size", None, "not_haiku", False, "authored"),
    ("find repos that benchmark llama.cpp throughput", "medium", "sonnet", False, "authored"),

    # ---- AUTHORED: complex (must NOT go to haiku) ----
    ("migrate the whole billing service from REST to gRPC", None, "not_haiku", False, "authored"),
    ("architect a sharded queue for 1M events/sec", "hard", "opus", False, "authored"),
    ("do an in-depth security review of the auth flow", None, "not_haiku", False, "authored"),
    ("trace the root-cause of the intermittent 502s in production", None, "not_haiku", False, "authored"),

    # ---- AUTHORED: bypass + anti-bypass ----
    ("please NO_TRIAGE here", None, None, True, "authored"),
    ("   /opus do the thing", None, None, True, "authored"),
    ("open ./opus.txt", None, None, False, "authored"),                 # anti-bypass: filename decoy
    ("the word slashopus is not a bypass", None, None, False, "authored"),  # anti-bypass: substring decoy
]


def main():
    out = Path(__file__).resolve().parent / "triage_labeled.jsonl"
    rows = []
    for prompt, tier, model, bypass, source in CASES:
        rows.append({
            "prompt": prompt,
            "expected_tier": tier,
            "expected_model": model,
            "expect_bypass": bypass,
            "source": source,
        })
    with out.open("w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")

    n = len(rows)
    n_bypass = sum(1 for r in rows if r["expect_bypass"])
    n_seed = sum(1 for r in rows if r["source"] != "authored")
    n_new = n - n_seed
    tiers = {}
    for r in rows:
        if not r["expect_bypass"]:
            tiers[r["expected_tier"]] = tiers.get(r["expected_tier"], 0) + 1
    print(f"wrote {n} cases -> {out}")
    print(f"  bypass={n_bypass}  routing={n - n_bypass}")
    print(f"  tier coverage (non-bypass): {tiers}")
    print(f"  from corpora={n_seed}  authored={n_new}")


if __name__ == "__main__":
    main()
