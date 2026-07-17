# Adversarial review: Codex “Audit harmful Brainer skills”

**Date:** 2026-07-17  
**Reviewer session:** Cursor (parent model served as Grok 4.5; cheap subagents for digs)  
**Target:** Codex sessions *Audit harmful Brainer skills* / *(2)*  
**Branch under review:** `codex/skills-effectiveness-verification` @ `a767d72`  
**Success criterion:** top 3 things that can be done better or fixed

---

## Executive verdict

The Codex work **did not prove Brainer skills are harmful** in the preregistered sense (≥5pp task-success regression or attributable safety/scope violation).

What it *did* establish well:

- Legacy compliance-canary auto-injection is noisy/harmful on a frozen trigger corpus (**250/400** hard-negative FPs).
- The lean **`frontier`** profile clears that gate (**TP 50 / FP 0 / FN 0**).
- A focused **FRONTIER vs OFF** pilot (76 valid outcomes) is a **ceilinged null** — no pass lift; do **not** expand the 8,300-run matrix.
- Generic process skills should not auto-compose by default until proven.

What overreached:

- Quarantine / **retire** / **demote** / `delete_by_default` for 14 bodies rests mainly on **content taxonomy + observational sibling reminder counts**, not causal outcome proof.
- Repo defaults were rolled back (hooks pruned, catalog demoted) as if “unproven/generic” ≈ “harmful.”
- Docs and wiring still disagree on several measured-positive skills.

**Merge status:** quarantine + pilot commits (`499bd9e`, `48871db`) are **not on `main`**. Deep-review harden `55f9535` **is** on `main`.

---

## Top 3 fixes

### 1. Separate “quiet the noisy defaults” from “retire/demote 14 skills”

**Keep / ship:** frontier canary default; strip bare-`again` / correction-ledger false obligations; freeze the paid matrix.

**Do not treat as decided:** retire / demote-role-brief / 30-day `delete_by_default` for the 14 prompt bodies. Relabel those as **manual/unproven** until the harmful gate fires or a named per-skill disable trial completes. Codex itself admitted: *“We have not proven those 14 skills are useless individually.”*

### 2. Resolve measured-positive contradictions before merge

| Skill / mechanism | Still claimed in `eval/FINDINGS.md` | What `499bd9e` did |
|---|---|---|
| `prompt-triage` | **−20.9%** tokens; historically “keep auto-wired” | Hook removed; classified **retire**; `auto-install: false` |
| `verify-before-completion` | Judge delta **+0.04–+0.92** | FULL body → experimental/manual; compact canary probe kept |
| `learn-skill`, `loop-engineering` | Classified **retain-manual** (tooling) | Also flipped `auto-install: false`; learn-skill hooks removed |

**Fix:** either re-measure OFF vs ON under current hosts and keep/retire with evidence, or rewrite FINDINGS/install guidance so docs match wiring. Restore **retain-manual** hook/tool wiring separately from prose quarantine.

### 3. Finish enforcement + kill doc/artifact drift (and stop treating giant eval dumps as the product)

Half-finished surface:

- No expiry/deletion job despite `expiry_days: 30` + `delete_by_default: true`
- No skill bodies deleted (quarantine is invocation policy only — fine, but then don’t advertise delete)
- Stale: `FINDINGS.md` default-path advice, `README` canary description, `HOOKS_MAP.md` still listing prompt-triage, skill-count inconsistency (30 vs 21 vs 24)
- Focused v2 `campaign-summary.json` says `completed:0` / `skipped:76` while analysis says **76/76 completed**
- Profile suite reported as 20/20 in places; measured **19**
- ~**15.5k** lines of committed JSON/JSONL dominate the branch for a futility/null result

**Fix:** one reconcile pass (docs ↔ hooks ↔ quarantine JSON), fix the summary artifact, and avoid committing bulk result corpora unless CI needs them (LFS or regenerate).

---

## What Codex concluded (fair summary)

**User ask:** which Brainer skills are unhelpful/harmful, and how to verify (skills-may-make-AI-worse framing).

**Core narrative:** Brainer was over-instructing / over-instrumenting via broad automatic composition of generic process skills.

