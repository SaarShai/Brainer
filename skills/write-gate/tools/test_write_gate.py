#!/usr/bin/env python3
"""Smoke tests for write_gate.py — runnable standalone with no pytest dep."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from write_gate import DEFAULT_THRESHOLD, decide, extract_trust, score_text  # noqa: E402


def assert_passes(text: str, kind: str = "fact", msg: str = "") -> None:
    s = score_text(text, kind)
    ok, verdict = decide(s, kind, DEFAULT_THRESHOLD, require_why=True)
    assert ok, f"expected pass: {msg}\n  text={text!r}\n  verdict={verdict}\n  score={s.total:.2f}"


def assert_rejects(text: str, kind: str = "fact", msg: str = "") -> None:
    s = score_text(text, kind)
    ok, verdict = decide(s, kind, DEFAULT_THRESHOLD, require_why=True)
    assert not ok, f"expected reject: {msg}\n  text={text!r}\n  verdict={verdict}\n  score={s.total:.2f}"


def test_decisions_need_why() -> None:
    # Decision without why-clause → reject even if score is high
    txt = "We chose pgvector over Qdrant. We rejected Pinecone. Decision: pgvector."
    assert_rejects(txt, "decision", "decision without why-clause")

    # Same decision with why-clause → pass
    txt2 = "We chose pgvector over Qdrant because dev parity matters, so that local == prod."
    assert_passes(txt2, "decision", "decision with why-clause")


def test_filler_recap_rejected() -> None:
    # Load-bearing: the text carries REAL positive signal (arch + numbers ≈ 3.5,
    # above threshold), so the only reason it rejects is the filler penalty.
    # If the filler weight were mutated to 0, the positive signal would carry it
    # over threshold and this reject would fail — that's the mutation we want killed.
    dirty = ("In summary, the ingestion worker writes to Postgres and is 12ms p50. "
             "To recap, index is 320MB on disk. Long story short.")
    assert_rejects(dirty, "fact", "filler drags real signal under threshold")

    # Positive control: identical claims minus the filler phrases must PASS.
    clean = "The ingestion worker writes to Postgres and is 12ms p50. Index is 320MB on disk."
    assert_passes(clean, "fact", "same text without filler passes (proves penalty is load-bearing)")


def test_error_lesson_passes() -> None:
    txt = (
        "Bug: deploy failed because PG_URL was unset in production env.\n"
        "Fix: added to vault and reloaded systemd unit.\n"
        "Root cause: env was set in .envrc which doesn't apply to systemd.\n"
    )
    assert_passes(txt, "error", "concrete failure with fix")


def test_architecture_with_code() -> None:
    txt = (
        "The ingestion service runs on Fly.io and calls the embedding worker at /embed.\n"
        "```python\nresult = embed(chunk)\n```\n"
        "Latency: 120ms p50, 450ms p99."
    )
    assert_passes(txt, "fact", "arch + code + numbers")


def test_speculation_drops_score() -> None:
    # Load-bearing: the text carries REAL positive signal (arch + numbers ≈ 3.5,
    # above threshold), so the only reason it rejects is the speculation penalty.
    # If the speculation weight were mutated to 0, the positive signal would carry
    # it over threshold and this reject would fail — the mutation we want killed.
    dirty = ("The cache layer runs on Redis and is 320MB. Reads are 12ms p50 "
             "against the index. I think it could maybe work, possibly.")
    assert_rejects(dirty, "fact", "speculation drags real signal under threshold")

    # Positive control: identical claims minus the speculation phrases must PASS.
    clean = "The cache layer runs on Redis and is 320MB. Reads are 12ms p50 against the index."
    assert_passes(clean, "fact", "same text without speculation passes (proves penalty is load-bearing)")


def test_entity_cap() -> None:
    # Many repeated entities — cap should prevent overshoot from this alone
    txt = "Foo Foo Foo Bar Bar Bar Baz Baz Baz Qux Qux Qux Quux Quux Quux"
    s = score_text(txt, "fact")
    assert s.features.get("entity_overlap", 0) <= 1.5 + 1e-9, "entity_overlap not capped"


def test_why_clause_inside_fence_does_not_satisfy_gate() -> None:
    """REGRESSION: a `# because reasons` comment inside ``` ``` used to bypass
    the decision gate. Why-clause must come from prose, not code."""
    txt = (
        "We chose pgvector over Qdrant.\n"
        "```python\n# because reasons\nx = 1\n```\n"
    )
    s = score_text(txt, "decision")
    assert not s.has_why, "why-clause inside fence must not count"
    ok, _ = decide(s, "decision", DEFAULT_THRESHOLD, require_why=True)
    assert not ok, "reasonless decision must reject even with fenced 'because'"

    # Prose 'because' still works
    txt2 = "We chose pgvector over Qdrant because dev parity matters."
    s2 = score_text(txt2, "decision")
    assert s2.has_why
    ok2, _ = decide(s2, "decision", DEFAULT_THRESHOLD, require_why=True)
    assert ok2


def test_since_no_longer_satisfies_why_clause() -> None:
    """REGRESSION: 'since' is overwhelmingly temporal and was bypassing the gate."""
    # Temporal 'since' — should NOT be a why-clause
    txt = "We chose pgvector over Qdrant. Tracked since yesterday."
    s = score_text(txt, "decision")
    assert not s.has_why, "'since' alone should no longer count as a why-clause"


def test_why_clauses_need_word_boundaries() -> None:
    """REGRESSION: naked substring matching let why-markers fire inside unrelated
    words — 'overdue tomorrow' matched 'due to', 'reasoning' matched 'the reason' —
    so reasonless decisions slipped past the why-gate."""
    # 'overdue' must NOT satisfy via 'due to'; 'reasoning' must NOT via 'the reason'.
    txt = "We chose pgvector over Qdrant. The migration is overdue tomorrow. Reasoning ongoing."
    s = score_text(txt, "decision")
    assert not s.has_why, "boundary-less why-marker fired inside an unrelated word"
    ok, _ = decide(s, "decision", DEFAULT_THRESHOLD, require_why=True)
    assert not ok, "reasonless decision must reject when no genuine why-clause is present"

    # Genuine markers still fire on word boundaries.
    for good in (
        "We chose pgvector because dev parity matters.",
        "We chose pgvector due to dev parity.",
        "We chose pgvector in favor of dev parity.",
        "We chose pgvector so that local equals prod.",
    ):
        assert score_text(good, "decision").has_why, f"genuine why-clause missed: {good!r}"


def test_entity_overlap_is_fast_on_large_input() -> None:
    """REGRESSION: list.count-per-element was O(n²); used to take seconds on 20k tokens."""
    import time
    txt = ("Foo Bar Baz " * 8000)  # 24000 tokens
    t0 = time.time()
    s = score_text(txt, "fact")
    elapsed = time.time() - t0
    assert elapsed < 1.0, f"score_text took {elapsed:.2f}s on 24k tokens (was O(n²))"
    assert s.features.get("entity_overlap", 0) <= 1.5 + 1e-9


def test_passes_with_concrete_signal() -> None:
    # Realistic durable fact: describes WHAT a system is (arch) AND gives numbers.
    # Metrics alone (without arch context) intentionally fall below threshold.
    txt = (
        "The pgvector index lives in PostgreSQL and is 320MB.\n"
        "Reads are 12ms p50 against the new schema. Migration ran in 14s.\n"
    )
    assert_passes(txt, "fact", "arch + numbers (representative durable fact)")


def test_metrics_only_below_threshold() -> None:
    # Metric-only logs ARE intentionally below threshold — they're log entries,
    # not durable facts. Capturing this as a positive assertion.
    txt = "Run took 14s. Index is 320MB. Reads are 12ms p50."
    assert_rejects(txt, "fact", "metric-only is not a durable fact")


def test_trust_bypass_rescues_vouched_atomic_fact() -> None:
    """A genuine atomic fact with no marker words scores ~0 and is rejected by
    default (the measured 82% false-reject recall gap). A 'verified'/'user_confirmed'
    trust tier vouches its importance and bypasses the signal floor."""
    txt = "The PROMPTER project folder is also called alfred."
    s = score_text(txt, "fact")
    ok, _ = decide(s, "fact", DEFAULT_THRESHOLD, require_why=True)
    assert not ok, "neutral atomic fact should reject by default (no trust)"
    ok_v, _ = decide(s, "fact", DEFAULT_THRESHOLD, require_why=True, trust="verified")
    assert ok_v, "verified trust must bypass the signal floor"
    ok_u, _ = decide(s, "fact", DEFAULT_THRESHOLD, require_why=True, trust="user_confirmed")
    assert ok_u, "user_confirmed trust must bypass the signal floor"
    # A weak/low tier must NOT bypass.
    ok_a, _ = decide(s, "fact", DEFAULT_THRESHOLD, require_why=True, trust="asserted")
    assert not ok_a, "asserted (low tier) must not bypass"


def test_trust_does_not_rescue_net_negative_filler() -> None:
    """Trust vouches importance, not quality: net-negative content (filler /
    speculation penalties) must still reject even at the highest tier."""
    txt = "In summary, basically what we did was some stuff. I think it could maybe work, possibly."
    s = score_text(txt, "fact")
    assert s.total < 0, "filler+speculation should be net-negative"
    ok, _ = decide(s, "fact", DEFAULT_THRESHOLD, require_why=True, trust="user_confirmed")
    assert not ok, "trust must not rescue net-negative (filler/speculation) content"


def test_user_confirmed_waives_why_but_verified_does_not() -> None:
    """A reasonless decision rejects by default. Only the strongest tier
    (user_confirmed) waives the why-clause; plain 'verified' still demands it."""
    txt = "We decided to go with the repo-local wiki."
    s = score_text(txt, "decision")
    ok, _ = decide(s, "decision", DEFAULT_THRESHOLD, require_why=True)
    assert not ok, "reasonless decision rejects by default"
    ok_u, _ = decide(s, "decision", DEFAULT_THRESHOLD, require_why=True, trust="user_confirmed")
    assert ok_u, "user_confirmed waives the why-clause"
    ok_v, _ = decide(s, "decision", DEFAULT_THRESHOLD, require_why=True, trust="verified")
    assert not ok_v, "verified does NOT waive the why-clause for a decision"


def test_extract_trust_reads_only_frontmatter() -> None:
    """trust must be read from YAML frontmatter, not spoofable from the body."""
    page = "---\nschema_version: 2\ntrust: verified\ntype: fact\n---\n# x\nbody text\n"
    assert extract_trust(page) == "verified"
    body_only = "no frontmatter here. trust: user_confirmed mentioned in prose.\n"
    assert extract_trust(body_only) is None, "body mention of trust: must not count"
    assert extract_trust("plain text, no trust at all") is None


def test_marker_stuffed_filler_rejected() -> None:
    """ADVERSARIAL (2026-06-27 PROMPTER opt run): content-free corporate filler
    seeded with marker substrings (decision/arch/why/procedure) scored 8.0 and
    PASSED. The buzzword penalty must pull it back under the floor."""
    payload = ("We decided to leverage our approach so that things work better. "
               "The system uses synergy and depends on best practices.\n\n"
               "1. Align stakeholders\n2. Maximize outcomes")
    assert_rejects(payload, "fact", "marker-stuffed buzzword filler must reject")
    # Positive control: a genuine decision with the SAME marker shapes but REAL
    # content (specific entities + a why) still passes — penalty targets buzzwords,
    # not the markers themselves.
    real = "We chose pgvector over Qdrant because dev parity matters, so that local equals prod."
    assert_passes(real, "decision", "genuine specific decision still passes")


def main() -> int:
    tests = [
        test_decisions_need_why,
        test_filler_recap_rejected,
        test_error_lesson_passes,
        test_architecture_with_code,
        test_speculation_drops_score,
        test_entity_cap,
        test_passes_with_concrete_signal,
        test_metrics_only_below_threshold,
        test_why_clause_inside_fence_does_not_satisfy_gate,
        test_since_no_longer_satisfies_why_clause,
        test_why_clauses_need_word_boundaries,
        test_entity_overlap_is_fast_on_large_input,
        test_trust_bypass_rescues_vouched_atomic_fact,
        test_trust_does_not_rescue_net_negative_filler,
        test_user_confirmed_waives_why_but_verified_does_not,
        test_extract_trust_reads_only_frontmatter,
        test_marker_stuffed_filler_rejected,
    ]
    failed = 0
    for t in tests:
        try:
            t()
            print(f"  ok  {t.__name__}")
        except AssertionError as e:
            failed += 1
            print(f"FAIL  {t.__name__}: {e}")
    if failed:
        print(f"\n{failed}/{len(tests)} failed")
        return 1
    print(f"\nall {len(tests)} passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
