# 2026-07-20 decision evidence manifest

Committed companion to `eval/FINDINGS.md`'s 2026-07-20 sections (the
`claim_without_evidence` ablation entries and the phase-2 lane notes). The
underlying research artifacts live only in the git-ignored
`.brainer/research/2026-07-skills-overhaul/` working directory, so a fresh
clone cannot reproduce the reasoning from FINDINGS.md alone — this file is
the tracked record of the key numbers, methods, limitations, and exact
replay commands for the day's three decisions. Sanitized: no transcript
content, no session filenames or hashes (none of the fire-value corpus's
session identifiers are public in `eval/FINDINGS.md`, so none are repeated
here; sessions are referred to below only by relative size/role — "Session A"
= the one long/dominant session, "Session B"/"Session C" = the two smaller
ones). `.brainer/sessions/raw/` is itself git-ignored, so a fresh clone would
not have the source transcripts regardless of filename.

This file does not restate or override `eval/FINDINGS.md`, which remains the
binding record; it is evidence backing, owned separately (orchestrator owns
FINDINGS.md).

## Decision 1 — `claim_without_evidence`: keep default-on, standing decision

**Decision.** Keep the `claim_without_evidence` compliance-canary probe
default-on. No cap/cooldown policy adopted. Causal lanes A/B/C (paired
fork-resume ablation) not run — this is a **cost-benefit judgment on
correlational evidence**, not a proven verdict. Standing, with a named
revisit trigger (fire volume or IGNORED rate rising materially, or a future
model-upgrade re-test flagging the probe).

**Key numbers.**
- Premise re-baseline: of 46 distinct fire events (block-sha dedup of 86 raw
  emissions across 3 non-empty Claude sessions — Session A: 69 raw/29
  distinct, Session B: 13 raw/13 distinct, Session C: 4 raw/4 distinct; a
  4th Claude session and 2 Codex sessions in the same corpus scored zero
  emissions and are not counted here), the **current** hook
  (post-2026-07-20 precision fix) fires on **14/46 (30.4%)** at probe level;
  `claim_without_evidence` is **14/14 (100%)** of those surviving probe
  fires. Of the 30 distinct events where the *original* corpus recorded
  `claim_without_evidence`, only **12/30 (40%) still fire** on the current
  hook — absolute volume dropped ~60-70%, but the probe's *share* of
  whatever still fires did not collapse (65.2% old distinct-basis share →
  100% probe-level / 66.7% any-reminder share now).
- Labels (corpus-wide, 100% of the 86 raw emissions reviewed): **ACTED 69,
  IGNORED 1, UNCLEAR 16**. (46 distinct events of that 86 raw — raw volume is
  inflated by compaction re-injecting byte-identical reminder blocks.)
