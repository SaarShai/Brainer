# EVAL — `team-lead`

Method for testing team-lead's cost claim ("orchestrator/worker splits are
cheaper than end-to-end top-model") against REAL lane telemetry, instead of
asserting it. Harness: [`tools/team_lead_eval.py`](tools/team_lead_eval.py).
Tests: [`tools/test_team_lead_eval.py`](tools/test_team_lead_eval.py).

## What this measures

- Token spend per pricing tier (frontier / mid / small / glm / local), derived
  from real dispatch records.
- Leader-share vs delegate-share of total tokens — the structural signature
  team-lead's protocol is supposed to produce (leader plans+reviews, cheap
  lanes do volume).
- Accepted vs rejected lane counts.
- `cost_per_accepted_change` = total blended cost / accepted lane count.
- A **counterfactual**: the same total token volume, entirely priced at the
  frontier rate — and `savings% = 1 - (blended cost / counterfactual cost)`.

## What this does NOT measure

- **Output quality.** A cheap lane that produces a worse or wrong result
  costs less per token and is not rewarded here as "efficient" — this tool
  only prices tokens and counts accept/reject outcomes it is told about. If
  the question is "is the DELEGATED work as good as frontier would have
  produced", that is [`skills/eval-gate`](../eval-gate/EVAL.md)'s job
  (LLM-as-judge quality gate), not this one. Run both: eval-gate for lift,
  this harness for cost structure. Neither substitutes for the other.
- Whether a frontier-only run would have used fewer or more tokens for the
  SAME task (see the counterfactual caveat below) — this harness cannot know
  that without a paired same-task run on both topologies.

## The counterfactual caveat (read before quoting `savings%`)

The counterfactual re-prices the observed total token count at the frontier
`$/Mtok` rate. This assumes **token-count parity**: that a single frontier
model doing the whole task end-to-end would have burned the same number of
tokens the lane split burned. In practice that's unproven either direction:

- The split could burn MORE tokens than end-to-end frontier would (brief
  overhead, re-derivation across lane boundaries, redundant context per
  lane) — in which case `savings%` here OVERSTATES the real saving.
- End-to-end frontier could burn MORE tokens than the split for the same
  outcome (no free/cheap bulk-parallel lanes to absorb volume work) — in
  which case `savings%` here UNDERSTATES the real saving.

The external anchor cited by the protocol itself
([`skills/_shared/ORCHESTRATION.md` §6](../_shared/ORCHESTRATION.md)) is:

> Orchestrator/worker splits measure **58–74% cheaper** than end-to-end
> top-model (architect-loop DESIGN.md §2, PEAR).

Treat that range as the external, independently-measured baseline; treat
THIS tool's `savings%` as **this run's structural ratio** — a number worth
tracking over time and comparing against the 58–74% anchor, not a number to
quote as a validated absolute dollar saving on its own.

## Pricing — ratios are the durable output, not the dollars

`team_lead_eval.py` ships a built-in `$/Mtok` table (frontier / mid / small /
glm / local=0) as illustrative placeholder estimates, overridable per-tier via
`BRAINER_PRICE_<TIER>` (e.g. `BRAINER_PRICE_FRONTIER=15`). **Absolute prices
rot** the day a vendor reprices or a new model tier ships — the number that
stays meaningful across time is the RATIO: leader-share vs delegate-share,
and `savings%` vs the frontier counterfactual. Read the `$` columns as
illustrative only; read the tier-share and savings-ratio numbers as the
signal.

## Inputs

1. `--trace <path>` — a JSONL file written by
   [`skills/_shared/orchestration_trace.py`](../_shared/orchestration_trace.py)
   (`record_lane_event`). Tolerant of missing/extra fields; malformed lines
   are skipped and the skip count is reported, never fatal. `ok` (dispatch
   success) is used as an ACCEPTANCE PROXY for these records — it is the
   closest signal the trace format carries today, not literally "a reviewer
   accepted this change."
2. `--lanes <path>` — manual records (CSV or JSONL: `lane_label, tier,
   tokens, accepted`) for lanes whose token totals are reported out-of-band.
   The motivating case: Claude-harness Agent-tool subagents report their
   subagent token totals outside `orchestration_trace`'s dispatch path, so
   this format lets a human/leader paste those totals in directly, with an
   explicit `accepted` verdict per lane.

Records with no discoverable token count are counted (so lane totals stay
honest) but excluded from cost math and flagged `UNPRICED` — there's nothing
to price.

## How to run

```bash
# markdown report from real trace + manual lanes
python3 skills/team-lead/tools/team_lead_eval.py \
  --trace .brainer/trace/lanes.jsonl \
  --lanes path/to/manual_lanes.csv

# JSON for programmatic consumption
python3 skills/team-lead/tools/team_lead_eval.py --trace .brainer/trace/lanes.jsonl --json

# unattended gate: fail loudly if savings% regresses below threshold,
# or if there are zero accepted lanes (savings% isn't meaningful then)
python3 skills/team-lead/tools/team_lead_eval.py \
  --trace .brainer/trace/lanes.jsonl --gate --min-savings 40
```

Run the test suite:

```bash
python3 skills/team-lead/tools/test_team_lead_eval.py
```

## Datapoints

One row per real session/run where a leader actually filled in observed
numbers from real trace + manual-lane data — never invented. Add a row each
time this harness is run against a live team-lead session.

| date | session/task | total tokens | leader-share | delegate-share | accepted / rejected lanes | cost_per_accepted_change | savings% vs counterfactual | notes |
|---|---|---|---|---|---|---|---|---|
| 2026-07-05 | architect-loop review + frontier-routing build (Fable 5 leader, 17 Agent lanes: 7 build, 5 verify, 2 research, 1 glm-extract, 1 codex-xhigh, 1 frontier-verify) | 1,033,224 (delegate) | UNMEASURED — leader context not in trace; record leader events to close this | 100% of traced | 16 / 1 (rejected: fetch lane returned summaries not verbatim — caught by shape-invariant check) | $0.2164 | 72.1% (inside the 58–74% external anchor) | manual CSV from Agent-tool per-lane totals; tiers: builders/verifiers=mid (sonnet-pinned defs), research-lite=small (haiku-pinned), glm=glm, codex-xhigh + frontier-verifier(inherit)=frontier; token-parity caveat applies |
