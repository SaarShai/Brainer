# Live canary fires (claim_without_evidence), session 62ae33f7, 2026-07-19/20
# Context: each fired on an assistant reply that was SUMMARIZING work already verified
# (evidence quoted in that reply or in immediately-prior tool uses/turns), or reporting
# status of background agents — not claiming new unverified work.

## FIRE 1 (2026-07-20T04:34:39.711Z)

### assistant reply preceding the fire:
```
Cold verification is running (independent read-only verifier re-running all suites against the branch). I'll report the verdict when it lands. Interim state:

**Done so far:**
- **Goals registered** (task 1): six purposes + scope rule now resident in [CLAUDE.md](CLAUDE.md), AGENTS.md, GEMINI.md (outside install sentinels) + wiki concept page. Committed to main as `8eaa45e`.
- **Sessions harvested** (task 2, via codex luna digests): the desktop "effectiveness review" session had already concluded **"contraction, not expansion"** — verdict "1 of 6 goals genuinely served"; null FRONTIER-vs-OFF result; adopted migration map in [TARGET_ARCHITECTURE.md](docs/TARGET_ARCHITECTURE.md). Ralph session: queue scrapped, "don't add machinery". Routing session: adversarial review returned REDUCE. Nobody had executed the contraction — that became the plan.
- **Built on branch `simplify-2026-07-19`** (worktree, main untouched): retired 7 doctrine skills (standing-orders, self-improvement-loops, requirements-ledger, wayfinder, fable-mode, plan-first-execute, lean-execution) → **31→24 skills**; rehomed their 5 still-valuable mechanical probes into compliance-canary; purged all forward references (codex terra did the mechanical purge); resident boot block **8012→7237 bytes**; canary intent capture (no-drop guarantee) untouched.
- **My verification**: run_all_tests **105/105**, canary **188/188**, frontier-defaults 16/16, exp8 OK. One health fail (H4b) is a pre-existing untracked runtime artifact, unrelated.

Also noted: local `main` is **9 commits ahead of origin** — yesterday's routing-hardening commits were never pushed.
```

## FIRE 2 (2026-07-20T04:48:17.791Z)

### assistant reply preceding the fire:
```
Verifier's C2 defect fixed and committed (`182e906`): conflict registry pruned (gate exits 0, 4/4 pytest), stale INSPIRATION/specs wording corrected, retired eval arms removed since `kaggle_notebook.py` globs them into live runs. `make check` now shows `run_all_tests: 101/101 PASS` with only the pre-existing H4b runtime-artifact check failing — same as any fresh checkout of main.

All 7 verifier criteria now effectively green (C1, C3–C7 passed cold; C2's named defects are fixed and re-gated). Remaining input: Kimi K3's adversarial report — wake armed on its process; final reconciliation and merge verdict then.
```

## FIRE 3 (2026-07-20T05:13:59.940Z)

### assistant reply preceding the fire:
```
Symlinks removed (staged). Both reviewers are now in, so the 4-minute polling loop is retired. Remaining in flight: the builder lane applying the shared Kimi/Sol fixes — when it reports READY FOR JUDGING I'll cold-verify, fold in the symlink removal, commit, re-run the full gates, and deliver the consolidated four-seat merge recommendation.
```

## FIRE 4 (2026-07-20T05:33:23.607Z)

