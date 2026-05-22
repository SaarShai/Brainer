---
type: concept
axis: knowledge_org
tags: [wiki, governance, schema]
confidence: med
related: [[raw/2026-04-18-karpathy-wiki-spinoffs]], [[schema]]
---

# Wiki governance — enforced schema

Rules the wiki is supposed to follow. Most were implicit in v1. Promoting to explicit + enforcement-ready after the Karpathy-spinoff survey.

## Frontmatter (required on all wiki pages)

```yaml
---
type: concept | project | raw | session-memory | pattern | ...
axis: input_compression | output_filter | cross_session_memory |
      verification | knowledge_org | measurement | skill_crystallization | meta
tags: [...]
confidence: low | med | high
evidence_count: N            # number of distinct evidence points
verified: YYYY-MM-DD         # last-check date
supersedes: [old-page]       # optional, array
superseded-by: new-page      # optional, null when not superseded
relations:                    # optional, typed
  - {type: depends_on, target: "X"}
  - {type: contradicts, target: "Y"}
---
```

## Immutability rules

| folder | rule | enforcement |
|---|---|---|
| `raw/` | append-only, never rewrite | validate-write hook (planned) |
| `wiki/` = `concepts/`, `patterns/`, `projects/` | mutable, track via supersession | manual + lint pass |
| `schema.md`, `index.md`, `log.md`, `ROADMAP.md` | meta — update often, careful | manual |

## log.md format (grep-friendly, switched from JSONL after Karpathy-spinoff lesson)

```
## [YYYY-MM-DD] <op> | <title>

<free-form body 1-3 lines>
```

Ops vocabulary: `ingest`, `compile`, `decide`, `ship`, `reject`, `measure`, `supersede`, `lint`.

Shell queries:
```bash
grep "^## \[" log.md                # all entries
grep "reject\|supersede" log.md     # contradictions + retractions
grep -A3 "\[2026-04-18\]" log.md    # one day's activity
```

## Hooks (planned enforcement layer)

| hook | tool | purpose | status |
|---|---|---|---|
| SessionStart | context-keeper-v2 | inject L0 + L1 | skeleton |
| UserPromptSubmit | classify-message | route prompt → template | not built |
| PostToolUse(Write\|Edit) | validate-write | block writes to raw/ | not built |
| PreCompact | context-keeper v1 | extract + pointer | **live** |
| Stop | skill-crystallizer | detect + write L3 SOP | spec |

## Supersession protocol

When a page replaces an older claim:
1. New page gets frontmatter `supersedes: [old-page]`.
2. Old page gets `superseded-by: new-page` + confidence demoted one tier.
3. Entry in `log.md`: `## [YYYY-MM-DD] supersede | <old> → <new>`.

## Retention decay (planned monthly lint)

Unreinforced pages age out:
- `verified` > 90 days + 0 new backlinks → demote `semantic` → `episodic`.
- `verified` > 180 days + still no activity → move to `raw/archived/YYYY-MM/`.

## DONE_WHEN contracts (borrowed from karpathy-skills)

Every `projects/<tool>/README.md` declares a `DONE_WHEN:` section listing testable exit criteria. Lets agents know when a tool is "ready" vs "WIP."
