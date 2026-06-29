---
name: wiki-memory
description: "Repo-local markdown wiki with progressive retrieval (search → timeline → fetch) and gated writes (verified facts only). Use when the task references past work, decisions, memory, \"have we done X\", project facts, or when you need to record a durable finding. Tiered: L0 rules · L1 pointer index · L2 facts · L3 SOPs · L4 archive. Replaces note-app sprawl; no global agent config."
effort: low
tools: [Bash, Read, Write, Glob, Grep]
---

# wiki-memory

Long-term repo-local memory. One skill, two modes: **retrieve** (read) and **write** (gated).

## First-time bootstrap (per project)

If `wiki/` doesn't exist in the project root, run once:

```bash
python3 skills/wiki-memory/tools/wiki.py init
```

Creates the `wiki/` tree (`L0_rules.md`, `L1_index.md`, `schema.md`, `L2_facts/`, `L3_sops/`, `L4_archive/`, `raw/`, `concepts/`, `patterns/`, `projects/`, `people/`, `queries/`, `templates/`) seeded from the skill's bundled defaults. Idempotent — re-running after content lands is safe and writes nothing. Default target is `./wiki` in cwd; override with `--root <path>` or `WIKI_ROOT=<path>`.

**Degraded-write detection (cbm `dump_verify.h` lineage):** after `index` (and any write that re-indexes), the result carries `status` + `persisted`. The index re-counts rows actually written to the `docs` table vs the expected page count; if `persisted < ratio × expected` it reports `status: "degraded"` instead of a silent ok — surfacing a write that only half-landed. Pages-only; a floor skips tiny stores (default 5 — below it `status` stays `ok`). Tunable: `WIKI_DEGRADED_RATIO` (default `0.5`), `WIKI_DEGRADED_FLOOR` (default `5`). On `status: "degraded"`, re-run `index` and investigate before trusting retrieval.

**Ingest decisions / ADRs (cbm `manage_adr` lineage):**

```bash
python3 skills/wiki-memory/tools/wiki.py ingest-decisions [--repo-root <path>]
```