### assistant reply preceding the fire:
```
**Merged and shipped:** `cad2683` on `main`, pushed (`8eaa45e..cad2683`), post-merge suite 105/105 PASS, `install.sh` re-run pruned all 7 retired-skill symlinks, old worktree and branch cleaned up.

**Phase 2 underway** on new branch `simplify-phase2` (same isolated-worktree discipline). Scoped to the uncontested consolidated backlog — I dropped the wiki-trio and learn-skill/task-retrospective merges since Sol argued against both and there's no measured case yet:

Three disjoint builder lanes running now:
1. **Plugin zero-probe fix** — make plugin-only installs discover packaged probes (`COMPLIANCE_CANARY_SKILLS_ROOT` fallback) + regression test. Sol's top finding.
2. **Unwired-machinery deletion** — `loop_run_monitor.py` (752+732 lines), `artifact_guard.py` (242), `scripts/skill-templates/`, watch pairs, `remeasure_baseline.sh`, empty caveman `tools/`; I verified zero production callers before authorizing each.
3. **Posture/doc contradictions** — 8 items (eval-gate label drift, stale default-on claims, task-retrospective authority contradiction, propagate dual source-of-truth, etc.).

Sequenced after those land (both touch canary):
4. Rehome verify-before-completion's 5 default-on probes into canary (kills the split-brain).
5. Retire `legacy`/`shadow` canary profiles (~1,250 lines) — the judgment-dense one; I'll design the LEARNING_CONTRACT §2 resolution myself (rehome minimal correction-capture into frontier per canon, not delete) and delegate the mechanics.

Each lane reports READY FOR JUDGING; I cold-verify before committing, full gates before any merge proposal.
```

## FIRE 5 (2026-07-20T05:47:33.778Z)

### assistant reply preceding the fire:
```
Lane 3 (posture/doc fixes) reports READY FOR JUDGING — all 8 items fixed, with two flags I'll chase in the cold verify: (1) it observed a transient mid-task race where the shared worktree briefly appeared reverted (matching the known dirty-tree failure pattern from memory) and had to re-apply its edits; (2) the suite showed `102 passed, 1 FAILED: py-syntax` from files lane 2 deleted mid-run — expected to clear once lane 2's suite-row cleanup lands. Waiting on lane 2's report, then I'll verify all three lanes' edits actually coexist on disk (race check included) before committing.
```

## FIRE 6 (2026-07-20T06:04:09.027Z)

### assistant reply preceding the fire:
```
Lane-5 design settled while lane 4 runs. Key facts mapped:

- `legacy`/`shadow` surface: ~12 branch sites in `hook.py`, the profile-parameterized A/B harness under `eval/skills_effectiveness/` (manual, but live code), `test_profiles.py`, and ~350 legacy-profile lines in canary's SKILL.md.
- The LEARNING_CONTRACT §2 decision (Kimi's "forced choice"): §2 says a user correction is closeout-blocking **unconditionally**, and the canon memory pins the correction ledger as one of its mechanical enforcers — but it currently only runs in the non-default `legacy` profile, i.e. the contract is already silently unenforced by default. Deleting the clause would contradict canon and the user's standing "corrections are the highest-value learning source / bias to over-capture" position. **Decision: retire both profiles, and rehome a minimal §2 enforcement into `frontier`** — the `user_correction` detector plus correction-ledger surfacing (fires only on correction-shaped prompts, so default-noise risk is bounded), while `shadow`'s measurement role collapses into the existing `frontier`/`off` A/B arms.

This lane must wait for lane 4 (both rewrite `hook.py`/`test.sh`/SKILL.md), so it launches on lane 4's landing. Then: full gates → Kimi K3 + Sol xhigh adversarial audits of the whole phase-2 branch → reconciled report.
```

## FIRE 7 (2026-07-20T06:04:09.071Z)

### assistant reply preceding the fire:
```
Lane-5 design settled while lane 4 runs. Key facts mapped:

- `legacy`/`shadow` surface: ~12 branch sites in `hook.py`, the profile-parameterized A/B harness under `eval/skills_effectiveness/` (manual, but live code), `test_profiles.py`, and ~350 legacy-profile lines in canary's SKILL.md.
- The LEARNING_CONTRACT §2 decision (Kimi's "forced choice"): §2 says a user correction is closeout-blocking **unconditionally**, and the canon memory pins the correction ledger as one of its mechanical enforcers — but it currently only runs in the non-default `legacy` profile, i.e. the contract is already silently unenforced by default. Deleting the clause would contradict canon and the user's standing "corrections are the highest-value learning source / bias to over-capture" position. **Decision: retire both profiles, and rehome a minimal §2 enforcement into `frontier`** — the `user_correction` detector plus correction-ledger surfacing (fires only on correction-shaped prompts, so default-noise risk is bounded), while `shadow`'s measurement role collapses into the existing `frontier`/`off` A/B arms.

This lane must wait for lane 4 (both rewrite `hook.py`/`test.sh`/SKILL.md), so it launches on lane 4's landing. Then: full gates → Kimi K3 + Sol xhigh adversarial audits of the whole phase-2 branch → reconciled report.
```

