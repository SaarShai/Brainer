# EVAL — `eval-gate`

LLM-as-judge quality gate. **Status: opt-in, unmeasured** — plumbing verified
offline; effectiveness A/B pending (N≥50 before any default promotion).

## Verified — plumbing (offline, no network)

`bash skills/eval-gate/tools/test.sh` — exercises all three verbs via
`--stub-score` (deterministic, no model):

- `score` pass (stub 5 → 1.0 ≥ 0.7) → exit 0
- `score` fail (stub 2 → 0.4 < 0.7) → exit 1
- `score` empty candidate → exit 2
- `add-case` rejects a thin reason and a reasonless ("no why") reason → exit 1
- `add-case` accepts a why-bearing reason, appends exactly one JSONL line → exit 0
- `add-case --force` overrides the gate → exit 0
- `suite` all-pass → exit 0; any case below threshold → exit 1
- `suite` mean-regression vs a saved baseline → exit 1
- judge-unreachable / unparseable → exit 2 (gate fails safe, never ships blind)

## Verified — judge–human agreement (mechanism, public benchmark)

Validates that Claude-as-judge tracks *human* quality labels — i.e. the score
means something. This is NOT a measure of your content taste (that's the
pending A/B below); it's proof the judging mechanism is sound.

- Corpus: `lmsys/mt_bench_human_judgments` — 20 blinded pairs, 7 tasks
  (qids 81–87), presentation order randomized, human-winner slot balanced
  10/10. Judge: Claude Sonnet (5-agent fan-out, 4 pairs each), each response
  scored 0–5 independently, blind to the human label.
- Pairwise agreement (judge's higher score == human winner): **79%** (15/19
  non-tie; 1 judge-tie), vs 50% random — in the band of published GPT-4-judge
  and human–human agreement on MT-bench (~80%).
- Score separation: mean human-winner **4.10** vs loser **3.00** (**+1.10**).
- Gate view @0.7 (pass = score ≥4): winners pass **75%**, losers pass **25%**.
- Caveats: N=20 (wide CI), narrow task slice, Sonnet judge. 3 of 4
  disagreements fell on one task (q82) — rubric/judge weaker there.
- Reproducibility: fetch + blind + aggregate is deterministic Python; the
  judging step is a Claude-Code agent fan-out. Run 2026-05-31.

## Pending — effectiveness A/B

The claim to test is *not* token savings (this skill spends tokens to buy
quality); it's **defect catch-rate vs false-reject**:

| Metric | Without eval-gate | With | Target |
|---|---|---|---|
| bad outputs shipped (escapes) | | | ↓ |
| good outputs wrongly blocked (false rejects) | | | ≈0 |
| judge–human score agreement | | | ≥0.8 corr |

Protocol: build a 50-case set (25 known-good, 25 known-bad) for one real task;
score each; compare the gate's pass/fail to human labels. Judge: Ollama local
(smoke) → MiMo (production). The rubric is the variable — measure how rubric
specificity moves agreement.

## Failure modes

- Rubric too vague → low judge–human agreement (the score is noise). Mitigation:
  specificity; the agreement metric above surfaces it.
- Judge model too small → inconsistent scores. Use a 7B+ instruct model or MiMo.
- Self-judging (same model generates + judges) can run lenient; temp 0 + an
  external rubric mitigate but don't eliminate.

## Lineage / sources

- `eval/judge.py` — backends + 0-5 scoring lifted here.
- LLM-as-judge + regression-suite + failure→case ratchet (the standard ML-eng
  eval loop), applied to agent / content output.
