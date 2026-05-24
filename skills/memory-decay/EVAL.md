# memory-decay — EVAL

## Mechanism

Exponential confidence decay: `confidence_new = confidence_old × exp(-λ × days_idle)` where `λ = ln(2) / halflife_days`. Default half-life **405 days** (5% per 30 idle days), matching [ogham-mcp/ogham-mcp](https://github.com/ogham-mcp/ogham-mcp) (91.8% QA on LongMemEval).

Protection class (skips decay) sourced from [doobidoo/mcp-memory-service](https://github.com/doobidoo/mcp-memory-service) — error/lesson/sop/procedure pages, explicit `protected: true`, `evidence_count ≥ 3`, or pages under `L0_rules.md` / `L3_sops/` / `raw/`.

## Built-in tests

`python tools/test_decay.py` — 8 tests:

- frontmatter parses + body preserved
- `rewrite_confidence` flips only that field
- dry-run reports but does not write
- `--apply` writes the expected exp-decay value (verified against the closed-form solution)
- `type: error` pages are protected (Mistake-note protection)
- `evidence_count ≥ 3` protects
- `L3_sops/` dir protects
- `--archive-candidates` flags pages below threshold

## Real-world calibration

Run dry-run against Token Economy's own `wiki/`:

```
scanned: 40  protected: 5  changed: 25  errors: 0
```

The 5 protected pages match expectation (4 in `L3_sops/`, 1 with `evidence_count: 3`). Decay factor at 29 idle days lands at ×0.952 — exactly the 5% / 30 d rate the lineage prescribes.

## Target metrics (pending integration)

When wiki-memory's retrieval scoring multiplies in the decayed `confidence`:

- **Retrieval evidence-rate** stays flat or rises (decay should suppress stale-but-tempting matches without hiding fresh ones).
- **Stale-fact retrieval rate** drops by ≥40% over a 6-month window when decay runs weekly.
- **No regression** on the `runner_wiki.py` A/B against the pre-decay baseline.

## Anti-falsifications

- If evidence-rate *drops* after decay, you're either (a) decaying too fast (lower λ) or (b) decaying pages that should be protected (audit the protection class).
- If the wiki visibly empties out over 6 months, half-life is too short OR you're not bumping `evidence_count` on retrieval — fix the bump path first, then re-evaluate.

## Known limits

- Linear scan of all pages — fine up to ~10K pages; beyond that, batch the run.
- Date parsing only knows `YYYY-MM-DD` and `YYYY/MM/DD`; non-ISO dates fall back to filesystem mtime (which is usually fine but loses semantic intent like "verified yesterday").
- No "access frequency" boost (LFU/LRU style) — pure age-based. A future companion could read access logs and boost frequently-retrieved pages back up.

## Composition with related skills

- `write-gate` decides what enters the wiki at confidence T₀.
- `memory-decay` ages that confidence over time.
- `/consolidate-memory` (Anthropic skill) does merge/dedup — independent axis.
- `wiki-memory`'s retrieval scoring needs to *read* the decayed `confidence` to make the decay matter; until that wiring lands, decay is informational.