## FIRE 8 (2026-07-20T04:34:39.711Z)

### assistant reply preceding the fire:
```
Cold verification is running (independent read-only verifier re-running all suites against the branch). I'll report the verdict when it lands. Interim state:

**Done so far:**
- **Goals registered** (task 1): six purposes + scope rule now resident in [CLAUDE.md](CLAUDE.md), AGENTS.md, GEMINI.md (outside install sentinels) + wiki concept page. Committed to main as `8eaa45e`.
- **Sessions harvested** (task 2, via codex luna digests): the desktop "effectiveness review" session had already concluded **"contraction, not expansion"** — verdict "1 of 6 goals genuinely served"; null FRONTIER-vs-OFF result; adopted migration map in [TARGET_ARCHITECTURE.md](docs/TARGET_ARCHITECTURE.md). Ralph session: queue scrapped, "don't add machinery". Routing session: adversarial review returned REDUCE. Nobody had executed the contraction — that became the plan.
- **Built on branch `simplify-2026-07-19`** (worktree, main untouched): retired 7 doctrine skills (standing-orders, self-improvement-loops, requirements-ledger, wayfinder, fable-mode, plan-first-execute, lean-execution) → **31→24 skills**; rehomed their 5 still-valuable mechanical probes into compliance-canary; purged all forward references (codex terra did the mechanical purge); resident boot block **8012→7237 bytes**; canary intent capture (no-drop guarantee) untouched.
- **My verification**: run_all_tests **105/105**, canary **188/188**, frontier-defaults 16/16, exp8 OK. One health fail (H4b) is a pre-existing untracked runtime artifact, unrelated.

Also noted: local `main` is **9 commits ahead of origin** — yesterday's routing-hardening commits were never pushed.
```

## FIRE 9 (2026-07-20T04:48:17.791Z)

### assistant reply preceding the fire:
```
Verifier's C2 defect fixed and committed (`182e906`): conflict registry pruned (gate exits 0, 4/4 pytest), stale INSPIRATION/specs wording corrected, retired eval arms removed since `kaggle_notebook.py` globs them into live runs. `make check` now shows `run_all_tests: 101/101 PASS` with only the pre-existing H4b runtime-artifact check failing — same as any fresh checkout of main.

All 7 verifier criteria now effectively green (C1, C3–C7 passed cold; C2's named defects are fixed and re-gated). Remaining input: Kimi K3's adversarial report — wake armed on its process; final reconciliation and merge verdict then.
```

## FIRE 10 (2026-07-20T06:39:44.092Z)

### assistant reply preceding the fire:
```
Lane 5 (profile retirement) is alive and mid-work — its last edit landed 8 seconds ago. Progress so far:

- **Branch state**: still at commit `6e08c04` (Phase 2b probe rehome, committed and verified). Nothing new committed yet, as expected — the builder doesn't commit.
- **Lane 5 activity**: 232 transcript events so far; it's currently deep in [hook.py](skills/compliance-canary/tools/hook.py), stripping the legacy/shadow profile branches. The in-progress diff is already **−226 / +33 lines** on hook.py alone — consistent with the ~12 legacy/shadow branch sites being deleted and the minimal Mechanism-4 rehome being added.
- Still ahead of it per the brief: `test_profiles.py` updates, SKILL.md condensation, external consumers in `eval/skills_effectiveness/`, docs, and the verbatim verification runs (test.sh 188, test_profiles, run_all_tests, the two smoke tests).

Given it just started the main file, I'd estimate it's roughly a third of the way through. I'll be notified automatically when it reports READY FOR JUDGING; then I cold-verify, commit, run `make check`, and launch the Kimi K3 + Sol xhigh adversarial audits you asked for.
```

