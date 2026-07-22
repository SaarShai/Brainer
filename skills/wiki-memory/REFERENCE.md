# wiki-memory — deep-dive reference

Extended reference material for [`SKILL.md`](SKILL.md): compile-ingest of external
sources, loop-mode's memory contract, consolidate/decay maintenance, schema-evolution,
aging & reconcile, the graphify boundary, and OKF interop/export. Consult this when the
retrieve/write core in `SKILL.md` isn't the operation you need — not on every trigger.

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

## Loop Mode

Use this mode when [`loop-engineering`](../loop-engineering/SKILL.md) names a loop memory contract. The rhythm is **recall before pass, write after pass**:

1. **Recall before each pass:** read the loop's `state_store`, then run `wiki.py search "<loop topic>"`, inspect relevant timelines, and fetch only the pages needed to re-anchor the pass. Treat `anchor_files` and the loop state as required inputs, not optional context.
2. **Write after each pass:** record attempts tried, verifier verdict, failures, state revision, and next action in the loop state file or board. Do not write every pass log into the wiki.
3. **Promote only durable lessons:** if a pass produced a verified, project-specific lesson that future sessions should recall, use the normal write path below: search/overlap first, gate with `write-gate`, update or create one narrow page, read it back, and append `wiki/log.md`.
4. **Update facts in place:** prefer updating/superseding the existing same-subject page over appending a fresh near-duplicate. Use `overlap` and `resolve` when a new pass changes an old fact.

Brainer's default memory backend is this repo-local wiki plus explicit loop state on disk. External semantic stores can be explored later behind an adapter only after they beat this contract on a Brainer task benchmark; do not add a vendor dependency just because a loop needs memory.

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

## Aging & reconcile

Once a page is in the wiki, two companions maintain it:
- Page `confidence` and the `verified:` date carry staleness signal; `wiki-refresh` reconciles drifted pages against the codebase, and `lint --strict` flags pages whose `verified:` date is stale.
- [`wiki-refresh`](../_shared/briefs/wiki-refresh.md) reconciles pages against the *current codebase* (the Keep/Update/Consolidate/Replace/Delete decision is wiki-refresh's — not restated here) and emits typed `contradicts:` edges. Drift signal: `python skills/wiki-memory/tools/wiki.py audit-refs [--code-root PATH]` lists pages whose cited code paths no longer exist. Run decay weekly (cheap), refresh monthly or after a refactor/rename (costs reads).
- **Belief-update propagation:** `python3 skills/wiki-memory/tools/wiki.py stale-citers` surfaces pages whose **body** cites a `superseded-by`/`contradicts:`-marked page — a supersession does NOT auto-ripple to its citers, so they keep pointing at outdated knowledge. Run it in [`wiki-refresh`](../_shared/briefs/wiki-refresh.md) right after wiring any supersession/contradiction edge, then repoint each citer at the newer page (or note the dispute). Report-only: it never rewrites another page's body (invalidate-don't-delete; surface, don't silently mutate).

**Temporal semantics — what this store does and does not model.** The wiki
implements **epistemic time** only: `supersedes`/`superseded-by`/`contradicts`
edges + trust tiers say *"this belief replaced or disputes that belief"* — which
is where graph memory measurably earns its keep (temporal/supersession reasoning
is the one axis where graph variants beat flat memory in the published evals;
plain lookup ties or loses). It does **not** model **valid time** ("this fact
held from T1 to T2") à la Graphiti/Zep bi-temporal intervals — a deliberate
non-adoption (see `wiki/concepts/framework-hardening-adoption.md` rows 7/12): no
measured need at this scale, and a bi-temporal engine is infra we reject. If a
future eval shows event-time failures, the smallest next step is one optional
`occurred:` field on event/observation pages, not an engine.

## Boundary with graphify

If the project has `graphify-out/graph.json` (auto-extracted code graph), do not duplicate its content here. Split:

- **`graphify-out/`** owns the *what / how / connected-to* layer: symbols, callers, modules, communities. Auto-extracted, refreshed on commit, ephemeral.
- **`wiki/`** owns the *why / decision / failure-lesson* layer: rationale, trade-offs, incidents, durable procedures. Hand-curated, gated, permanent.

When writing a new page, first run `graphify query "<topic>"` (or grep `graphify-out/GRAPH_REPORT.md`); if the answer is already covered by the auto-graph, the page is redundant — skip the write. The reverse also holds: don't try to make graphify carry the *why*; it can't.

## OKF interop

Grounded in a deep review of Google's Open Knowledge Format (OKF v0.1, `GoogleCloudPlatform/knowledge-catalog`). Our `page_id` already equals an OKF concept-id (path-minus-ext), so interop is a thin serializer:

```
python3 skills/wiki-memory/tools/wiki.py export-okf --out <dir>     # one-way publish to a conformant OKF bundle
python3 skills/wiki-memory/tools/wiki.py okf-validate --bundle <dir>  # v0.1 conformance check (exit 1 if not)
```

- **`export-okf`** — serializer only (no import, no sibling sync — sibling-sync is byte-rsync of skill *code*, not a knowledge channel). Remaps frontmatter (`timestamp←updated`, `description←preview`, `title←body H1`), rewrites `[[wikilinks]]`→`/id.md`, synthesizes per-dir `index.md` (+ `okf_version` at root) and `log.md`. All governance keys (trust/confidence/supersedes/…) ride along as OKF custom keys. View the graph with the upstream `viz.html` pointed at the bundle.
- **`resource:` / `[[?stub]]`** — see schema.md. Relationship-as-page (OKF `references/joins`): promote a content-bearing derivation to its own page, but keep `supersedes`/`contradicts` as typed directional frontmatter, never untyped OKF body links.

The nine **quality-scan verbs** the same review produced (`health` · `contradict-scan` · `novelty` · `claim-ground` · `claim-audit` · `synth-candidates` · `maturity` · `gaps` · `calibration`) are maintenance instruments, not retrieve/write protocol — documented in [`wiki-refresh`](../wiki-refresh/REFERENCE.md#quality-scan-verbs), which owns the reconcile pass that consumes them. (The code stays here, in `tools/wiki.py`.)

## Optional MCP

`tools/wiki_mcp/` exposes `wiki_search`, `wiki_fetch`, `wiki_timeline`, `wiki_new` for MCP-aware hosts.
