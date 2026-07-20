---
name: learn-skill
description: Experimental/manual skill-learning workflow retained for paired evaluation. Invoke explicitly with `/learn` or `/learn-skill`; it does not auto-load or install hooks.
status: experimental
disable-model-invocation: true
effort: low
tools: [Bash, Read, Grep, WebFetch]
auto-install: false
pulse_reminder: a learned skill is born `proposed` (slash-only, won't auto-fire) and its rationale must clear write-gate. Dedup before you create — patch, don't duplicate.
---

# learn-skill

<!-- split-justified -->

Brainer's `/learn`. Brainer could already *retrospect* a task you just did
([`task-retrospective`](../task-retrospective/SKILL.md)), but had no way to **ingest a
source you point at** into a skill (skill-creator was removed). This fills that gap —
a direct port of [Hermes' `/learn`](https://hermes-agent.nousresearch.com/docs/user-guide/features/skills).

**No new engine.** `/learn` is a *standards-guided prompt over existing tools*: you read
the source with WebFetch/Read/Grep/deep-research, then these stdlib helpers dedup, lint,
and scaffold the file. The only quality gate is [`write-gate`](../write-gate/SKILL.md)'s
rule scorer — no LLM judge in the write path.

## When to Use
- `/learn ~/projects/acme-sdk — focus on auth + pagination`
- `/learn https://docs.example.com/api/quickstart`
- `/learn how I just deployed staging` (from this conversation)
- `/learn filing an expense: open portal, New > Expense, attach receipt, submit`
- "turn this into a skill", "capture this as a skill", "make a skill from these docs".

Not for: auditing a task you already finished (→ `task-retrospective`); saving a single
durable *fact* (→ `wiki-memory` + `write-gate`). `/learn` produces a *procedure*.

## Procedure (5 steps)

1. **Source — extract literally.** Read the source with existing tools. Pull *exact*
   commands, code blocks, flags, paths, and error strings — NOT a prose summary.
   Summarization collapse (losing the literal commands that make a skill executable) is
   the #1 failure mode. If the source is a URL, `WebFetch` it; a dir, `Read`/`Grep` it.

2. **Dedup before write.** Don't birth a duplicate.
   ```bash
   python3 skills/learn-skill/tools/learn.py dedup \
     --desc "<one-line description of the candidate>" \
     --body-file /tmp/candidate_body.md      # optional: the drafted procedure
   ```
   - `CREATE` (exit 0) → proceed.
   - `LIKELY_PATCH` / `POSSIBLE_PATCH` (exit 3) → **abort and show the user the summary.**
     A similar skill exists (description overlap, or your candidate reuses commands that
     already live in another skill). Decide *with the user*: patch the existing skill, or
     re-frame this one. **No auto-merge.**

3. **Author to house standards.** Required sections, in order: `When to Use` /
   `Procedure` / `Pitfalls` / `Verification`. No invented commands (only cite tools that
   exist). Frame steps around real tools. `description ≤60 chars` is **advisory** — Brainer
   uses long rich descriptions for model-invocation triggering, and a proposed skill is
   slash-only, so a short description is fine until promotion. A skill is unshipped until
   its failure modes are declared ([LEARNING_CONTRACT §8](../_shared/LEARNING_CONTRACT.md#8-anticipate-at-ship-time--premortem-lifecycle-gauntlet)),
   and — if it ships a machine gate — until that gate has a negative test
   ([LEARNING_CONTRACT §3](../_shared/LEARNING_CONTRACT.md#3-mechanism-over-prose)).

4. **Gate the rationale.** The "why does this earn a skill" block must clear write-gate:
   ```bash
   python3 skills/write-gate/tools/write_gate.py gate --kind sop --file /tmp/rationale.md \
     && echo "earns a skill" || echo "rejected — revise or drop"
   ```
   Exit 1 → add the reason / cite evidence / drop the filler. No agent-only override.

5. **Write — born untrusted.** Scaffold the file:
   ```bash
   python3 skills/learn-skill/tools/learn.py scaffold \
     --name "<name>" --desc "<desc>" --source "<url-or-path>" \
     --when "..." --proc "..." --pitfalls "..." --verify "..." --rationale "..."
   # then validate it:
   python3 skills/learn-skill/tools/learn.py lint --file skills/<name>/SKILL.md
   ```
   The scaffold sets `status: proposed`, `disable-model-invocation: true` (won't auto-fire),
    `auto-install: true`, and stamps `source:` + `learned_at:` for later staleness checks.

6. **Weakest-executor acceptance test.** Before proposing, run the skill on the
   weakest model tier that will actually execute it — fresh context, an instance
   the skill was NOT authored from (a different input of the same class). The
   author's context always runs its own skill fine; the test is whether a dumb
   cold executor can. On failure, **fix the skill text, not the output** — that
   write-back is what converts one frontier authoring pass into a permanent
   cheap-tier execution path.

## Trust — earned by counted usage, not granted
A learned skill is **born `proposed` and cannot auto-fire.** Promotion to model-invocable
is **gated on real usage telemetry** — a hand-incremented counter would be a lie, so the
count comes from observed invocations.

```bash
# 1. Usage is logged. Either explicitly...
python3 skills/learn-skill/tools/telemetry.py record --skill <name> --outcome hit
# Abort records may attach: --verifier-cause ... --causal-status
# skill-caused|task-difficulty|model-capability|unknown --mechanism ... --evidence-ref ...
# ...or mined from a transcript (Skill tool_use → next-turn correction = abort, else hit):
python3 skills/learn-skill/tools/telemetry.py scan --transcript "$TRANSCRIPT_PATH"

# 2. Promote ONLY when the gate clears: >= N consecutive hits, no trailing abort, lints clean.
python3 skills/learn-skill/tools/learn.py promote --name <name> --min-successes 3
#   -> flips status: trusted + disable-model-invocation: false, else REFUSED with the count.

# 3. Demote a skill telemetry has flagged (>=3 consecutive aborts → review):
python3 skills/learn-skill/tools/telemetry.py flag --min-aborts 3
python3 skills/learn-skill/tools/learn.py demote --name <name> --reason "telemetry-flagged"
```

Promotion is a **closed gate** (generator = field usage; verifier = `learn.py promote`
reading telemetry — a separate actor). Spec in [`LOOPS.md`](LOOPS.md), lints clean. This is
Brainer doctrine: a skill earns its trigger by measured behavior, not by being authored.

## Staying fresh — sources drift, skills must too
A learned skill stamps `source:` + `learned_at:`. The staleness reconcile re-checks them
against ground truth (git history for repo paths, age for URLs — stdlib can't fetch, so a
stale URL is flagged for the agent to re-`WebFetch`):

```bash
python3 skills/learn-skill/tools/learn.py staleness --apply   # mark drifted skills status: stale
```
A `stale` skill is a promote candidate again only after a re-`/learn` refreshes its source.

## Getting nominated — the canary watches for capturable workflows
When a non-trivial multi-step workflow completes (≥6 tool calls, at a wrap-up turn,
not build/test/git boilerplate), `compliance-canary`'s `workflow_nomination` detector
nudges you to `/learn` it. It **nominates, never writes** — write-gate + dedup (in the
/learn flow) make the actual call. Shipped as [`drift_probes.json`](drift_probes.json);
the canary auto-discovers it. Silence per-deployment via `COMPLIANCE_CANARY_PROBE_IDS` (exact-id selection).

## Pitfalls
- **Summarization collapse** — the model writes "configure auth and paginate" instead of
  the literal `curl -H "Authorization: Bearer $T" .../page?cursor=...`. The skill becomes
  unrunnable. Force literal extraction in step 1.
- **Silent duplicate** — dedup on descriptions alone misses skills whose *bodies* overlap;
  the body-code scan (`--body-file`) catches reused commands. Always pass the drafted body.
- **Auto-fire too early** — never ship a learned skill as model-invocable. `proposed` +
  `disable-model-invocation: true` is non-negotiable for v1.
- **Patch ignored** — an exit-3 dedup verdict is advisory; treat it as a stop, not a hint.

## Verification
```bash
python3 skills/learn-skill/tools/test_learn.py        # 56: authoring/lifecycle + hidden-ID/sandbox/invariant/checkpoint rollback gates
python3 skills/learn-skill/tools/test_telemetry.py    # 18: record/scan/stats/flag/streaks + SQLite migration/concurrency/exact rollback
python3 skills/learn-skill/tools/test_nomination.py   # 7:  the canary nomination detector + boilerplate filters
python3 skills/loop-engineering/tools/loop_lint.py skills/learn-skill/LOOPS.md   # 0 fail · 0 warn
python3 skills/learn-skill/tools/learn.py lint --file skills/<name>/SKILL.md     # exit 0
```
A learned skill is "done" only when it passes its own `lint` and its rationale cleared
write-gate; it is "trusted" only when telemetry clears the promotion gate.

## Related skills
- [`write-gate`](../write-gate/SKILL.md) — the rationale gate (step 4).
- [`task-retrospective`](../task-retrospective/SKILL.md) — decides *what* to learn from a task you *did* and *which form* it takes; it calls `/learn` only when that form is a skill. `/learn` is the skill-authoring *mechanism* (it ingests a source you *point at*) — a different level, not a duplicate.
- [`wiki-refresh`](../wiki-refresh/SKILL.md) — will re-check the `source:` field for staleness (deferred follow-up).
- [`wiki-memory`](../wiki-memory/SKILL.md) — for durable *facts* rather than procedures.

## Conditional activation (won't misfire where its tools are absent)
A learned skill declares the external CLI tools it needs: `requires_tools: gh, jq`
(`/learn` / `scaffold --requires-tools` populates it). `learn.py check-tools --name X`
verifies them against this environment; the SessionStart nudge warns when a trusted skill's
deps are missing. Advisory — Claude Code has no native tool-gated hiding, so it surfaces a
would-misfire skill rather than hard-blocking it.

## Refinement — improve a failing skill, don't only retire it
When a trusted skill accrues aborts, patch it instead of just demoting:
```bash
python3 skills/learn-skill/tools/learn.py refine --name X     # read-only brief: body + abort evidence
python3 skills/learn-skill/tools/learn.py patch --name X --old '<exact text>' \
        --new '<fix>' --rationale '<why — because/so that>' \
        --gate-registry '<operator-owned frozen JSON ID-to-argv map>' \
        --held-in-id '<opaque-held-in-id>' \
        --held-out-id '<distinct-opaque-held-out-id>' \
        --gate-timeout-seconds 30 --gate-output-limit-bytes 16384
```
`refine` distinguishes confirmed `skill-caused` failures from `task-difficulty`,
`model-capability`, and `unknown`; it does not recommend a skill edit without confirmed
skill causality. `patch` is **gated**: held-in must fail and held-out pass before mutation;
after write-gate + patch + lint, both commands must pass and a final lint rechecks the
post-gate artifact. For self-improvement, the CLI receives only distinct opaque IDs; a
strict regular single-link registry snapshot beneath a non-symlinked, operator-controlled
parent hierarchy resolves them to shell-free argv and is unreadable
inside the gate sandbox. Hidden commands and their output are not surfaced in normal results or
errors. Legacy `--held-in-cmd`/`--held-out-cmd` remains available for compatibility outside this
proposer-hidden route. Commands run without a shell inside a write-denying, no-fork OS sandbox
and a fresh POSIX process group, default to a 30-second timeout each (finite, positive,
hard-capped at 300 seconds), and retain at most
16 KiB each. The sandbox permits reads plus writes only inside a private temporary directory;
it denies network and process creation, so a gate cannot detach a watcher or mutate/hardlink
the skill. Every exit path kills the original process group and verifies that no live member
remains. A host without that sandbox fails closed before spawning a behavior gate or
mutating the skill. Registry ancestry is checked for symlinks and its resolved leaf is
rechecked around every gate; this assumes the trusted parent hierarchy stays stable during
the command and does not claim descriptor-walk resistance to a hostile concurrent parent swap.
Gates are therefore
single-process: a command that itself needs subprocesses is refused by the sandbox. Every
gate must leave the target's regular-file type, single-link status, device/inode identity,
permission bits, and bytes unchanged. An initially hardlinked target is refused before any
gate or mutation. A mutation refuses the patch and safely
replaces the leaf without following a symlink, restoring a regular file with the pre-gate
bytes and mode. Outer rollback uses the same helper. "Exact restoration" means path type +
contents + permissions; it does **not** claim to restore the original inode. Changes outside
the target leaf
(including broader gate side effects) remain the harness/`locked_surfaces` owner's
responsibility. Telemetry uses stdlib SQLite WAL transactions; an existing JSONL store is
imported idempotently. Metadata rewrite is guarded by inode/type/link/mode/byte checks before
and after, and its checkpoint row is deleted by exact SQLite id if the final invariant changes.
On success it resets the skill to `proposed` and **checkpoints telemetry** so it re-earns
trust from a clean slate. Two failed
rounds → demote. The agent proposes; `patch` verifies — spec #5 in [`LOOPS.md`](LOOPS.md).

## The full self-improvement loop (all built)
1. **Author** a learned skill from a source (this skill) → born `proposed`, slash-only.
2. **Nominate** — the canary spots a capturable workflow and nudges `/learn` (never writes).
3. **Instrument** — `telemetry.py` logs each invocation's hit/abort (recorded or transcript-mined).
4. **Promote** — `learn.py promote` flips `proposed → trusted` once usage clears the gate.
5. **Refine** — a failing skill is patched (gated) and re-earns trust, *before* retiring.
6. **Reconcile** — `learn.py staleness` flags drifted sources; `check-tools` flags absent deps;
   `demote`/`flag` retire what can't be saved.

Honest limits (see [`EVAL.md`](EVAL.md)): transcript-mined outcomes are heuristic
(`source: inferred`); a strict operator counts `--manual-only`. Slash-literal invocations
that don't surface as a `Skill` tool_use aren't counted.

## Optional evaluation wiring
The root installer leaves these hooks disabled. For an explicit FULL arm,
`bash skills/learn-skill/tools/install.sh` wires two hooks into `.claude/settings.json`:
- **SessionEnd** → `telemetry scan` the transcript (APPEND-only usage log).
- **SessionStart** → a read-only nudge listing promote-ready / demote / stale skills.
  Silent unless actionable (cache-safe; only skills with a `learned_at` stamp are scanned).

Critically, the unattended path is **append/read-only** — it never mutates a skill. The
mutating steps (`promote` / `demote` / `staleness --apply`) stay agent-run behind the nudge
(loop-engineering: an unattended write path needs a gate; here the gate is the human/agent
reading the nudge). Spec #4 in [`LOOPS.md`](LOOPS.md) declares the `output_actions` allowlist
(scan-append, nudge-print only) and lints clean. Tune: `LEARN_SKILL_PROMOTE_MIN` /
`LEARN_SKILL_DEMOTE_MIN`.

**Codex** has no SessionStart/SessionEnd, so the installer wires **Stop** → per-turn
`telemetry scan --defer-trailing` (defers the just-fired invocation until its reply exists,
so hit/abort isn't judged early) and **UserPromptSubmit** → the same nudge. Codex transcripts
are a different schema, normalized to Claude shape via [`../_shared/transcript_norm.py`](../_shared/transcript_norm.py).
Codex has no discrete `Skill` tool_use, but it expands **every** skill invocation (slash OR
model-invoked) into an injected `<skill><name>…</name>` user block — the normalizer reads that
as the canonical invocation signal, so both kinds are auto-captured (verified live: a `/think`
followed by a correction recorded a `think` abort from the real Codex transcript).