## FIRE 11 (2026-07-20T07:02:11.343Z)

### assistant reply preceding the fire:
```
Task #11 marked in progress mentally — the audits are running, and the `cases.py` builder lane is launched. Here's the answer to your codex question, from direct inspection just now:

## Are the skills operational in both Claude desktop app and Codex?

**Claude (desktop app / Claude Code): yes, verified live in this very session.** `.claude/skills/` has all 24 current skills symlinked, the hooks are wired in settings, and I can point to proof from today: the context-keeper PreCompact hook ran during your `/compact` (its output is in your terminal — "structured memory saved…"), and the compliance-canary hook fired a real drift probe at me mid-session. Both default hooks demonstrably deliver.

**Codex: yes, installed and refreshed — with known, documented limits.** The recent setup attempt appears to have succeeded, and it was re-run as part of yesterday's phase-1 merge (I re-ran `./install.sh` after merging, which refreshed everything at Jul 19 22:29). Current state:

- `.codex/skills/` — all 24 skills symlinked, stale links for the retired skills pruned.
- `AGENTS.md` — carries the resident skills catalog, byte-identical to the one in `CLAUDE.md` (I diffed them just now). This is the main mechanism: Codex reads AGENTS.md at boot, so a Codex agent sees the same catalog and loads skill bodies from `skills/<name>/SKILL.md` on trigger.
- `.codex/hooks.json` — freshly written, wiring two events: `UserPromptSubmit` → compliance-canary and `Stop` → context-keeper's session archive.
- Delivery is not just configured but **live-observed**, per [docs/HOST_CAPABILITY_MATRIX.md](docs/HOST_CAPABILITY_MATRIX.md): exactly-once `UserPromptSubmit` delivery was observed in both native Codex CLI and Codex Desktop, and a `Stop` archive was observed in Codex Desktop.

The honest caveats (all documented in the capability matrix, by design — "honest degradation"):

1. **No `PreCompact` in Codex** — so context-keeper's pre-compaction state extraction doesn't run there; only the Stop-time archive does.
2. **No `Agent` tool in Codex CLI** — team-lead orchestration falls back to CLI dispatch (`codex exec`), and codex must run unsandboxed on macOS (sandboxed shells segfault on keychain access).
3. **brainer-audit's full event set is unverified on Codex** — installed, but only the two events above have live delivery evidence; the matrix explicitly says config proves installation, not delivery.
4. Most skills are plain markdown + python/bash, so they work identically on any host regardless of hooks — what degrades on Codex is only the *automatic* firing, and the resident catalog instructs the agent to enforce those rules manually.

One thing worth knowing: these symlinks/hooks live in the **canonical Brainer repo**. Sibling repos (screenery-lean, PROMPTER, etc.) each need their own `install.sh` run after the phase-2 merge propagates — that's the existing propagate-skill discipline, not something new.

Meanwhile: the `eval/skills_effectiveness` cleanup lane is running (scoped to only that directory so it can't interfere with the auditors), and both audits are in flight. I'll report as each completes.
```

## FIRE 12 (2026-07-20T07:13:01.459Z)