Scans the repo (`--repo-root`, default the wiki root's parent) for `DECISIONS.md`, `DECISIONS/*.md`, and `docs/adr/*.md`, and creates one `type: decision` page per source via the normal `new`/decision-template path. The source's H1 is the page title and the dedup key, so a re-run skips already-ingested decisions rather than duplicating them. The full ADR body (Status / Context / Decision / Consequences) is preserved with a source-provenance line.

## Compile-ingest (external sources)

Karpathy's core primitive: when the user brings an **external** source (paper, repo,
doc, article), don't just store it — *compile* it into the wiki so synthesis is paid
once and the wiki compounds. `wiki.py ingest <path|url>` deposits the source into
`raw/` (immutable) + logs it — **that is step 1 only**. The compile pass is an AGENT
procedure (code can't summarize), gated so an autonomous agent can't calcify
*unverified* syntheses into durable facts:

1. **Deposit** — `ingest <path|url>` → `raw/YYYY-MM-DD-slug.md`. One source at a time
   (a batch import is a dump, not a wiki).
2. **Extract** candidate concept/claim pages from the source (summarize; one
   technique/claim per page).
3. **Gate admission per candidate** — `python3 skills/wiki-memory/tools/wiki.py quorum
   --title "<t>" --sources <N> [--verified] [--user-confirmed] [--tags a,b] [--body-file <draft>]`:
   - **`autofile`** (≥2 *independent* sources, OR `--verified` against code/test, OR
     `--user-confirmed`) → create at the returned trust tier, add ≥2 backlinks,
     propagate to related pages.
   - **`quarantine`** (single unverified source) → create as an **`asserted` draft** and
     **surface it to the user** for confirmation; do NOT promote to a durable fact.
     Why: [`write-gate`](../write-gate/SKILL.md) scores *form, not truth* — a lone
     well-formed synthesis is exactly the poison it misses, so a second source / a
     verify step / a human is the only thing that earns `corroborated+`. (Karpathy's
     compile is safe because a human reviews lint output; `quorum` is the autonomous
     substitute for that reviewer.)
   - **`update-existing`** (overlap `high`) → update the same-subject page, don't create
     a near-duplicate.
4. **Reconcile** — after the batch run `contradict-scan`; if a new page supersedes/
   contradicts an old one, wire `supersedes`/`superseded-by` (+ `contradicts:`) then run
   `stale-citers` (see *Aging & reconcile*) so citers of the old page get repointed.
5. **Index + log** — `index`; the `new` path appends `log.md` for you.

Every page created still passes the write-gate why-clause + `overlap` dedup. This is a
generator→verifier pipeline (generator = candidate extraction; SEPARATE verifier =
`quorum` + write-gate + `contradict-scan`); model it with [`loop-engineering`](../loop-engineering/SKILL.md)
as a budget=1-per-source loop.

## Retrieve

Use when the task references past work, decisions, docs, memory, project facts, or "have we done X".

**Wiki-first:** when in doubt about any fact, rule, or decision, prefer reading the wiki over scrolling back through conversation history. The wiki is persistent and indexed; the context window is ephemeral and lossy (compaction silently drops detail). Retrieve before re-deriving.

1. Read `wiki/L1_index.md` first — it catalogs `concepts/` + `patterns/` +
   `projects/` + `queries/`, so it shows the knowledge that exists, not just
   project pages.
2. Run `python skills/wiki-memory/tools/wiki.py search "<query>"`.
3. For relevant hits, `python ... timeline "<id>"`. Timeline returns the page's
   **link graph**: `backlinks` (pages that cite this one), `outbound` (pages this
   one points to), and `neighbors` (same-dir). This graph *is* the retrieval
   index — read it, don't ignore it.
4. Fetch ≤3 pages first with `python ... fetch "<id>"`.
5. If insufficient, **follow the link graph before re-searching**: pick the next
   ≤2 pages from the prior page's edges (a typed edge to a related page beats a
   fresh keyword guess). Which edge: **`outbound`** = what this page depends on /
   points to (follow to go *deeper*); **`backlinks`** = what builds on or cites
   this (follow to go *broader*); **`neighbors`** = same-folder siblings (fallback
   when the typed edges miss). Judge by topical relevance to the task. Broaden to a
   new `search` only when the graph runs dry.
6. Cite page paths/IDs in your response.

**Compounding queries (file substantive answers back).** A query that produced a
*substantive synthesis* — a comparison, analysis, or decision spanning ≥2 pages, not a
trivial lookup — is itself new knowledge. File it back as a `queries/` page through the
normal gated write path (`overlap` → [`write-gate`](../write-gate/SKILL.md) → `new
--template decision` lands in `queries/`), citing the pages it synthesized, stamped
`trust: asserted` (promote on reuse via `consolidate`). This is the paper's "exploration
compounds" — the answer becomes durable so the next session recalls it instead of
re-deriving. Skip one-off / ephemeral lookups (the write **Fire condition** below still
governs).

**Loud query errors (cbm cypher.c lineage):** `search` distinguishes an *unsupported/malformed* query (empty · whitespace · punctuation-only · all-stopwords — nothing searchable) from a *valid* query that simply matched nothing. The former returns `{"error": "unsupported query: <reason>"}` and exits non-zero (`2`); the latter returns a normal empty `[]` (exit 0). Don't read an `error` payload as "no matches" — reword the query.

Never:
- load the whole wiki
- speculatively fetch raw/ archives
- cite a superseded page without noting the newer one

## Loop Mode

Use this mode when [`loop-engineering`](../loop-engineering/SKILL.md) names a loop memory contract. The rhythm is **recall before pass, write after pass**:

1. **Recall before each pass:** read the loop's `state_store`, then run `wiki.py search "<loop topic>"`, inspect relevant timelines, and fetch only the pages needed to re-anchor the pass. Treat `anchor_files` and the loop state as required inputs, not optional context.
2. **Write after each pass:** record attempts tried, verifier verdict, failures, state revision, and next action in the loop state file or board. Do not write every pass log into the wiki.
3. **Promote only durable lessons:** if a pass produced a verified, project-specific lesson that future sessions should recall, use the normal write path below: search/overlap first, gate with `write-gate`, update or create one narrow page, read it back, and append `wiki/log.md`.
4. **Update facts in place:** prefer updating/superseding the existing same-subject page over appending a fresh near-duplicate. Use `overlap` and `resolve` when a new pass changes an old fact.