**Demonstrable harm (supported):** legacy canary injection path — especially bare `again` in task-retrospective correction regex → correction ledger → bogus closeout-blocking memory obligation; **250/400** false injections on the frozen negative set.

**Policy they adopted:** keep specialized knowledge + executable tools + compact safety mechanisms; assume generic reasoning instructions unnecessary until proven.

**Pilot:** 19 cases × 2 arms × 2 hosts = 76; both arms 19/19; median token overhead ~+1.2% Codex / ~+1.7% Claude; expansion gate failed; ceiling effect admitted.

**14-body classification (taxonomy, not outcome proof):**

| Disposition | Skills |
|---|---|
| **retire** | `caveman-ultra`, `prompt-triage`, `requirements-ledger`, `standing-orders` |
| **demote → role briefs** | `fable-mode`, `lean-execution`, `plan-first-execute`, `team-lead`, `think` |
| **retain-manual** | `learn-skill`, `loop-engineering`, `task-retrospective`, `wayfinder` |
| **split** | `verify-before-completion` (keep compact probe + mechanical verifier) |

**Commits claimed / present on branch:** `499bd9e` (quarantine + frontier canary + harness), `48871db` (focused pilot), `a767d72` (wiki sibling registration). Session 2 is a fork of session 1.

---

## What the repo actually changed

### Behavior (important)

- Default canary profile → **`frontier`** (quiet: compact verify + pending-intent; legacy probes off unless profiled)
- Many skills → `auto-install: false` and/or `disable-model-invocation: true`; catalog marked Experimental/manual
- Removed default hooks: Codex `prompt-triage` + `learn-skill`; Gemini also lost `index-first` BeforeTool in-repo
- `install.sh` + `prune_optin_hooks.py`: reinstall **convergently strips** managed hooks for opt-in skills; caveman SessionStart pruned from **`$HOME/.claude/settings.json`** on install
- Builder / verifier / research-lite agent briefs absorbed compact plan/verify/stop rules

### Not changed

- Skill **bodies not deleted**
- Longitudinal hooks (canary-over-time, compaction handoff, wiki trust) **not** outcome-evaluated by the focused pilot
- Branch **not** pushed/merged to `main` (as of this review)

---

## Side notes from this review session

### Kimi K3 (inside the Codex campaign) — mixed

- **Our end:** invalid `temperature: 0.1` (K3 allows only `1`); client read timeouts; later “credentials no longer present”
- **Provider:** `429 engine_overloaded_error`, no fallback
- One real Kimi adversarial pass did land and is credited for blocking the paid matrix (hook-timing / differential-exclusion / secret-egress)

### Fable 5

- **Not** the model that drove the Codex audits (`gpt-5.6-sol`)
- In *this* Cursor review session, the parent agent was served as **Grok 4.5** despite a Fable-5-economical brief; meaningful synthesis was Grok + cheap subagents, not Fable

### Review tooling gaps

- `pi_agents` / Kimi K3 was **not** available as an MCP in this Cursor environment
- One medium critique subagent hit an API limit and fell back to Grok

---

## Recommended next actions (ordered)

1. Before any merge: fix FINDINGS/README/HOOKS_MAP/campaign-summary inconsistencies; drop or soften `delete_by_default`.
2. Keep frontier canary + freeze matrix; treat 14-body retire/demote as **proposals**, not shipped policy.
3. Restore retain-manual tooling hooks (`learn-skill` / `loop-engineering`) unless a disable trial says otherwise.
4. Decide prompt-triage with a fresh paired measurement or an explicit “measurement retired because …” note.
5. Soften install global prune messaging / sibling impact before running `./install.sh` on consumers.

---

## Key evidence paths

- `docs/SKILLS_EFFECTIVENESS_VERIFICATION.md`
- `eval/FINDINGS.md` (2026-07-16 campaign section)
- `eval/skills_effectiveness/quarantine_classification.json`
- `eval/results/skills-effectiveness/quarantine-classification.md`
- `eval/results/skills-effectiveness/focused-pilot-v2-analysis.md`
- `eval/results/skills-effectiveness/*-trigger-500.metrics.json`
- Commits: `499bd9e`, `48871db`, `a767d72` on `codex/skills-effectiveness-verification`
- Codex rollouts: `019f6e28-…` / forked `019f6ef6-…`