### assistant reply preceding the fire:
```
The repo archaeology came back with a definitive match — here's what it recovered while the web-research lane keeps running.

## The article and session, found

**The article**: "Skills could be making your AI worse" (campaign title "The Case Against Skills") by **Mike Taylor**, published by **Every** (every.to), pasted by you into a **Codex GPT-5.6 Sol session on 2026-07-16** with the prompt "what brainer skills are not helpful (anymore) or actually harmful for agents' performance? what is the best way to verify." The raw paste survives in `.brainer/sessions/raw/rollout-2026-07-16T20-39-33-….jsonl`.

Its core claims: frontier models (it names Fable 5, GPT-5.6, Opus 4.8) have already absorbed what most trending skills teach, so extra instructions "create confusion, not clarity" — you're "fighting the weights of the model." Keep skills only for private context, custom tools, personal taste, or company-specific workflow; retest ones compensating for model quirks (shelf life); retire anything that doesn't demonstrably improve results, proven by with/without A-B comparison and an LLM judge.

## What Brainer already did with it — this is the interesting part

That paste is the *origin story of the work we've been doing all along*. It triggered a full verification campaign, documented in [eval/FINDINGS.md](eval/FINDINGS.md), [docs/adversarial-review-harmful-skills-audits-2026-07-17.md](docs/adversarial-review-harmful-skills-audits-2026-07-17.md), and the whole `eval/skills_effectiveness/` apparatus. Its actual measured findings:

1. **The strong claim was NOT confirmed here.** A FRONTIER-vs-OFF pilot (19 task families × 2 arms × 2 hosts) was a ceilinged null — both arms 19/19, token overhead only ~1.2–1.7%. A later long-horizon probe went further: skills-on improved *neither* primary metric and produced extra defects in one arm → binding **DEMOTE verdict**.
2. **What WAS demonstrably harmful was over-instrumentation, not skill content**: the always-on canary auto-injection produced 250/400 false injections on a hard-negative corpus (a trigger-happy correction-ledger regex creating bogus closeout-blocking obligations). That's precisely the "repeated injected reminders distract a strong model" mechanism — and it's what the profile system, and now phase 2's contraction of it, fixed.
3. **One surprise in the other direction**: the verify-before-completion *probe* showed genuine signal (5/5 fresh verifications caught) — only its escalation wrapper was noise. So "skills hurt frontier models" isn't uniform; a cheap mechanical claim-checker earned its keep even at the frontier.
4. A skill-by-skill retire/demote taxonomy came out of that campaign — and a subsequent adversarial review correctly flagged it as *proposals resting on taxonomy, not causal proof*. The phase-1 contraction (retiring standing-orders, requirements-ledger, wayfinder, fable-mode, plan-first-execute, lean-execution, self-improvement-loops) and phase 2 (retiring the noisy canary machinery itself) are the enactment of exactly that article's doctrine, with the measurement discipline it demanded.

So the honest summary: **the current overhaul is already the response to that article** — and the repo's own data supports the article's *mechanism* claims (injection noise, unproven doctrine skills) while refuting its *blanket* claim (measured null, not measured harm, for the compact skills; one probe positively valuable).

Still pending: the web-research lane on recent external publications, which will let me check whether the outside evidence adds mechanisms Brainer hasn't tested (e.g. tool-catalog dilution, mid-turn interrupt costs) — I'll deliver the full synthesis mapping each current-catalog skill to its frontier-harm risk when it reports. The Kimi/Sol audits and the eval-harness cleanup lane are also still running.
```

## FIRE 13 (2026-07-20T07:17:30.053Z)

