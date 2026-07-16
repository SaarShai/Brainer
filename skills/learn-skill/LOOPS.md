# learn-skill loop specs

The five self-improvement mechanisms are loops. Per `loop-engineering`, each names a
generator, a SEPARATE verifier, a machine-checkable gate, a stop, and a budget. Lint:
`python3 skills/loop-engineering/tools/loop_lint.py skills/learn-skill/LOOPS.md`

## 1. Counted promotion gate (makes "born untrusted" real)
A learned skill earns model-invocation only when accumulated usage clears the gate. The
verifier (`learn.py promote`, reading telemetry) is a different actor from the generator
(usage accumulating in the field).

```loop
name: learned-skill-promotion-gate
topology: closed · inner · single
generator: accumulated /skill usage recorded by telemetry.py (hits/aborts)
verifier: learn.py promote reading telemetry stats (separate actor from the usage)
gate: python3 skills/learn-skill/tools/learn.py promote --name SKILL --min-successes 3
stop: skill flipped to status trusted, or promote exits 1 with a reason
budget: max_iterations=1
```

## 2. Workflow nomination watcher (nominate, never auto-write)
The compliance-canary detector nudges `/learn` at a non-trivial wrap-up. The actual
"earns a skill" decision is the SEPARATE verifier downstream: write-gate + dedup inside
the /learn flow. The nudge writes nothing.

```loop
name: workflow-nomination-watcher
topology: closed · outer · single
generator: compliance-canary workflow_nomination detector (nudges /learn at wrap-up)
verifier: write-gate + learn.py dedup, run later inside the /learn flow (separate actor)
gate: python3 skills/write-gate/tools/write_gate.py gate --kind sop --file RATIONALE.md
stop: agent runs /learn (nomination consumed) or declines it as one-off
budget: max_iterations=1
anchor_files: skills/learn-skill/SKILL.md, skills/learn-skill/drift_probes.json
state_store: .brainer/compliance-canary/<sid>.json
recall: canary reads probe_history (per-probe cooldown) before re-nudging
writeback: canary records the fired probe turn into probe_history
on_error: transient tool failure -> retry with backoff max 2; recoverable rationale/dedup refusal -> return observation; user-fixable config/auth/permissions -> interrupt; unexpected -> halt and surface
```

## 3. Staleness reconcile (sources drift; skills must too)
Re-checks each learned skill's `source:` against ground truth (git history for repo
paths, age for URLs). The verifier is the agent re-fetching the flagged source and
re-running /learn (write-gate re-gates) — separate from the detector.

```loop
name: learned-skill-staleness-reconcile
topology: closed · outer · single
generator: learn.py staleness (flags sources whose git history advanced past learned_at)
verifier: agent re-fetches the flagged source and re-/learns; write-gate re-gates (separate actor)
verifier_blind: true
verifier_inputs: task, outputs (source ground truth, skill source/learned_at, staleness output)
gate: python3 skills/learn-skill/tools/learn.py staleness --apply
stop: staleness reports no STALE rows (every source fresh or rechecked)
budget: max_iterations=5
anchor_files: skills/learn-skill/SKILL.md
state_store: each learned skill's SKILL.md frontmatter (status / source / learned_at)
recall: read every learned skill's source: and learned_at: frontmatter
writeback: mark status stale on drifted skills (--apply); re-stamp learned_at on re-learn
on_error: transient fetch failure -> retry with backoff max 2; recoverable stale output -> return observation; user-fixable auth/permissions -> interrupt; unexpected -> halt and surface
```

## 4. Unattended curation (the session-hook loop)
SessionEnd scans usage (append-only); SessionStart surfaces promote-ready / demote /
stale skills (read-only). The skill-MUTATING step stays the SEPARATE agent/human actor
behind the gate — the unattended path may only append + print (R10 allowlist).

```loop
name: learned-skill-unattended-curation
topology: open · outer · single
generator: SessionEnd telemetry scan (append-only usage) + SessionStart nudge (read-only surface)
verifier: the agent/human who reads the nudge and runs the gated promote/demote (separate actor)
verifier_blind: true
verifier_inputs: task, outputs (nudge, telemetry stats, learned-skill frontmatter)
gate: python3 skills/learn-skill/tools/learn.py promote --name SKILL --min-successes 3
stop: SessionStart nudge surfaces nothing (no promote-ready / demote / stale skill)
budget: max_iterations=1
accepted_open_loop: true
output_actions: telemetry-scan-append, nudge-print (NO promote/demote/staleness-apply/SKILL.md-write unattended)
anchor_files: skills/learn-skill/SKILL.md, skills/learn-skill/drift_probes.json
state_store: .brainer/learn-skill/usage.sqlite3 (SQLite WAL; idempotent legacy JSONL import) + each learned SKILL.md frontmatter
recall: SessionStart reads transactional telemetry stats + each learned skill's frontmatter
writeback: SessionEnd transactionally inserts inferred usage; the gated promote/demote writes frontmatter (agent-run)
on_error: transient hook read failure -> retry with backoff max 2; recoverable malformed record -> skip and surface; user-fixable config/permissions -> interrupt; unexpected -> halt and surface
```

## 5. Refinement (improve a failing skill, don't only retire it)
When a trusted skill accrues aborts, the agent reads `learn.py refine`'s brief (body +
structured abort evidence) and proposes a fix only from confirmed skill-caused failures;
`learn.py patch` is the SEPARATE verifier (behavioral baselines + write-gate + lint +
post-patch behavior). A successful patch resets the skill to
`proposed` and checkpoints telemetry so it re-earns trust. Two failed rounds → demote.

```loop
name: learned-skill-refinement
topology: closed · inner · single
generator: agent proposes a patch from confirmed skill-caused evidence in the learn.py refine brief
verifier: learn.py patch gates — opaque held-in/out IDs resolve from a frozen regular single-link JSON argv registry under a stable operator-controlled non-symlink parent hierarchy; held-in fails and held-out passes before mutation; every gate runs in a write-denying/no-fork OS sandbox plus a fresh process group, cannot read the registry, terminates and verifies the group on every exit path, refuses initial hardlinks, and keeps the target invariant (regular type + single link + identity + mode + bytes); timeout is finite/positive and hard-capped at 300 seconds; write-gate + pre/post lint; both behavioral commands pass after mutation; metadata/checkpoint boundaries are rechecked under open inode guards and an invalidated checkpoint is deleted by exact SQLite row id; safe rollback restores regular type + bytes + mode without following symlinks (separate from the author)
verifier_inputs: candidate diff, rationale, held-in result, held-out result, and lint result; excludes generator reasoning
gate: python3 skills/learn-skill/tools/learn.py patch --name SKILL --old OLD --new NEW --rationale WHY --gate-registry FROZEN_GATES.json --held-in-id held-in-v1 --held-out-id held-out-v1 --gate-timeout-seconds 30 --gate-output-limit-bytes 16384
stop: patch applied (skill reset to proposed + telemetry checkpointed), or budget hit → demote (retire)
budget: max_iterations=2
stuck: same skill still aborts after 2 refinement rounds
advisor: skills/_shared/model_roster.py cross-vendor panel — propose a structurally different fix (feeds the agent, not the gate)
redaction: model_roster.render_prompt scrubs secrets/.env/keys/PII via audit_redact before the skill body + abort evidence egress to the advisor panel
```
