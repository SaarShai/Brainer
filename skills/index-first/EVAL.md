# EVAL — `index-first`

## Static cost (pending measurement)

Will be filled in by `eval/runner.py` once a task set is authored. Expected static cost: small (description-only resident, body loads on trigger).

## A/B savings (pending)

**Hypothesis:** On tasks that involve tracing references, finding callers, or reading multiple related files/docs, this skill should reduce tool-call count and output tokens versus a baseline that lets the agent grep-and-read freely.

**Reference numbers from upstream (codegraph repo, not our measurement):** ~35% cheaper, ~59% fewer tokens, ~70% fewer tool calls, ~49% faster across 7 real codebases. Gains scale with corpus size; small repos show narrower margins because native search is already cheap.

A direct A/B requires an index actually being installed (e.g., codegraph + MCP) in both arms. Without that, the skill has nothing to redirect to and the test degenerates.

## Methodology

- Sample size: N=3-10 local smoke; N≥50 on Kaggle T4 for any >20% savings claim.
- Tasks: TBD in `eval/tasks/index-first.yaml`. Should pair grep-heavy exploration prompts ("trace all callers of X", "find every route that maps to handler Y") across small / medium / large corpora.
- Backends: ollama / anthropic / mimo.

## Failure modes (anticipated)

- **Over-trigger on indexless corpora**: skill body loads, no index exists, agent burns context for no payoff. Mitigation: explicit "check first, fall back" step in protocol.
- **Stale-index trust**: if the index hasn't synced and the agent doesn't verify, results will mislead. Mitigation: caveat in skill body.
- **Confidence-score blindness**: agent picks top result even when it's low-confidence. Mitigation: explicit step in protocol + anti-pattern bullet.