### assistant reply preceding the fire:
```
Phase 2d is committed (`78a4800`) — my own re-runs confirmed zero behavioral legacy/shadow references left, the 862-case frontier run byte-identical to baseline, `run_all_tests` at 103/103, and the two remaining harness test failures reproduce identically on main (they're fallout from phase 1's fable-mode retirement, not this change — queued as a known item). One process note: the builder ran `git stash` in the shared worktree despite an explicit ban — no damage this time (stash list empty, all commits intact), but that's the second confirmed violation of this rule by a builder, reinforcing that the ban has to be enforced by checking, not by briefing.

Now the synthesis you asked for — repo evidence plus fresh literature, mapped onto Brainer.

## Do skills hurt frontier models? What the evidence actually says

The external evidence (12 verified sources) converges on a nuanced answer: **not all scaffolding hurts, but three specific categories do, and frontier models are not exempt.** Ranked by evidence strength:

1. **Context dilution is real and universal** (controlled studies: Chroma's "context rot" across 18 frontier models; Microsoft's "tool-space interference" showing up to 85% degradation from large tool spaces; MCPGAUGE's ~20k-call study finding tool augmentation often net-negative). Every resident catalog line, tool schema, and reminder is measured distractor text. Frontier models degrade less, but they degrade.
2. **Coercive instructions calibrated for weaker models backfire on stronger ones** — this is *first-party Anthropic guidance*: their migration docs explicitly tell you to strip "CRITICAL/MUST/ALWAYS" scaffolding and forced-cadence instructions because newer models follow them too literally.
3. **Imposed workflows can cap a stronger model's own policy**: mini-swe-agent (100 lines, bash-only) matches elaborate harnesses at >74% on SWE-bench Verified; one 2026 benchmark had Opus 4.7 scoring *higher* in the minimal harness than in Claude Code on the same tasks; the first-party-harness advantage measurably shrinks as models get stronger.
4. **Mid-trajectory injected reminders** (the closest match to compliance-canary) have no controlled ablation yet, but multiple independent Claude Code field reports describe the same failure: reminder pollution causing an Opus-class model to lose facts it had itself derived mid-operation, plus 20–40k tokens/session of overhead.
5. The category the literature consistently **exempts**: scaffolding that supplies facts the model *cannot know* — project state, verified memory, indexes, custom tools.

## Mapped onto Brainer — and the uncomfortable/comfortable truth

Brainer already ran this experiment on itself (the campaign your pasted article triggered): FRONTIER-vs-OFF was a **null** (19/19 both arms, ~1.5% token overhead), the long-horizon probe found **no improvement and extra defects in one arm**, and the one demonstrably harmful thing was the **canary's false-injection rate** (250/400 on hard negatives before the profile fix). That aligns almost perfectly with the external mechanism ranking. Skill-by-skill on the current 24:

| Risk category | Skills | Assessment |
|---|---|---|
| Mid-turn injection (mechanism 4) | `compliance-canary` | The one *measured* harm source here. Phases 1–2 cut it to a 3-probe allowlist and deleted the pulse/escalation machinery. Residual risk is probe precision — notably, it fired at me twice *this session* on replies that were summarizing already-verified work, which is exactly the "false obligation" shape the campaign flagged. Worth a precision pass on live-session data. |
| Imposed workflow (mechanisms 2–3) | `think`, `team-lead`, `caveman-ultra`, `prompt-triage`, `loop-engineering`, `learn-skill`, `task-retrospective`, `verify-before-completion` | Highest theoretical risk for Fable-5/Sol-class — and already neutralized structurally: all are now slash-only/manual, costing ~1 catalog line each unless you invoke them. The literature says don't auto-fire these at frontier models; Brainer no longer does. |
| Resident context (mechanism 1) | the CLAUDE.md catalog block + code-craft directives | ~7.2KB resident, always paid. Phase 1 dieted it under budget, but this is the one *unavoidable* per-session tax, and the code-craft directives contain exactly the "never/always" phrasing Anthropic's migration guide warns over-triggers literal models. A rewrite toward positive-example phrasing is a cheap, evidence-backed follow-up. |
| Exempt (facts the model can't know) | `wiki-memory`, `context-keeper`, `baton`, `index-first`, `semantic-diff`, `impact-of-change`, `cache-lint`, `output-filter`, `write-gate`, `propagate`, `eval-gate`, `security-oversight`, `wiki-refresh`, `brainer-audit` | The category every source exempts — project state, memory, indexes, mechanical gates. These are Brainer's justified core. One caveat: even exempt tools pay mechanism-1 rent, so their catalog lines must stay terse. |

**The counter-finding worth keeping**: the v
```

## FIRE 14 (2026-07-20T07:17:36.746Z)