Brainer's default memory backend is this repo-local wiki plus explicit loop state on disk. External semantic stores can be explored later behind an adapter only after they beat this contract on a Brainer task benchmark; do not add a vendor dependency just because a loop needs memory.

## Write

**Triggers:** write only when there is an explicit persistence request, an armed [`task-retrospective`](../task-retrospective/SKILL.md) run has selected a durable project lesson, a loop contract calls for durable lesson promotion, or the user-confirmed task outcome genuinely requires a repo-local memory update.

Potential sources:
- **failure / bug / issue** — a non-trivial failure, wrong approach, or bug. Record what went wrong + the exact prevention rule (error/lesson page; decay-protected).
- **feedback / correction** — when persistence is explicitly requested or task-retrospective is armed, record the corrected rule and *why* the original was wrong.
- **successful execution** — a non-trivial task solved with a reusable procedure. Distill the playbook only when it will recur and belongs in this project.
- also: verified finding · user-confirmed decision · source ingested.

**No automatic task-boundary harvest:** do not run the write protocol merely because an ordinary task ended, a correction arrived, or work succeeded. If task-retrospective was armed, let it decide relevance and target. If it was not armed, fix the issue and optionally suggest task audit mode when the lesson is clearly repeatable; do not launch a full retrospective or memory write by default.

**Fire condition (one-line test):** write **iff** the candidate is a *durable, project-specific* fact, decision, procedure, or lesson you'd want a FUTURE session to recall. **Do NOT write** plain acknowledgements, ephemeral / general-knowledge questions (arithmetic, definitions, one-off lookups), or anything with no new project-specific fact — `write-gate` filters *low-signal* noise but not *off-topic* writes, so the should-fire judgement remains with the invoking protocol.

