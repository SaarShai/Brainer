---
name: propagate
description: "Use when the user asks to propagate, sync, roll out, or push Brainer skill changes to the sibling/consumer repos (screenery-lean, product images repo, farey-hecke, PROMPTER, …) after work in the canonical Brainer repo. Runs the classify → apply → reinstall → verify → post-check sequence per sibling, one repo at a time; never blind-copies; CUSTOMIZED files are flagged for manual merge, never overwritten."
effort: low
tools: [Bash, Read]
auto-install: true
pulse_reminder: propagation is per-sibling and sequential — classify first, fast-forward only STALE, never overwrite CUSTOMIZED, adopt new skills AND agent-defs (--adopt-agents, else team-lead's roster ships inert), re-run the sibling's install.sh, verify with --repo, then --post-check. Canonical must be committed BEFORE apply.
---

# propagate — push canonical skill changes to the sibling repos

Brainer is the canonical source; siblings vendor **forked copies** (they
customize legitimately). Propagation is therefore classify-then-apply, never
copy-everything. Full topology + landmines:
[`wiki/concepts/brainer-multi-repo-topology.md`](../../wiki/concepts/brainer-multi-repo-topology.md).

## Preconditions (hard)

1. **Canonical is committed.** `--apply-stale` copies the canonical *working
   tree*, but the classifier judges siblings against canonical *git history* —
   propagating uncommitted edits brands the sibling CUSTOMIZED forever after.
   `git status --short` must be clean for `skills/` before any apply.
2. Run every command from the Brainer repo root.
3. **One sibling at a time, never in parallel** — each sibling's `install.sh`
   writes user-global settings.

## Per-sibling sequence

```bash
R="<sibling dir name>"   # e.g. screenery-lean · "product images repo" · farey-hecke · PROMPTER
python3 scripts/sibling_sync_audit.py --repo "$R" --classify        # 1. read-only: STALE vs CUSTOMIZED + NEW-SKILL/NEW-AGENT list
python3 scripts/sibling_sync_audit.py --repo "$R" --apply-stale --apply-absent --adopt-new-skills --adopt-agents   # 2. fast-forward + adopt new skills + roster
( cd "/Users/za/Documents/$R" && bash install.sh )                  # 3. rewire that host's carriers/hooks
python3 scripts/sibling_sync_audit.py --repo "$R" --classify        # 4. verify: differs ≈ CUSTOMIZED only, new-sk/ag-new 0
python3 scripts/sibling_sync_audit.py --repo "$R" --post-check      # 5. mechanical target-repo test
```

**New skills adopt by default.** `--adopt-new-skills` copies every canonical
skill a sibling wholly lacks — so a skill you just created in Brainer reaches
every sibling on the next propagation with **no per-skill opt-in**. A sibling
that genuinely doesn't want a skill declines *explicitly* by listing its name in
that sibling's root `.brainer-sync-optout` (one per line); declining is the
deliberate act, adoption is the default. Always run step 2 with all **four**
apply flags — omitting `--adopt-new-skills` is what used to silently strand new
skills; omitting `--adopt-agents` is what used to strand team-lead's roster.

**Agent-defs travel too (`--adopt-agents`).** `.claude/agents/*.md` — team-lead's
`builder`/`verifier` lanes + the labor-tier roster — are tracked canonical SOURCE
(`.gitignore` carves `!.claude/agents/`), and they were the recurring silent gap:
propagation synced `skills/` but never the roster, so team-lead's lanes shipped
**inert** to siblings until someone hand-copied the defs. They now ride the same
classifier — a **STALE** roster def (older `builder.md` byte-matching a historical
canonical version) fast-forwards under `--apply-stale`; a **CUSTOMIZED** one is
protected; a **missing** one adopts by default under `--adopt-agents`. A sibling
declines a specific def with an `agent:<name>` line in `.brainer-sync-optout`
(same file as skill opt-outs). Because agent defs live **directly** in the host
loader path (`.claude/agents/`), a copied def is live immediately — no
`install.sh` symlink step (step 3 still runs for the skills side). The summary
table's `ag-id`/`ag-df`/`ag-new` columns make a non-zero roster gap visible on
every audit; `AGENT-ONLY` marks sibling-local roster defs that are never touched.

**Two carriers — know which owns what.** `builder`/`verifier` are ORPHANS (no
skill bundles them), so this sync is their **only** carrier and its CUSTOMIZED
protection is the only thing guarding a sibling's local edit. The other six
(`wiki-note`,`quick-fix`,`local-ollama`,`research-lite`,`kaggle-feeder`,
`glm-executor`) are ALSO bundled under `skills/prompt-triage/tools/agents/` and
`cp -f`'d into `.claude/agents/` by prompt-triage's installer at **step 3** —
which runs last and is authoritative for them (it overwrites unconditionally, so
for those six an `agent:` opt-out / CUSTOMIZED verdict is informational only).
Canonical keeps both copies byte-identical, so the two carriers never fight; if
they ever diverge, fix the `skills/prompt-triage/tools/agents/` source.

6. **Judgment test (per repo):** for any propagated `tools/*.py` that has an
   adjacent vendored test (`test_*.py` / `test.sh`), run it **in the sibling**
   (`cd` there first) and quote the result. At minimum, if hook files were
   propagated, run the sibling's `skills/compliance-canary/tools/test.sh`.

## What the classifier verdicts mean

- **STALE** — byte-matches a historical canonical version: the sibling simply
  never received later fixes. Safe to fast-forward; `--apply-stale` does it.
- **CUSTOMIZED** — holds ≥1 line that appears in **no** canonical version ever
  (line-level provenance, not whole-file hash — so a file that merely mixes
  old+new canonical sections is correctly STALE, not falsely CUSTOMIZED). The
  offending local lines are printed under the verdict. **Never overwritten.**
  Handle manually: fast-forward the file to canonical HEAD, then re-apply just
  those local lines on top, and ask whether the local change should be
  upstreamed into canonical. (`skills/HOOKS_MAP.md` is generated per-repo —
  permanently CUSTOMIZED, always leave it.)
- **absent** — `--apply-absent` adds missing files only inside skills the
  sibling already adopted; a wholly-absent skill dir is deliberate
  non-adoption — left alone.

## Never

- blind-rsync `skills/` across siblings (the hard rule this skill mechanizes)
- run sibling installs in parallel
- propagate uncommitted canonical state
- touch sibling-only skills
- commit inside a sibling repo — leave changes uncommitted for that repo's
  owner/session to review

## Report (per sibling)

`repo · applied N stale · added M absent · adopted S skills + A agent-defs ·
left K customized (list) · install.sh ok/fail · verify counts (incl. ag-new 0) ·
post-check result · adjacent tests run + outcome`. A propagation without step 4-6
evidence is not done.