### assistant reply preceding the fire:
```
Phase 2d is committed (`78a4800`) — my own re-runs confirmed zero behavioral legacy/shadow references left, the 862-case frontier run byte-identical to baseline, `run_all_tests` at 103/103, and the two remaining harness test failures reproduce identically on main (they're fallout from phase 1's fable-mode retirement, not this change — queued as a known item). One process note: the builder ran `git stash` in the shared worktree despite an explicit ban — no damage this time (stash list empty, all commits intact), but that's the second confirmed violation of this rule by a builder, reinforcing that the ban has to be enforced by checking, not by briefing.

Now the synthesis you asked for — repo evidence plus fresh literature, mapped onto Brainer.

## Do skills hurt frontier models? What the evidence actually says

The external evidence (12 verified sources) converges on a nuanced answer: **not all scaffolding hurts, but three specific categories do, and frontier models are not exempt.** Ranked by evidence strength:

1. **Context dilution is real and universal** (controlled studies: Chroma's "context rot" across 18 frontier models; Microsoft's "tool-space interference" showing up to 85% degradation from large tool spaces; MCPGAUGE's ~20k-call study finding tool augmentation often net-negative). Every resident catalog line, tool schema, and reminder is measured distractor text. Frontier models degrade less, but they degrade.
2. **Coercive instructions calibrated for weaker models backfire on stronger ones** — this is *first-party Anthropic guidance*: their migration docs explicitly tell you to strip "CRITICAL/MUST/ALWAYS" scaffolding and forced-cadence instructions because newer models follow them too literally.
3. **Imposed workflows can cap a stronger model's own policy**: mini-swe-agent (100 lines, bash-only) matches elaborate harnesses at >74% on SWE-bench Verified; one 2026 benchmark had Opus 4.7 scoring *higher* in the minimal harness than in Claude Code on the same tasks; the first-party-harness advantage measurably shrinks as models get stronger.
4. **Mid-trajectory injected reminders** (the closest match to compliance-canary) have no controlled ablation yet, but multiple independent Claude Code field reports describe the same failure: reminder pollution causing an Opus-class model to lose facts it had itself derived mid-operation, plus 20–40k tokens/session of overhead.
5. The category the literature consistently **exempts**: scaffolding that supplies facts the model *cannot know* — project state, verified memory, indexes, custom tools.

## Mapped onto Brainer — and the uncomfortable/comfortable truth

Brainer already ran this experiment on itself (the campaign your pasted article triggered): FRONTIER-vs-OFF was a **null** (19/19 both arms, ~1.5% token overhead), the long-horizon probe found **no improvement and extra defects in one arm**, and the one demonstrably harmful thing was the **canary's false-injection rate** (250/400 on hard negatives before the profile fix). That aligns almost perfectly with the external mechanism ranking. Skill-by-skill on the current 24:

| Risk category | Skills | Assessment |
|---|---|---|
| Mid-turn injection (mechanism 4) | `compliance-canary` | The one *measured* harm source here. Phases 1–2 cut it to a 3-probe allowlist and deleted the pulse/escalation machinery. Residual risk is probe precision — notably, it fired at me twice *this session* on replies that were summarizing already-verified work, which is exactly the "false obligation" shape the campaign flagged. Worth a precision pass on live-session data. |
| Imposed workflow (mechanisms 2–3) | `think`, `team-lead`, `caveman-ultra`, `prompt-triage`, `loop-engineering`, `learn-skill`, `task-retrospective`, `verify-before-completion` | Highest theoretical risk for Fable-5/Sol-class — and already neutralized structurally: all are now slash-only/manual, costing ~1 catalog line each unless you invoke them. The literature says don't auto-fire these at frontier models; Brainer no longer does. |
| Resident context (mechanism 1) | the CLAUDE.md catalog block + code-craft directives | ~7.2KB resident, always paid. Phase 1 dieted it under budget, but this is the one *unavoidable* per-session tax, and the code-craft directives contain exactly the "never/always" phrasing Anthropic's migration guide warns over-triggers literal models. A rewrite toward positive-example phrasing is a cheap, evidence-backed follow-up. |
| Exempt (facts the model can't know) | `wiki-memory`, `context-keeper`, `baton`, `index-first`, `semantic-diff`, `impact-of-change`, `cache-lint`, `output-filter`, `write-gate`, `propagate`, `eval-gate`, `security-oversight`, `wiki-refresh`, `brainer-audit` | The category every source exempts — project state, memory, indexes, mechanical gates. These are Brainer's justified core. One caveat: even exempt tools pay mechanism-1 rent, so their catalog lines must stay terse. |

**The counter-finding worth keeping**: the v
```

