---
name: propagate
description: "Use when the user asks to propagate, sync, roll out, or push Brainer skill changes to the sibling/consumer repos (screenery-lean, product images repo, farey-hecke, PROMPTER, …) after work in the canonical Brainer repo. Runs the classify → apply → reinstall → verify → post-check sequence per sibling, one repo at a time; never blind-copies; CUSTOMIZED files are flagged for manual merge, never overwritten."
effort: low
tools: [Bash, Read]
auto-install: true
pulse_reminder: propagation is per-sibling and sequential — classify first, fast-forward only STALE, never overwrite CUSTOMIZED, re-run the sibling's install.sh, verify with --repo, then --post-check. Canonical must be committed BEFORE apply.
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
python3 scripts/sibling_sync_audit.py --repo "$R" --classify        # 1. read-only: STALE vs CUSTOMIZED + NEW-SKILL list
python3 scripts/sibling_sync_audit.py --repo "$R" --apply-stale --apply-absent --adopt-new-skills   # 2. fast-forward + adopt new skills
( cd "/Users/za/Documents/$R" && bash install.sh )                  # 3. rewire that host's carriers/hooks
python3 scripts/sibling_sync_audit.py --repo "$R" --classify        # 4. verify: differs ≈ CUSTOMIZED only, new-sk 0
python3 scripts/sibling_sync_audit.py --repo "$R" --post-check      # 5. mechanical target-repo test
```

**New skills adopt by default.** `--adopt-new-skills` copies every canonical
skill a sibling wholly lacks — so a skill you just created in Brainer reaches
every sibling on the next propagation with **no per-skill opt-in**. A sibling
that genuinely doesn't want a skill declines *explicitly* by listing its name in
that sibling's root `.brainer-sync-optout` (one per line); declining is the
deliberate act, adoption is the default. Always run step 2 with all three apply
flags — omitting `--adopt-new-skills` is what used to silently strand new skills.

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

`repo · applied N stale · added M absent · left K customized (list) ·
install.sh ok/fail · verify counts · post-check result · adjacent tests run +
outcome`. A propagation without step 4-6 evidence is not done.