- Cap-pricing replay (grid: session cap ∈ {1,2,3,5,10}, kind cap ∈ {1,2,3},
  cooldown ∈ {5,8} turns): **no policy in the grid suppresses zero labeled-
  ACTED events**; cheapest-loss policy in the grid is `cooldown_5`, losing
  12 ACTED events corpus-wide for ~13.5KB saved (13,457B distinct-fire-only,
  30,367B counting future re-injections of the same suppressed block). The
  loss is concentrated almost entirely in Session A (the long, high-volume
  session, 69 of 86 raw events) — no tested policy achieves zero ACTED
  loss there because its labeled-ACTED events recur to the very last ranked
  distinct fire. **Proxy caveat**: the cooldown simulation models a coarser
  same-*kind* mechanism (not the real hook's per-`probe_id` cooldown) and
  approximates turn distance from raw reminder-event ordinal position — it
  is exact for Session A (100% turn-level fire rate makes ordinal = turn
  number there) but an upper bound for the other two sessions. Individual
  ACTED/IGNORED/UNCLEAR labels cover only 31/46 (67%) of distinct fires at
  the per-event level for this replay; the remaining 33% are unlabeled at
  that granularity, and since every session's own aggregate skews
  ACTED-heavy, the true losses are more likely undercounts than overcounts.

**Method (2-3 sentences each, with limitations).**
- *Premise re-baseline*: each of the 46 distinct fire events' T1 context
  (transcript prefix + triggering prompt) was reconstructed from the raw
  session logs and replayed directly through `hook.py` (not `hook.sh`) with
  a fresh, isolated `CLAUDE_PROJECT_DIR`/state dir per event, to see if the
  current detector still fires on that same content. **Limitation**: this
  is conditional-on-old-fires replay — it answers "would the detector still
  classify this exact prior content as a trigger," not "would a real
  multi-turn, cooldown-aware session show a reminder today"; it cannot
  surface *new* fires on turns that were formerly silent, and the ledger
  (Mechanism 3) verdicts in the per-event table are not faithfully
  reconstructable from a single fresh-state replay (accumulated open-request
  history can't be regenerated from one turn), so they're reported for
  completeness only and don't affect the probe-level numbers above.
- *Persistence / labels*: ACTED/IGNORED/UNCLEAR is an **observational**
  same-session correlation judgment — a human(-in-the-loop) read of the next
  assistant turn(s) after each fire and judged whether the flagged claim/gap
  was visibly addressed, against the tool's fixed label set (no new labels
  invented). **Limitation**: this is not a controlled outcome-lift
  measurement; it cannot show what the assistant would have done *without*
  the reminder, only what it did after receiving it, and a nontrivial share
  of "UNCLEAR" reflects a real structural blind spot (synthetic wakeup
  pings with no user-facing content to tie a response to) rather than
  genuine ambiguity in engaged sessions.
- *Cap-pricing replay*: for each candidate suppression policy, the labeled
  corpus was replayed to count how many observed ACTED events that policy
  would have suppressed and how many bytes it would have saved — zero model
  calls. **Limitation**: this is a coarser-than-real cooldown model (see
  proxy caveat above; same-kind, not same-`probe_id`, and turn-distance is
  approximated by raw ordinal position for 2 of 3 sessions), and it prices
  policies against a partially-labeled, non-causal, non-random corpus (6
  transcripts, 86 raw emissions) — it cannot support a claim that
  suppression would have caused worse *outcomes*, only that it would have
  hidden observed ACTED-labeled correlations.

**Exact replay commands.**

`fire_value.py` invocation (produces the raw fire/byte/token counts and
per-event dedup used as the basis for every number above; run against the
most-recent-by-mtime substantial (>=100KB) raw transcripts under
`.brainer/sessions/raw/` at the time, both hosts present in that directory —
exact filenames omitted, see the sanitization note above):

```bash
python3 eval/skills_effectiveness/fire_value.py \
  .brainer/sessions/raw/<claude-session-1>.jsonl \
  .brainer/sessions/raw/<claude-session-2>.jsonl \
  .brainer/sessions/raw/<claude-session-3>.jsonl \
  .brainer/sessions/raw/<claude-session-4>.jsonl \
  .brainer/sessions/raw/rollout-<codex-session-1>.jsonl \
  .brainer/sessions/raw/rollout-<codex-session-2>.jsonl \
  --json-out .brainer/research/2026-07-skills-overhaul/fire-value-remeasure-2026-07-20.json \
  --markdown-out .brainer/research/2026-07-skills-overhaul/fire-value-remeasure-2026-07-20.md
```

(the output directory is git-ignored working-doc space, not a sensitive
path — any local directory works equally well)

Hook-replay approach (premise re-baseline — no ready-made script; the method
run per distinct event was): reconstruct the T1 transcript prefix up to and
including the triggering prompt into a scratch file, then invoke the hook
directly with a fresh isolated environment so no cross-event cooldown state
leaks between replayed events:

```bash
CLAUDE_PROJECT_DIR="$(mktemp -d)" \
COMPLIANCE_CANARY_STATE_DIR="$(mktemp -d)" \
COMPLIANCE_CANARY_SKILLS_ROOT="$(pwd)/skills" \
python3 skills/compliance-canary/tools/hook.py <<'JSON'
{"session_id": "<synthetic-per-event-id>", "transcript_path": "<scratch-prefix-file>", "hook_event_name": "UserPromptSubmit", "prompt": "<reconstructed triggering prompt>"}
JSON
```

(`COMPLIANCE_CANARY_PROBE_IDS` left unset — production default: the 3
`FRONTIER_VERIFY_PROBE_IDS` plus any `frontier_emit: true` probe;
`COMPLIANCE_CANARY_CORRECTION_LEDGER`/`_DISABLED`/`_COOLDOWN` popped from the
inherited environment so no stray override applies.)

## Decision 2 — cap/cooldown suppression: not adopted

**Decision.** No per-session cap, per-kind cap, or widened cooldown was
adopted for `claim_without_evidence` (or any probe). Folded into Decision 1
above — the cap-pricing replay showed no policy in the requested grid is
"free" (zero labeled-ACTED loss) corpus-wide, so the follow-up decision
table simplified to a binary keep/demote on the (unrun) causal lane B,
without a cap branch.

**Key numbers.** See Decision 1's cap-pricing numbers — restated here for
the cap-specific record: grid tested = session cap ∈ {1,2,3,5,10}, kind cap
∈ {1,2,3}, cooldown ∈ {5,8} turns. Corpus-wide the cheapest policy actually
in the grid (`cooldown_5`) still costs 12 lost ACTED events (of 46 distinct
fires, 20 suppressed total) for 13,457B saved (distinct-fire-only) / 30,367B
(counting re-injections). Diagnostic-only extension beyond the grid: a
session cap would need K≥29 and a per-kind cap K≥23 for the single dominant
session (Session A) to reach zero ACTED loss — neither is a real "cap" in
any practical sense.

**Method, with limitations.** Same zero-model-call replay as Decision 1's
cap-pricing method above: bucket distinct fires by session/kind/cooldown-
window and count suppressed vs. surviving labeled events. The proxy caveat
(coarser same-kind cooldown vs. the real per-`probe_id` mechanism;
turn-distance approximated by raw ordinal position, exact only for the one
100%-fire-rate session) applies identically here — this is exploratory
pricing of a **different, coarser hypothetical mechanism**, not a
tightening of the exact live one, and the "cap branch rejected" framing is
correlational (priced against observed, partially-labeled ACTED events), not
a proven claim that any tested cap would have degraded real outcomes.

**Exact replay commands.** Same `fire_value.py` invocation as Decision 1
(the cap-pricing replay consumes its JSON output). The per-policy simulation
itself is a bucketing/counting pass over the labeled distinct-fire table
(`cap-pricing-replay-2026-07-20.json`) — no separate live-session command;
it re-derives entirely from the `fire_value.py` output plus the
individually-attributed ACTED/IGNORED/UNCLEAR labels already gathered for
Decision 1.

## Decision 3 — sibling-retention table prepared

**Decision.** Prepared (not applied) a per-sibling skill-retention decision
table across the four propagated sibling repos (PROMPTER, screenery-lean,
screenery-design-master, farey-hecke) classifying each canonically-retired
skill still present in a sibling's `skills/` dir as RETIRE / KEEP / DECIDE.
No sibling file was mutated to produce it — read-only across all four repos,
confirmed via `git status --short` before/after. (A fifth, read-only sibling
— `product images repo`, mid-deferred-propagation — was added the same day;
see `.brainer/research/2026-07-skills-overhaul/sibling-retention-inventory-2026-07-20.md`
for the full, current table, including two 2026-07-20 KEEP→DECIDE
downgrades made after re-verifying the underlying test-dependency and
customized-wording evidence.)

**Key numbers.** 7 canonical-retired skill names recur across every sibling
(`fable-mode lean-execution plan-first-execute requirements-ledger
self-improvement-loops standing-orders wayfinder`), each with an
identically-worded ~86-179 byte resident catalog line. Confident-RETIRE
reclaimable bytes per sibling (unaffected by the later KEEP→DECIDE
downgrades, since those only moved bytes between the DECIDE and KEEP
columns): **PROMPTER 1292B, screenery-lean 599B, screenery-design-master
510B, farey-hecke 704B** — closing 85% / 70% / 45% of each repo's
boot-surface excess over canonical respectively (farey-hecke has no
sibling-original excess to compare against). The `product images repo`
fifth sibling carries the same 704B core-7 total but **0B** of it is
confident-RETIRE (dirty, mid-propagation tree — every row deferred).

**Method, with limitations.** Per sibling: diffed `skills/` directory names
against canonical HEAD's current 22-skill set; classified each extra as
canonical-retired (present in canonical's own git deletion history) or
sibling-original (never existed in canonical); measured the exact resident
catalog-line byte count between each sibling's `CLAUDE.md` sentinel markers;
searched for dependency evidence (`grep -rl <name>`, excluding the skill's
own dir and the three host files) and cross-checked hits inside
`compliance-canary`'s rehomed probe files against canonical's byte-identical
copy to distinguish genuine sibling-specific dependencies from
rehoming-note artifacts; used `SKILL.md` mtime plus each repo's own
`git status`/`git ls-files` tracking state as a secondary, weak dormancy
signal. **Limitation**: mtime is not reliable usage evidence — sync/
propagate operations bump it without invocation; dependency grep found real
functional wiring in only a minority of rows (most hits are either
rehoming-note artifacts or cross-references from other doomed-cohort
skills); and the two 2026-07-20 downgrades (screenery-lean `fable-mode`,
screenery-design-master `wayfinder`) show the original KEEP calls had
over-read weaker signals (a preserved test *fixture*, and *customized
wording* respectively) as stronger use-evidence than they actually were —
this table is qualitative triage, not a measured usage study.

**Exact replay commands.** No model-call or scripted replay — this decision
was produced by direct filesystem inspection (`ls`, `grep -rl`, `git log
--diff-filter=D`, `stat`) against each sibling's working tree, not a runnable
tool. To reproduce the byte counts: `sed -n '<line>p' CLAUDE.md | wc -c` on
the catalog line for each skill name, per sibling. To reproduce the
canonical-retired classification: `git log --oneline --diff-filter=D --
skills/<name>` run inside this canonical Brainer repo.
