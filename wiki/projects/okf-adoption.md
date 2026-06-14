---
schema_version: 2
title: "OKF adoption — what we took, what we dropped"
type: project
domain: tools
tier: semantic
confidence: 0.9
created: 2026-06-14
updated: 2026-06-14
verified: 2026-06-14
sources: [https://github.com/GoogleCloudPlatform/knowledge-catalog/blob/main/okf/SPEC.md, skills/wiki-memory/tools/wiki.py, skills/wiki-memory/tools/test_okf.py]
resource: skills/wiki-memory/tools/wiki.py
supersedes: []
superseded-by:
contradicts: []
tags: [okf, interop, wiki, decision, sibling-sync]
---

# OKF adoption — what we took, what we dropped

Decision record after a deep review of Google's Open Knowledge Format (OKF v0.1, `GoogleCloudPlatform/knowledge-catalog`). Records the *why* so a future session does not re-propose the rejected framings. Implemented + tested 2026-06-14 (46/46 suite, `[[schema]]`-conformant export validated under real PyYAML).

## Framing (the load-bearing conclusion)

OKF standardizes the *substrate* our wiki had already independently converged on (markdown + YAML frontmatter, path-based ids, link graph, progressive index, append log). Our `page_id` equals an OKF concept-id byte-for-byte (path-minus-ext). **So the data model is NOT the prize** — it maps ~1:1 and is cheap. The leverage is OKF's enrichment-eval *lenses*, because our toolchain had **zero semantic/judge layer** (all detection was regex / `.exists()` / Jaccard). Our governance (trust tiers, write-gate, decay, refresh) is the differentiator OKF cannot express — keep it as the moat.

## Adopted (shipped in `wiki.py`)

- **`export-okf` — ONE-WAY publish serializer only.** Because `page_id == OKF concept-id`, serialization is near-free (frontmatter remap + wikilink rewrite + synthesized `index.md`/`log.md`); governance keys ride along as preserved OKF custom keys. Adopted in order to make our knowledge consumable by any OKF tool and to borrow the upstream `viz.html` graph viewer without building one.
- **`contradict-scan` / `novelty` / `claim-ground`** (OKF eval lenses: `absence_of_contradictions`, `redundancy_index`, `hallucination_free`). Adopted because we stored DECLARED `contradicts:` edges but had no DETECTION, and `audit-refs` only checked path existence, not whether prose echoes its source or describes present code wrongly. These are candidate-surfacing detectors feeding the `wiki-refresh` skill; the semantic verdict stays a judge step.
- **`resource:` frontmatter field** (single-valued canonical artifact pointer). Adopted because the overloaded `sources:` list silently hid **6 rotted artifact paths** — a single-valued pointer is existence-checkable where a mixed provenance list is not; strict lint now emits `broken_resource`. See `[[schema]]`.
- **`[[?stub]]` forward-ref hatch + `--fail-on-error` lint gate.** Adopted to align with OKF's "consumers MUST tolerate broken links" for intentional not-yet-written targets, while making strict lint a real CI gate (it was a no-op before).

## Dropped / rejected (do not re-propose)

- **OKF as a sibling-interchange format replacing rsync — CATEGORY ERROR.** Dropped because sibling-sync is byte-rsync of skill *code* (`skills/` + `install.sh`); `wiki/` lives at repo root **outside** the sync path, so an OKF knowledge bundle has nothing to plug into. The sibling wikis are also stale clones of Brainer's OWN meta-wiki (no heterogeneous per-project knowledge to interchange), and repo doctrine is import-and-localize-then-sever (`[[schema]]`, Imported-Wiki-Completeness). For byte-identical code distribution a normalizing knowledge format is strictly *worse* than rsync. See `[[projects/delegate-router]]` for the multi-repo topology.
- **Two-way / live OKF sync.** Export is publish-only because round-trips through OKF's lossy single-`timestamp` + dropped-unknown-keys risk silently downgrading our trust/confidence/supersedes governance state.
- **Per-directory `index.md` now.** Deferred because `L2_facts/`, `L3_sops/`, `queries/` are empty and the corpus is small — a monolithic index is correctly sized. The exporter synthesizes per-dir `index.md` at export time instead.

## Kept guardrails (E)

Closed `type` enum + write-gate (OKF's open string is tolerated only at the export boundary); no `# Citations` body section (keep `sources:`); typed `supersedes`/`contradicts` edges stay directional frontmatter, never untyped OKF body links. See `[[concepts/wiki-governance]]`.
