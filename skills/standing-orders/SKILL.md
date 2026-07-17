---
name: standing-orders
description: "Experimental standing-directive probes retained for shadow telemetry and paired evaluation. Frontier profiles suppress their output; invoke manually only for an explicit evaluation arm."
status: experimental
disable-model-invocation: true
trigger_type: hook
risk_level: low
host_support: [claude, codex, gemini]
side_effects: [reads_repo]
requires_tools: [none]
auto-install: false
pulse_reminder: "standing-orders: big decomposable work → written goal, independent lanes in parallel, other-vendor advisor at commitment points, driven end-to-end with live verification — never partial-as-done. High-level → blindspot pass first; bank verified lessons at closeout."
---

<!-- split-justified -->

# standing-orders — the user's standing directives, mechanically armed

> **Shadow/manual during skill-effectiveness evaluation.** Probe matches may be
> logged by the canary shadow profile, but frontier leads receive no directive.

Two of the user's recurring instructions — "work like a real orchestrator on
big work" and "think before you commit, and bank what you learn on hard
work" — used to depend on the agent *remembering* to apply them. This skill
makes both **mechanical**: `compliance-canary`'s `prompt_intent` probes
(`skills/compliance-canary/tools/PROBES.md`) regex-match the CURRENT user
prompt and inject a directive the moment either shape appears, the same
trigger mechanism `loop-engineering` and `eval-gate` already use because
"the model will remember to load this skill" is unreliable on its own
(measured: blind agents don't auto-invoke a skill even with a strong
description).

## (a) What it is

### ORCH tier — self-set goal, parallel lanes, cheapest-capable delegation, driven to done

Fires on substantial, decomposable work: a multi-file feature, a migration,
a fleet of fixes, an end-to-end build. When armed:

- **Write an explicit end-to-end GOAL** before touching code — the shape
  `plan-first-execute` and `team-lead` §1 already require; a goal you can't
  finish writing means the decision isn't made yet.
- **Update the goal on results**, don't silently redefine it — if a lane's
  output changes what "done" means, restate the goal and say why, never
  drift into a different done-bar without naming the change.
