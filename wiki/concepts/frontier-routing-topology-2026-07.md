---
trust: verified
schema_version: 2
title: "Frontier-routing topology decided: main loop routes down; escalate-up mode available; measured 72.1%"
type: decision
domain: "framework"
tier: episodic
confidence: 0.8
created: "2026-07-05"
updated: "2026-07-05"
verified: "2026-07-05"
sources: ["6 surveyed systems topology review (aider architect, opusplan, Devin, Cursor, RouteLLM, FrugalGPT)", "Brainer team-lead EVAL harness (d3b073b)", "session datapoint (bdd2db1)", "model_roster telemetry (a5c315f)", "orchestration_trace JSONL (a5c315f)"]
supersedes: []
superseded-by:
tags: [orchestration, routing, topology, decision, measured, cost, frontier-model]
---

# Frontier-routing topology decided: main loop routes down; escalate-up mode available; measured 72.1%

## Question

Should the session model be the **frontier** (routing down to cheap workers) or a **cheap model** (escalating up to frontier on hard prompts)?

## Decision

**Frontier-leads (route down) is default.** All 6 surveyed systems use it:
- aider architect: 85% vs 84% solo frontier
- opusplan
- Devin
- Cursor
- RouteLLM: 85% cost cut @95% GPT-4 quality (router-topology for one-shot queries, not coding agents)
- FrugalGPT: 98% (cascade w/ quality-oracle requirement)

**Escalate-up mode now exists.** When `BRAINER_TRIAGE_ESCALATE_UP=1`:
- `prompt-triage` emits `frontier-advisor` / `frontier-verifier` directives on hard prompts
- Cheap mains may only execute from frontier-authored plans
- `/model` switches at phase boundaries only (cache namespace)

(Commit 118fa0d implements this mode.)

## Measurement (first datapoint)

**Setup:** Brainer team-lead EVAL harness (d3b073b), datapoint bdd2db1.

**Build:** this session = 17 lanes, 1.03M delegate tokens, 16/1 accepted/rejected.

**Metrics:**
- cost_per_accepted_change: **$0.2164**
- structural savings vs all-frontier counterfactual: **72.1%** (token-parity caveat; inside 58–74% external anchor from [[architect-loop-adoption-2026-07]])
- **Leader tokens unmeasured** — recorded as the open gap

## Infrastructure shipped

- `model_roster` per-lane telemetry: usage/latency/served_model (a5c315f)
- `orchestration_trace` JSONL logging (a5c315f)
- Effort tiers incl. codex `model_reasoning_effort` mapping (a5c315f)
- Leader-bulk-edit drift probe w/ min_count (a44b270)

## Related

- [[concepts/architect-loop-adoption-2026-07]]
- [[concepts/e2-prose-rules-measured-2026-07]]
- [[concepts/team-lead-upstream-2026-07]]
