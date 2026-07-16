# self-improvement-loops loop spec

This policy adds a supplemental contract to the existing `loop-engineering`
spec. It does not define a runner or store. The example is a bounded refinement
of this proposed skill through existing `learn-skill` gates and telemetry.

```loop
name: self-improvement-policy-refinement
topology: closed · outer · single
self_modifying: true
generator: agent proposes one bounded patch to skills/self-improvement-loops/SKILL.md from confirmed skill-caused evidence
verifier: fresh-context verifier runs the frozen held-in and held-out commands plus loop_run_monitor.py; separate from the proposer
verifier_blind: true
verifier_inputs: task, candidate artifact, candidate diff, held-in result, held-out result, runtime trace; excludes proposer reasoning
gate: python3 skills/learn-skill/tools/learn.py patch --name self-improvement-loops --old OLD --new NEW --rationale WHY --gate-registry FROZEN_GATES.json --held-in-id held-in-v1 --held-out-id held-out-v1 && python3 skills/loop-engineering/tools/loop_run_monitor.py --resolved-spec loop.resolved TRACE.json
held_in_gate: opaque held-in ID resolved by existing learn.py patch from a frozen operator-owned JSON argv registry; targeted baseline fails and candidate passes
held_out_gate: distinct opaque held-out ID resolved from the same registry; baseline and candidate both pass, with at least one split strictly improved
stop: one artifact-bound candidate passes both frozen gates and owner approves promotion, or two rejected rounds halt and escalate
budget: max_iterations=2
editable_surfaces: skills/self-improvement-loops/SKILL.md only, one bounded patch
locked_surfaces: held-in and held-out commands, evaluator implementation and revision, skills/loop-engineering/tools, skills/learn-skill/tools, permissions, budgets, telemetry history
artifact_binding: loop_run_monitor.py trace binds every result to candidate_id, artifact_hash, evaluator_revision, diff_size, and trace_refs
human_approval: owner must approve evaluator or gate changes, editable-surface expansion, and production promotion
anchor_files: skills/self-improvement-loops/SKILL.md, skills/self-improvement-loops/EVAL.md, skills/self-improvement-loops/LOOPS.md, skills/loop-engineering/SKILL.md, skills/learn-skill/SKILL.md
state_store: .brainer/learn-skill/usage.sqlite3 (SQLite WAL; idempotent legacy JSONL import) plus the candidate trace consumed by skills/loop-engineering/tools/loop_run_monitor.py
recall: read learned-skill telemetry, current skill frontmatter, prior rejected trace_refs, and the frozen evaluator revision before each proposal
writeback: existing learn.py patch checkpoints telemetry; append candidate lineage and verifier verdict to the runtime trace without rewriting prior evidence
output_actions: edit skills/self-improvement-loops/SKILL.md max 1 per iteration; telemetry checkpoint max 1 per accepted patch; append candidate trace max 1 per iteration; default-deny all evaluator, locked-surface, promotion, git, and external actions
on_error: transient execution failure -> retry with backoff max 2; recoverable candidate failure -> record rejection and return observation; user-fixable config/auth/permissions or approval boundary -> interrupt; unexpected or locked-surface mutation -> halt and surface
stuck: accepted empty/trivial diff, repeated artifact_hash, same rejection twice, or two iterations without held-in/held-out improvement
advisor: skills/_shared/model_roster.py read-only divergent panel proposes a different rung or bounded edit and feeds the generator, never the verifier
redaction: model_roster.render_prompt scrubs secrets/.env/keys/PII via audit_redact before any cross-vendor egress
consent: human supplies explicit first-egress consent to model_roster --run; absent consent keeps the advisor local-only
```

Lint with:

```bash
python3 skills/loop-engineering/tools/loop_lint.py skills/self-improvement-loops/LOOPS.md
```
