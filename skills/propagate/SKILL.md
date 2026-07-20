---
name: propagate
description: "Use when the user asks to propagate, sync, roll out, or push Brainer skill changes to the sibling/consumer repos (screenery-lean, product images repo, farey-hecke, PROMPTER, …) after work in the canonical Brainer repo, or asks to harvest lessons, reap lessons, or bring learnings back from a sibling. Runs the classify → apply → reinstall → verify → post-check sequence per sibling, one repo at a time; never blind-copies; CUSTOMIZED files are flagged for manual merge, never overwritten."
effort: low
tools: [Bash, Read]
auto-install: true
pulse_reminder: propagation is per-sibling and sequential — classify first, fast-forward only STALE, never overwrite CUSTOMIZED, adopt new skills AND agent-defs (--adopt-agents, else team-lead's roster ships inert), re-run the sibling's install.sh, refresh its resident docs with canonical install.sh --catalog-only, verify with --repo, then --post-check. Canonical must be committed BEFORE apply. A run that only pushes and skips the harvest (reverse) lane is INCOMPLETE unless you state why.
---

# propagate — push canonical skill changes to the sibling repos

Brainer is the canonical source; siblings vendor **forked copies** (they
customize legitimately). Propagation is therefore classify-then-apply, never
copy-everything. Full topology + landmines:
`wiki/concepts/brainer-multi-repo-topology.md` (in the canonical Brainer
checkout — deliberately not a link: consumer repos don't vendor `wiki/`).

## Approved repository boundary (hard)

The authoritative list lives in `scripts/sibling_sync_audit.py` (`APPROVED_SIBLINGS`) —
canonical is `Brainer`, consumers currently include `PROMPTER`, `screenery-lean`, and
similar forked checkouts; check that constant for the exact, current set rather than
trusting this doc to stay in sync.

Do not discover or propagate to other adjacent repositories merely because they
contain `skills/` and `install.sh`. An additional target requires the user to
name it for the current task; then pass `--allow-unapproved` together with its
explicit `--repo`. The no-argument audit lists only the approved consumers.

## Preconditions (hard)

1. **Canonical is committed.** `--apply-stale` copies the canonical *working
   tree*, but the classifier judges siblings against canonical *git history* —
   propagating uncommitted edits brands the sibling CUSTOMIZED forever after.
   `git status --short` must be clean for `skills/` before any apply.
2. Run every command from the Brainer repo root.
3. **One sibling at a time, never in parallel** — each sibling's `install.sh`
   writes user-global settings. Its installer may intentionally differ; step 3b
   uses canonical Brainer only for the generated resident-doc block.

## Per-sibling sequence

```bash
R="<sibling dir name>"   # e.g. screenery-lean · "product images repo" · farey-hecke · PROMPTER
python3 scripts/sibling_sync_audit.py --repo "$R" --classify        # 1. read-only: STALE vs CUSTOMIZED + NEW-SKILL/NEW-AGENT list
python3 scripts/sibling_sync_audit.py --repo "$R" --apply-stale --apply-absent --adopt-new-skills --adopt-agents   # 2. fast-forward + adopt new skills + roster
( cd "/Users/za/Documents/$R" && bash install.sh )                  # 3. rewire that host's carriers/hooks
SKILLS_DIR="../$R/skills" bash install.sh --project "/Users/za/Documents/$R" --catalog-only  # 3b. compile resident docs with canonical carrier logic
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

## Harvest (reverse) lane

Propagation is not one-directional. Each sibling accumulates its own lessons
(bugs it hit, gotchas it worked around) that Brainer never sees unless
someone reads them back. Per sibling repo:

1. **Scan for lesson artifacts, then pre-scan for already-harvested IDs.**
   Three artifact shapes:
   - `docs/*brainer*learn*` failure-report files
   - `.brainer/` lesson/baton notes
   - wiki pages tagged `for-brainer`

   Each artifact may hold multiple lesson blocks (one artifact ≠ one lesson),
   so identify lessons at the **block** level. **Block boundaries:** a lesson
   block runs from its markdown heading (or the artifact's first line, when
   headerless) to the next same-or-higher-level heading or end of file;
   fenced code inside stays part of the block. **Per-lesson ID:** when the
   block has a stable section heading, the ID is `<source file> + <section
   heading>`; otherwise the ID is a content hash — trim leading/trailing
   whitespace from the lesson block, normalize all line endings to `\n`, take
   the sha256 of the result, and truncate to the first 12 hex chars.
   **Marker hygiene:** a `harvested:` line only counts if it appears OUTSIDE
   a code fence and matches the exact grammar `harvested: <ISO-date> <sha>
   <lesson-id>` (any other shape — inside a fence, missing a field, extra
   trailing text — is not a valid marker and is ignored). Parse every valid
   `harvested:` line in the artifact into a consumed-ID set **before** doing
   anything else. If more than one marker line names the same lesson-id and
   they disagree (different sha and/or date), the strictest reading wins:
   treat that lesson-id as **NOT** harvested, re-run step 4's verification
   for it, and on success rewrite the artifact to hold a single clean marker
   for that ID (replacing the conflicting lines). Skip any lesson block
   whose ID is already in the (deduplicated, non-conflicting) consumed set —
   this is what makes a re-run over the same artifact a no-op instead of a
   double-harvest. A lesson block appended to an artifact **after** it was
   marked gets a fresh ID (new heading/new hash) and is **not** in the
   consumed set, so it IS harvested on this pass — append-only artifacts
   never get stuck at "fully marked, nothing more to see."
2. **SCOPE-classify each unconsumed lesson** per
   [LEARNING_CONTRACT §1](../_shared/LEARNING_CONTRACT.md#1-scope-classification-is-mandatory-at-banking-time)
   — `this-skill` / `this-repo` / `cross-skill` / `cross-repo` / `canon`. A
   this-repo-only lesson stays in that sibling; nothing to harvest.
3. **Land cross-repo/canon lessons in Brainer**: canon doc or skill, plus an
   executable check per
   [LEARNING_CONTRACT §3](../_shared/LEARNING_CONTRACT.md#3-mechanism-over-prose)
   (mechanism over prose — never prose-only). Record the repo-relative
   `<landed-path>` (canon doc / skill file / test) per landed lesson — step 4
   greps exactly that file.
4. **Verify before marking, then mark per lesson, not per file.** `git show
   <sha>:<path>` only proves a *snapshot* once contained the rule — it says
   nothing about whether that rule survived. Verify **survival at current
   Brainer HEAD** instead: run `git show HEAD:<landed-path>` and grep it for
   the rule text (or rule ID) from step 3. A lesson that landed and was
   later reverted (present in the old sha's snapshot, absent from HEAD) MUST
   fail this check, remain unmarked, and be re-harvested next pass — the sha
   in the marker records *when* it landed, never *whether it still holds*.
   Only after HEAD confirms survival, append one `harvested: <ISO date>
   <brainer commit sha> <lesson-id>` line per harvested lesson (not one
   blanket line per artifact), placed outside any code fence and matching
   the grammar in step 1 exactly — this is what lets a partially-harvested
   artifact (some blocks consumed, one still this-repo-only, one newly
   appended) be marked correctly without falsely covering lessons it didn't
   land.

## Failure modes

Premortem ([`LEARNING_CONTRACT`](../_shared/LEARNING_CONTRACT.md) §8):

- **Silent-failure path** — a builder edits Brainer canonical `skills/` but never runs this
  skill; nothing forces propagation, so siblings quietly diverge from canonical with no
  error anywhere until someone happens to diff them. Even when run, `install.sh` failing
  inside a sibling (step 3) can leave that sibling's carriers half-rewired while the
  classifier (step 4) still reports counts, unless its exit code is actually checked.
- **Rot-when-unwatched** — `.brainer-sync-optout` entries accumulate and are never revisited:
  a sibling opts out of a skill for a reason that stopped applying months ago, and nothing
  re-prompts "does this opt-out still make sense" — the classifier just keeps treating that
  skill as deliberately absent forever.
- **No-hooks host** — propagation is a manually-invoked CLI sequence (`sibling_sync_audit.py`
  + each sibling's `install.sh`), not a hook, so it behaves identically on Codex/Gemini per
  `docs/HOST_CAPABILITY_MATRIX.md`; the real exposure is that nothing on ANY host schedules
  or reminds a builder to propagate — it fires only when a human/agent remembers to invoke
  `/propagate` or this skill's trigger phrase.

## Report (per sibling)

`repo · applied N stale · added M absent · adopted S skills + A agent-defs ·
left K customized (list) · install.sh ok/fail · verify counts (incl. ag-new 0) ·
post-check result · adjacent tests run + outcome`. A propagation without step 4-6
evidence is not done.

**Harvest fields (per sibling):** `artifacts scanned N · lessons found L
(skipped already-harvested X) · SCOPE breakdown
(this-skill/this-repo/cross-skill/cross-repo/canon counts) · landed-where +
commit sha (verified via git show) · newly-marked-consumed count`, or
`skipped: <reason>` if the harvest lane did not run.