- **Parallelize INDEPENDENT lanes only** — one subagent per lane, each with
  its own goal + done-means (`team-lead` §3's brief contract); two lanes
  touching the same file are one lane, or worktree-isolated. **Intervene on
  a drifting lane** rather than letting it wander: diagnose from evidence,
  fix the brief, respawn at the same tier (`team-lead` §4) — a lane failure
  is a brief/context problem first, not a reason to escalate tier.
- **Token economy ladder — frontier tokens are judgment only.** Route the
  volume down the ladder (`team-lead` §2, `ORCHESTRATION.md` §1-§2):
  `local-ollama` (free, on-box) → `glm-executor` (GLM-5.2, ~zero cost, 1M
  context — prioritized as the cheap-but-capable default before spending a
  frontier token) → `quick-fix`/`builder` (tiny → medium) → the leader's own
  frontier context only for genuinely hard reasoning it cannot delegate.
  Escalate tier on a diagnosed capability gap, never on failure count.
- **Other-vendor advisor at commitment points.** Before an architecture
  choice, migration, API shape, or wide-blast-radius refactor, consult a
  **cross-vendor** frontier advisor (`ORCHESTRATION.md` §6's commitment-
  boundary rule), resolved via
  [`skills/_shared/model_roster.py`](../_shared/model_roster.py)'s
  `pick_panel(exclude_lane=...)` — it excludes the generator's own vendor
  lane for diversity. Generalized by host: on a Claude host the advisor is
  the strongest reachable GPT (`codex exec` CLI or the codex plugin); on a
  GPT/Codex host it is the strongest reachable Claude (`claude -p` CLI, the
  Claude plugin, or an MCP Claude tool). Act on the verdict or surface the
  disagreement — never silently absorb it.
- **End-to-end-to-done, never partial-as-done.** Drive the goal through
  impl → tests → review → **live verification** — for a UI/browser-facing
  change that means actually exercising the real path (browser/computer-use,
  not a mock), per `verify-before-completion`'s Live Proof rule ("ship/merge-
  ready without Live Proof" is an explicit non-claim there). Reporting
  partial progress as "done" is the exact failure `verify-before-completion`
  and the `completion_without_closure` / `claim_without_evidence` probes
  already guard — this tier's job is to make sure the goal was actually
  end-to-end, not just to re-gate the claim.
  **Three legitimate stop conditions**, and only these: (1) **missing
  credentials** — a secret, API key, or access the agent cannot obtain
  itself; (2) **destructive ambiguity** — the next step is irreversible
  (delete, force-push, send, migrate data) and the goal doesn't disambiguate
  which of two outcomes is wanted; (3) **conflicting requirements** — two
  parts of the ask cannot both be satisfied and only the user can pick.
  Anything else ("this is hard", "this will take a while", "I could ask
  first") is not a stop condition — it's the work.

### DEEP tier — blindspot pass, verified-lesson capture

Fires on high-level tasks — architecture, strategy, an unfamiliar domain,
a postmortem. When armed:

- **Blindspot pass BEFORE committing to an approach** — the same move
  `plan-first-execute` names for unfamiliar territory: enumerate the unknown
  unknowns before drafting anything. Concretely: what questions should be
  asked that haven't been; what does "good" look like here (a reference
  implementation, a house style, a spec); what prior/historical work already
  exists (this repo's wiki, an earlier attempt, an upstream pattern); which
  known potholes recur in this class of task. A quick delegated survey, not
  a research project.
- **Collect lesson candidates DURING work**, not only at the end — both
  **corrections** (the user said "no, do X instead") and **confirmed
  approaches** (a choice that worked and why), each tagged with the *why* it
  mattered. `write-gate`'s content gate already requires a why-clause for
  any decision; capturing it live means it's not reconstructed from memory
  later.
- **At closeout, persist only VERIFIED lessons** through the standard pipe:
  `write-gate` (content-quality gate, scope classification) →
  `wiki-memory` (the actual write path). Shape rules (`write-gate`'s "What
  earns a memory" + `task-retrospective`'s destination ladder):
  - **One lesson per file**, with a **one-line summary at the top** (the
    frontmatter `description:`) — atomic by contract in the cross-session
    memory dir; the repo wiki instead prefers fewer, richer pages, but each
    still opens with a one-line summary.
  - **No duplicates — update the existing note instead** of writing a new
    one that says almost the same thing (`wiki.py overlap`'s dedup-at-write
    job).
  - **Delete a note that turns out wrong** rather than leaving it to rot —
    git is the archive; a falsified page is removed, not left stale.
  - Candidates are collected **during** the task but only **persisted after
    verification** — an unverified "this seemed to work" does not earn a
    page (write-gate's execution-gate sibling, `verify-before-completion`,
    already requires the action to have run and passed first).

## (b) Trigger design

Two `prompt_intent` probes in [`drift_probes.json`](drift_probes.json),
matched by `compliance-canary`'s `detect_user_correction` detector (the same
mechanism `prompt_intent` and `user_correction` share — see `PROBES.md`)
against the CURRENT user prompt, every turn:

| id | fires on |
|---|---|
| `orch-tier-intent` | build/migrate/refactor/port-family verbs + object, move/convert/replace/break-dependency phrasing, write+object, all/entire/whole/every-scoped fix/audit/update, end-to-end, make-tests-pass, ship-a-feature, multi-conjunct asks, test-and-fix, and the explicit fleet-orchestration phrases absorbed from `loop-engineering`'s (now-retired) `fleet-orchestration-intent` probe |
| `deep-tier-intent` | architecture/strategy/tradeoff/roadmap/postmortem/retrospective language, a restricted "how should/do/to (i/we)? PLANVERB" approach-question form, unfamiliar-domain phrasing, and an X-vs-Y comparison |

Both can fire on the same prompt (a task that is both strategic AND
decomposable — e.g. "design the new caching layer and wire it up to all
endpoints" arms both tiers, correctly).

**Bypass:** no dedicated bypass token is wired (see Honest limitations —
`unless_pattern` is not implemented for this probe kind). To skip a tier for
one turn, say so explicitly in the prompt ("skip the goal-writing, just
patch this one line") — the agent should honor an explicit override even
though the probe still fires; the probe is a nudge into context, not a gate
that blocks anything.

## (c) HONEST LIMITATIONS

- **UserPromptSubmit cannot re-anchor mid-turn.** The probes fire once, when
  the user's prompt lands — a single long agent turn that drifts internally
  (starts end-to-end, quietly stops at "tests pass") gets no fresh nudge
  until the NEXT user prompt. The `pulse_reminder` above re-anchors on
  `compliance-canary`'s periodic cadence, and the symptom-level probes it
  already ships (`completion_without_closure`, `claim_without_evidence`,
  `early_stop`) catch the DOWNSTREAM symptoms of that drift within the same
  session — but neither is a substitute for a probe that could re-check
  mid-turn, because none exists on this host.
- **Hookless hosts degrade to the resident catalog.** On a host with no
  `UserPromptSubmit` hook (`codex` CLI, `gemini` CLI without the migrated
  hook set — see `docs/HOST_CAPABILITY_MATRIX.md`), neither probe fires
  mechanically; the RULE still binds, but only via the resident one-line
  catalog entry in `CLAUDE.md`/`AGENTS.md`/`GEMINI.md` — the agent has to
  recognize the trigger itself and apply the doctrine above by hand. This is
  the same degradation every other `prompt_intent`-based skill in this repo
  accepts (`loop-engineering`, `eval-gate`, `wiki-memory`, `write-gate`,
  `baton`, `propagate`).
- **`prompt_intent` does not support `unless_pattern`.** Confirmed by
  reading `hook.py`: `DETECTORS["prompt_intent"] = detect_user_correction`,
  and `detect_user_correction` never reads `probe.get("unless_pattern")` —
  only `detect_forbidden_regex` does. Adding an `unless_pattern` field to
  either probe here would be a silent no-op (an alive-looking-dead gate),
  so neither probe declares one. Negation is instead guarded with a
  fixed-width negative lookbehind on the single highest-risk bare trigger
  (`use your team`) — this only catches negation immediately adjacent to
  the trigger ("don't use your team"), not phrase-separated negation ("no
  need to use the team here"). The regex layer deliberately does NOT treat
  bare "keep going" / "continue" as ORCH-decomposable signals for the same
  reason — a holdout fixture (`tools/corpus_holdout.jsonl`) includes a
  none-labeled "keep going, add another test case for the plus operator"
  trap specifically to prove those words alone are not evidence of
  substantial work.
- **The regex layer misses some implicit big tasks — measured, not
  assumed.** On the tuning corpus (`tools/corpus_tuning.jsonl`, 56 prompts):
  ORCH recall 28/28 (100%) over `orchestrate`+`both`, DEEP recall 27/28
  (96.4%) over `deep`+`both` — one accepted miss, "what db access pattern
  fits this data model" (a bare implicit architecture question with no
  strategy/approach marker word at all), 0/14 false fires on `none`-labeled
  prompts for either probe. On the adversarial holdout corpus
  (`tools/corpus_holdout.jsonl`, 56 prompts, deliberately varied vocabulary
  plus "no subagents"/"don't"/"keep going" red herrings): ORCH recall 28/28,
  DEEP recall 28/28, 0/14 false fires. Both clear the ≥0.85 floor with
  margin, but a sufficiently novel phrasing outside either corpus's
  vocabulary can still slip past silently — this is a regex, not a
  classifier; there is no confidence score to fall back on.
- **The `X vs Y` DEEP trigger is intentionally broad** (`\bvs\.?\b` between
  any two tokens) to catch terse comparisons ("evaluate build vs buy",
  "kafka vs rabbitmq") without a marker word nearby. Real-world false
  positives on a casual, non-technical "X vs Y" are accepted — a spurious
  DEEP nudge only adds an unwanted blindspot-pass reminder, it never blocks
  or auto-acts, so the cost of over-firing here is much lower than the cost
  of under-firing on a genuine architecture question.

## (d) Deep-dive

The tuning guide (pattern locations, fixture corpora, the re-run-the-gate
command), the failure-modes premortem, and the relationship to `team-lead` /
`ORCHESTRATION.md` §6 / `loop-engineering` are covered in the linked
companion doc: [`REFERENCE.md`](REFERENCE.md).
