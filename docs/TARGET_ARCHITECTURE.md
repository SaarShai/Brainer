# Brainer target architecture (north star)

Status: adopted 2026-07-18 as the design standard for all future rounds.
Derived from the 2026-07-17 independent review, the six-goal audit, and two
independent advisor consults (GPT 5.6 Sol Ultra, Kimi K3) that converged on the
same shape. Each round moves the repo toward this document or amends it with
evidence; it is not aspirational decoration.

## Mission, restated falsifiably

Brainer's measured value is **state, tools, and gates** — not influence over the
model's mind. The suite exists to make agent sessions:

1. cheaper per unit of accepted work (deterministic token savers),
2. resumable and knowledge-compounding (provenance-graded state + wiki),
3. honest at the claim boundary (shipped-error detection, not error production),
4. drop-proof for user intent (capture + close-boundary reconciliation),
5. bounded in loops (reject unbounded / self-grading / oracle-free loops),
6. checkable when delegating (evidence-envelope subagent contracts).

Goals it does NOT own: frontier cognition/mindsets (native capability; keep
`think` for weak-model tiers only), model routing (host's job), error
production, session-history substrate wherever the host reaches parity.

## Four layers, separated by emission authority

Emission authority = the right to inject bytes into the model's context. It is
the scarce resource; everything else is cheap.

### L0 — State (the product)
All persisted state is files; all writes mechanical; every byte provenance-graded
`verified-runtime | verified-tool | narrative-assumed`. Retrieval ranks higher
grades first; conflicts resolve toward `verified-runtime`.
- **Intent log** — every user prompt verbatim, append-only, written by the
  UserPromptSubmit hook. Zero LLM, zero injection. One capture, three consumers
  (reconciliation, verification guard, pre-compaction extraction).
- **Checkpoints** — context-keeper PreCompact extraction + SessionEnd archive.
- **Wiki** — gated durable memory (write-gate, wiki-refresh, progressive retrieval).
- **Batons** — curated handoffs where no hook fires.

### L1 — Deterministic tools (callables; can never inject)
semantic-diff, output-filter, index-first/graphify, wiki retrieval, loop_lint,
verification tools. All measured wins live here; all capability growth goes here.
Where the host allows interception, proven savers become default-mechanical
(re-read → semantic-diff; noisy output → filter) instead of agent-elective.

### L2 — Guards (the only injectors; hard budget: ≤2 default-on)
1. **Claim/evidence guard** — claim-class + freshness + evidence-class match +
   substrate-notification suppression. Hardened into the delegation boundary:
   subagent returns require an evidence envelope (artifact ids/hashes, commands,
   results, unresolved risks); the lead-side guard validates class, subject, and
   freshness mechanically. On hosts with blocking close decisions, enforcement
   blocks; elsewhere it degrades honestly to advisory.
2. **Close-boundary reconciliation** — at a detected wrap-up, one deterministic
   pass maps every captured intent to satisfied / answered / deferred-with-reason
   / superseded / uncovered. Only uncovered items inject, quoting the user's own
   words. No per-turn ledger, no nagging. Corrections are intent: the same pass
   checks "every correction banked or explicitly waived" (closes the learning
   loop the frontier pivot left open).
Everything else runs in shadow until it graduates the admission gate. The
no-drop capture itself never has an opt-out; only emission is governed.

### L3 — Measurement harness (the moat)
Admission to L2 requires the **three-mode gate**:
- frozen corpus = precision regression floor (never the sole gate);
- **seeded fault injection = recall** (a guard that can't be fault-injected
  can't be admitted);
- rolling live shadow = drift detection.
Every guard carries a cost contract: recall on seeded faults, live precision,
false-block cost, miss cost, tokens-per-1k-turns, kill rule, review date.
Corpora must include host-event morphologies (task notifications, compactions,
resumes), not just lexical templates — the 2026-07 field failure was a
morphology hole, not a phrase hole.

## Cross-cutting rules

- **Tier by host feature and task risk, never model name.** Capability
  auto-disable is banned: the one proven live catch was orchestration-shaped
  (unverified subagent completion), and smarter leads have more of that surface.
- **Prose survives only as task-local briefs** (leader/builder/verifier
  contracts generated at delegation time) — the only carrier reaching subagent
  interiors. No resident generic doctrine.
- **Attribution chain or it didn't happen:** mechanism fired → agent acted →
  artifact changed → prevented/escaped failure → cost. Detector firing is not
  success; the product metric is escaped defects and cost per useful catch.
- **Host-parity audit each release:** cede any sub-mechanism the host now does
  natively; keep only what the host can't (provenance grading, cross-host memory).
- **Own contracts must not drift:** SKILL.md, EVAL.md, installer behavior, and
  committed configs are checked for agreement by CI (gate-liveness + contract
  tests). A reliability suite must be a reliable source of truth about itself.

## Migration map (current catalog → target)

| Current | Target disposition |
|---|---|
| compliance-canary (frontier) | L2 guard #1, after notification fix + three-mode admission |
| requirements-ledger | replaced by intent log + L2 guard #2 (capture stays unconditional) |
| context-keeper | L0 checkpoint engine (unchanged role) |
| wiki-memory / write-gate / wiki-refresh | one L0 memory subsystem, provenance-graded |
| semantic-diff / output-filter / index-first | L1, default-mechanical where host allows |
| loop-engineering | loop_lint + spec schema in L1; doctrine → brief |
| team-lead / plan-first-execute / lean-execution / wayfinder / caveman-ultra / fable-mode / standing-orders | role briefs or retirement via gate; no resident bodies |
| think | slash-only, weak-model tiers |
| prompt-triage | cede to host routing; keep only deterministic savings |
| brainer-audit | L3 shadow telemetry + event ontology (fix event kinds at normalization) |
| eval-gate / impact-of-change / security-oversight | L1 explicit analyzers |

## Measurement priorities (ordered)

1. **Long-horizon controlled experiment** — the suite's raison d'être has zero
   controlled evidence at any arm. Multi-hour sessions, 4–8 embedded
   requirements, midstream supersessions, two compactions, subagent handoffs,
   planted droppable constraints; FRONTIER vs OFF; measure requirement-survival
   recall, false-terminal-completion rate, recovery, cost. Decides whether the
   program is product or placebo; funds before any further guard tuning.
2. Reminder dose-response / habituation (does the 3rd injection change behavior?).
3. Longitudinal wiki lift (does session N+1 beat session N?).
4. Host-compaction A/B (checkpoint vs native).
5. Current-catalog end-to-end cost, re-measured every release.