Protocol:
1. Search existing pages first.
2. Prefer updating an existing page over creating a new one; fewer rich pages beat many thin one-off pages. **Dedup-at-write:** `python skills/wiki-memory/tools/wiki.py overlap --title "<title>" --tags "a,b" [--body-file <draft>]`. `high` → update the reported `best_match` instead of creating (two pages on one subject inevitably drift apart). `moderate` → create, but it's a Consolidate candidate for [`wiki-refresh`](../wiki-refresh/SKILL.md). `low` → create.
3. **Pre-check the candidate with [`write-gate`](../write-gate/SKILL.md)** — `python skills/write-gate/tools/write_gate.py gate --kind <kind> --file <candidate>`. If it rejects, revise or drop; do not bypass.
4. If no page, run `python skills/wiki-memory/tools/wiki.py new --template page --title "<title>" --domain "<domain>"`.
5. Name new pages at domain/category level, not task-specific bug names.
6. Fill v2 frontmatter completely.
7. **Why-clause requirement (decisions / conventions):** the page body must contain at least one of `because …`, `so that …`, `to avoid …`, `in order to …`, `due to …`. (`since` is intentionally *not* accepted — it reads as temporal and was bypassing the gate; write a causal `because`/`in order to` instead. See `write_gate.py` `WHY_CLAUSES`.) Reasonless decisions are rejected by write-gate. Source: [codenamev/claude_memory](https://github.com/codenamev/claude_memory) (100% on a 100-case FEVER-derived test).
8. For procedures/failures, include when it applies and the exact prevention rule.
8b. **Retrieval cue (the observable symptom).** For `error` / `lesson` / `sop` pages, add a body line naming the *observable signal* a future agent would pattern-match on — the symptom, not the topic:
    ```
    **Trigger / symptom:** off-by-hours in date tests (failing by exactly the local UTC offset)
    ```
    Put it **in the page body**, not in a bespoke `trigger:` frontmatter key. `wiki.py search` ranks over title/type/tags/path/preview/**body** — it does **not** index arbitrary frontmatter keys, so a frontmatter-only `trigger:` is a silent search no-op (verified: a phrase living only in frontmatter returns zero hits). A body cue makes the lesson findable by its symptom phrase via the normal search→timeline→fetch path (no load-all-up-front). Phrase it as the symptom itself (a noun phrase / the left side of the "→"), not as ordered fix-steps. Optionally also echo the key symptom word in `tags:` (tags are indexed and weighted), but the body line is the canonical, always-searchable form.
9. Add ≥2 useful wikilinks when possible.
10. Append `wiki/log.md`.
11. Run `python ... index`; for new v2 pages run `python ... lint --strict`.
12. **Selective refresh on write (compounding loop):** if this write *contradicts* or *supersedes* an existing page, or a refactor/rename invalidated refs a related page cites, invoke [`wiki-refresh`](../wiki-refresh/SKILL.md) with the **narrowest** scope hint (the affected page id / tag / dir) — don't wait for the periodic sweep. A new fact that invalidates an old one is exactly when reconcile pays off. Fire only on contradiction/supersession/refactor signals, not on every write. (Port of EveryInc ce-compound Phase 2.5 selective-refresh-check.)

**Conflict & trust — the poison defense (`write-gate` is NOT a truth filter).** The gate scores *signal/quality*, not *truth*: a confident, well-formed but WRONG lesson passes it (measured — 8/8 adversarial lessons passed at mean score 4.88; `eval/exp5_adversarial/`). So before writing a fact that may **contradict** an existing same-subject page, run the trust-gated check:
```bash
python3 skills/wiki-memory/tools/wiki.py resolve --title "<t>" --body-file <draft> --tags "a,b" --trust <tier>
```
Tiers: `asserted` (default) < `corroborated` (independently re-seen) < `verified` (checked against code/test/fs, cf. `audit-refs`) < `user_confirmed`. Stamp each page's tier at creation with `new --trust <tier>`. `resolve` returns an action: **create** (no same-subject page) · **replace** (your higher-trust correction supersedes — wire `supersedes`/`superseded-by`) · **reject** (a higher-trust page exists; do NOT overwrite — raise trust by verifying, or record `contradicts:[[…]]`) · **dispute** (equal trust — mark `contradicts:` both ways so retrieval surfaces the conflict instead of serving one as truth). This recovers the truth+poison coexistence case (measured — dependent accuracy 0.5→1.0). **Honest limit:** with no competing truth and no verifier, a lie can only be *flagged unverified*, not corrected — that hand-off is [`verify-before-completion`](../verify-before-completion/SKILL.md) + code-grounded checks. (Pure logic in [`provenance.py`](tools/provenance.py).)

## Consolidate & decay *(2026-06-12)*

```
python3 skills/wiki-memory/tools/wiki.py consolidate [--min-fetches N] [--apply]
python3 skills/wiki-memory/tools/wiki.py decay [--halflife-days D] [--apply]
```

`consolidate`: reuse-driven promotion — pages **fetched** ≥N times (search hits don't count) while still `trust: asserted` become `corroborated` candidates. One tier only: `verified` stays earned through write-gate evidence, never popularity. `raw/` and `L4_archive/` are immutable. Report-first; `--apply` rewrites trust frontmatter, deletes nothing. Fetch counts live in `<wiki>/.brainer/usage.json` (gitignored; ledger corruption never breaks reads).

`decay`: time-based confidence aging (exponential, default half-life 405d; vendored from PROMPTER's memory-decay — `tools/decay.py`). Protection class skips `type: error|lesson|sop|procedure`, `protected: true`, `evidence_count ≥3`, `L0_rules.md`/`L3_sops/`/`raw/`. Dry-run by default. Run weekly/before audits, never per-prompt.

## Schema-evolution (recurring failures → proposed rules)

```bash
python3 skills/wiki-memory/tools/wiki.py schema-evolution [--threshold N]
```

Karpathy's point that the human's *primary* lever is refining the **schema** (not editing pages), made autonomous. Instead of fixing the same defect page-by-page forever, a defect class that recurs ≥`--threshold` (default 3 — rule of three) becomes a **proposed amendment** to `schema.md` / the page templates (e.g. recurring `missing_trigger_cue` → "bake a Trigger/symptom line into the lesson template"). Signal = the wiki's own `lint --strict` warning histogram + an optional append-only reject log at `<root>/.brainer/schema_signals.jsonl`.

**Report-only, human-gated by hard rule:** it NEVER edits `schema.md`. `schema.md` is a canonical contract co-owned by human + agent; the loop *proposes* (with evidence — count + target section), a human approves and applies. That gate is the schema-side analogue of `quorum` for facts and is why [`task-retrospective`](../task-retrospective/SKILL.md) likewise won't auto-edit canonical contracts. Run periodically (with `decay`/`wiki-refresh`), not per-prompt.

## Lint

```
python3 skills/wiki-memory/tools/wiki.py lint [--strict] [--stale-days N] [--hub-threshold N] [--scope PATH ...]
```

Always-on findings: broken `[[wikilinks]]`, orphans (0 inbound), duplicate titles, stale `verified:` (>`--stale-days`, default 180, with `age_days`), gravity-well hubs (inbound > `--hub-threshold`, default 20). `--scope` adds extra roots so trees outside the wiki (concepts/, runbooks/, designs/foo/ledger.md) participate in the link graph and get hygiene-scanned. `--strict` adds v2-frontmatter enforcement, missing-provenance / missing-backlinks warnings, and supersession-reverse-link checks.

Write-gate (two layers). Both are **procedure gates** — agent steps in the write protocol above, not code auto-invoked by `wiki.py`. `wiki.py` enforces only the structural guard (a duplicate filename raises `FileExistsError`); the rest is agent discipline plus `lint`/`lint --strict` flagging violations after the fact.

**Execution gate** (agent discipline — see [`verify-before-completion`](../verify-before-completion/SKILL.md)):
- No durable memory from unexecuted plans.
- No trivial lookups inflated into fake procedures.
- `wiki/raw/` is immutable after creation (convention; not enforced by the write path).
- No duplicate page without supersession.

**Content gate** (run [`write-gate`](../write-gate/SKILL.md) before the write, per protocol step 3):
- Candidate must score above the signal threshold (decisions / errors / architecture / code / numbers, minus filler / speculation).
- Decisions and conventions must embed a why-clause.

## Aging & reconcile

Once a page is in the wiki, two companions maintain it:
- Page `confidence` and the `verified:` date carry staleness signal; `wiki-refresh` reconciles drifted pages against the codebase, and `lint --strict` flags pages whose `verified:` date is stale.
- [`wiki-refresh`](../wiki-refresh/SKILL.md) reconciles pages against the *current codebase* (Keep/Update/Consolidate/Replace/Delete) and emits typed `contradicts:` edges. Drift signal: `python skills/wiki-memory/tools/wiki.py audit-refs [--code-root PATH]` lists pages whose cited code paths no longer exist. Run decay weekly (cheap), refresh monthly or after a refactor/rename (costs reads).
- **Belief-update propagation:** `python3 skills/wiki-memory/tools/wiki.py stale-citers` surfaces pages whose **body** cites a `superseded-by`/`contradicts:`-marked page — a supersession does NOT auto-ripple to its citers, so they keep pointing at outdated knowledge. Run it in [`wiki-refresh`](../wiki-refresh/SKILL.md) right after wiring any supersession/contradiction edge, then repoint each citer at the newer page (or note the dispute). Report-only: it never rewrites another page's body (invalidate-don't-delete; surface, don't silently mutate).

## Tier layout

```
wiki/
├── L0_rules.md        # stable behavior rules
├── L1_index.md        # compact pointer catalog (lists concepts/patterns/projects/queries)
├── concepts/          # atomic technique pages  ← durable facts land here in practice
├── patterns/          # reusable workflows/runbooks  ← SOPs land here in practice
├── projects/          # target-project pages
├── people/            # referenced humans
├── queries/           # durable Q&A
├── raw/               # immutable sources
├── L2_facts/          # available fact tier (often empty — see note)
├── L3_sops/           # available SOP tier (often empty — see note)
├── L4_archive/        # cold session archives
├── index.md           # rich catalog
├── log.md             # append-only timeline
└── schema.md          # contract for page types
```

**Pick the folder by *kind of knowledge*, not by L-tier number.** In practice
durable facts are filed under `concepts/`/`queries/` and reusable playbooks under
`patterns/`; `L2_facts/`/`L3_sops/` are available L-tier buckets that are usually
empty and are **not** the primary store. Don't send an agent to look in an empty
`L2_facts/` for a fact that lives in `concepts/`. `L1_index` catalogs the topical
folders so the knowledge is discoverable at startup.

## Boundary with graphify

If the project has `graphify-out/graph.json` (auto-extracted code graph), do not duplicate its content here. Split:

- **`graphify-out/`** owns the *what / how / connected-to* layer: symbols, callers, modules, communities. Auto-extracted, refreshed on commit, ephemeral.
- **`wiki/`** owns the *why / decision / failure-lesson* layer: rationale, trade-offs, incidents, durable procedures. Hand-curated, gated, permanent.

When writing a new page, first run `graphify query "<topic>"` (or grep `graphify-out/GRAPH_REPORT.md`); if the answer is already covered by the auto-graph, the page is redundant — skip the write. The reverse also holds: don't try to make graphify carry the *why*; it can't.

## OKF interop & quality scans

Grounded in a deep review of Google's Open Knowledge Format (OKF v0.1, `GoogleCloudPlatform/knowledge-catalog`). Our `page_id` already equals an OKF concept-id (path-minus-ext), so interop is a thin serializer; the higher-value adoptions are the eval-lens detectors our toolchain lacked.

```
python3 skills/wiki-memory/tools/wiki.py export-okf --out <dir>     # one-way publish to a conformant OKF bundle
python3 skills/wiki-memory/tools/wiki.py okf-validate --bundle <dir>  # v0.1 conformance check (exit 1 if not)
python3 skills/wiki-memory/tools/wiki.py health                     # ONE-PASS epistemic health across all six lenses (0 = healthy) — start here
python3 skills/wiki-memory/tools/wiki.py contradict-scan            # candidate cross-page contradictions (numeric divergence)
python3 skills/wiki-memory/tools/wiki.py novelty                    # intra-page redundancy_index (echo-vs-synthesis)
python3 skills/wiki-memory/tools/wiki.py claim-ground <id>          # flag prose claims whose cited artifact is gone
python3 skills/wiki-memory/tools/wiki.py claim-audit                # per-page data/directive/judgment mix; flag opinion-heavy weak-evidence pages
python3 skills/wiki-memory/tools/wiki.py synth-candidates           # clusters of same-subject pages ripe for a higher-order synthesis note
python3 skills/wiki-memory/tools/wiki.py maturity                   # observation>hypothesis>rule: promotion + conflict-driven demotion candidates
python3 skills/wiki-memory/tools/wiki.py gaps                       # knowledge-completeness: recurring wikilink targets with no page (missing concepts)
python3 skills/wiki-memory/tools/wiki.py calibration                # confidence-vs-evidence: over/under-confident pages
```

- **`export-okf`** — serializer only (no import, no sibling sync — sibling-sync is byte-rsync of skill *code*, not a knowledge channel). Remaps frontmatter (`timestamp←updated`, `description←preview`, `title←body H1`), rewrites `[[wikilinks]]`→`/id.md`, synthesizes per-dir `index.md` (+ `okf_version` at root) and `log.md`. All governance keys (trust/confidence/supersedes/…) ride along as OKF custom keys. View the graph with the upstream `viz.html` pointed at the bundle.
- **`contradict-scan`** (rec F) — the *detection* layer above declared `contradicts:` edges: same-subject pairs with (a) diverging numbers for a shared key, or (b) a **polarity conflict** (negation-flip / antonym on near-identical wording), minus already-declared edges. **Type-aware**: polarity is skipped when both pages are judgment-dominant (opinion×opinion is expected divergence, not contradiction). High-overlap-gated to keep false positives near zero (measured: 0 on the live wiki). Each candidate carries a deterministic **`suggested_resolution`** verb (report-only, borrowed from Zep "invalidate-don't-delete" + mem0): `invalidate` (polarity contradiction — keep higher-trust/newer, mark other `contradicts:`), `supersede` (numeric value change — newer/higher-trust value wins, `superseded-by`), or `dispute` (equal trust+recency — flag both). Output is **candidates for confirmation**, not truth — confirm, then write the edge. Use in [`wiki-refresh`](../wiki-refresh/SKILL.md).
- **`novelty`** (rec H) — intra-page tautology score, orthogonal to `overlap`/graphify (those are inter-document). Low score = page echoes its own headings/schema/refs; a write-gate / refresh signal.
- **`claim-ground`** (rec G) — sentence-granular grounding finer than `audit-refs`; the semantic "does present code match the prose" verdict is a judge step for `wiki-refresh`.
- **`synth-candidates`** — the *synthesizing-knowledge* lens. Inverse of dedup: clusters distinct same-subject pages (≥2 shared tags) ripe for a higher-order synthesis note (RAPTOR / GraphRAG community-summary pattern). Report-only — the agent writes the synthesis; flags clusters that already have a likely synthesis parent. Edges are tag-based only (wikilink edges over-cluster the dense link graph into one blob — measured).
- **`health`** — the usable capstone: one pass that runs all six lenses + novelty and rolls up the actionable counts per angle (`0` total = healthy). Start here; run the individual verb behind any non-zero count for detail.
- **`calibration`** — the *confidence-vs-evidence* lens. A page's `confidence` scalar and its actual evidence (sources + inbound corroboration + trust tier + verified-freshness, scored 0–4) are stored independently and drift apart. Flags **overconfidence** (high confidence, weak evidence) and **underconfidence** (low confidence, strong evidence). Distinct from trust (evidence strength) and maturity (the ladder) — it checks *consistency between two stored signals*. Sharp/low-noise (live: 1 over, 1 under of 42). Report-only.
- **`gaps`** — the *knowledge-completeness* lens (what's MISSING, not what's written). Aggregates recurring `[[wikilink]]` targets that resolve to no page and ranks by reference frequency: a concept referenced ≥N times with no canonical page is a real gap (a one-off is just a typo); a repeatedly-referenced `[[?stub]]` is a promised-but-unwritten note. Path-style targets need an exact match; bare names keep the stem fallback. Sources are curated pages only (raw/ is frozen). Report-only.
- **`maturity`** — the *observation→hypothesis→rule* lens. Maturity is a separate axis from trust (a verified page can be superseded-maturity). Infers each page's dominant stage from its claim mix + type and surfaces two currently-unsurfaced signals: **promotion** (a hypothesis/observation page still `trust: asserted` but cited many times → corroborate/distill toward a rule; each candidate carries `corroborating_inbound` — citations *from observation pages* are evidence accrual (A-MEM), distinct from mere popularity — and `has_falsifier` — a rule earns its status only by stating what would falsify it, Popper/LangMem, so a promotion candidate without one is flagged "state a falsification condition first") and **conflict-driven demotion** (a rule/verified page carrying a `contradicts:` edge → review, don't silently trust). Report-only.
- **`claim-audit`** — the *data-vs-opinion-vs-decision* lens. Grades each page's claims by epistemic klass via [`claim_grade.py`](tools/claim_grade.py) and flags judgment-heavy pages with weak evidence (an opinion page posing as durable memory). **Report-only heuristic, never a gate** — per-claim typing is measurably noisy (blind validation: even independent annotators agree only ~40% unanimously on messy SOP prose), so interpret aggregate ratios, not single labels. The grader abstains (`unknown`) on unmarked text.
- **`resource:` / `[[?stub]]`** — see schema.md. Relationship-as-page (OKF `references/joins`): promote a content-bearing derivation to its own page, but keep `supersedes`/`contradicts` as typed directional frontmatter, never untyped OKF body links.

## Optional MCP

`tools/wiki_mcp/` exposes `wiki_search`, `wiki_fetch`, `wiki_timeline`, `wiki_new` for MCP-aware hosts.

## Files

```
tools/
├── wiki.py            # search/fetch/timeline/new/index/lint
├── code_map.py        # symbol-level navigation aid
├── config.py          # path + threshold defaults
├── tokens.py          # shared token estimator
├── wiki_mcp/          # optional MCP server
├── test_lint_hygiene.py
└── README.md
```
