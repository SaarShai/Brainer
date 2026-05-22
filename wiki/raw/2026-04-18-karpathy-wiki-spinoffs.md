---
type: raw
date: 2026-04-18
source: sonnet subagent
tags: [karpathy, wiki, research]
---

# Karpathy-wiki spin-offs — lessons

5 projects surveyed. Full synthesis below, followed by 5 additions queued for our wiki.

## 1. obsidian-mind (MIT)
- 5-hook pipeline: `session-start.ts` (inject North Star + git + vault listing), `classify-message.ts` (UserPromptSubmit routing), `pre-compact.ts` (snapshot transcript, keep last 30), `stop-checklist.ts` (orphan + index check), `validate-write.ts` (PostToolUse guard).
- `vault-manifest.json` — machine-readable infrastructure / scaffold / user_content boundaries. Enables safe `/vault-upgrade`.
- `brain/Memories.md` as pure index/MOC; no facts live in it; facts in linked pages.

## 2. dair.ai Karpathy pattern
- **Four-phase ingest cycle**: Ingest → Compile → Query & Enhance → Lint & Maintain. Compile separate from ingest = batch amortization, less write amplification.
- Query answers with reuse value are filed back.
- LLM-driven periodic health checks (inconsistency, missing-data imputation).

## 3. rohitg00 agentmemory gist
- `confidence` + `verified` date + `supersedes`/`superseded-by` chain.
- Retention decay (Ebbinghaus): unreinforced facts demoted semantic → episodic → archived.
- Typed entity-relation graph: `uses`, `depends_on`, `contradicts`, `caused`.

## 4. forrestchang/andrej-karpathy-skills (MIT)
- Declarative `DONE_WHEN:` success criteria per operation — gives agent a loop-exit condition.
- Install-as-plugin path (`/plugin install`) — no manual CLAUDE.md edits.
- `EXAMPLES.md` separate from `SKILL.md` — few-shot samples loaded on demand.

## 5. rarce/git-wiki (MIT)
- `log.md` grep-friendly markdown: `## [YYYY-MM-DD] op | title`. JSONL harder to grep without tooling.
- `sources/` immutability enforced by explicit SKILL.md + PostToolUse guard (not just convention).
- `people/` + `concepts/` as typed sub-dirs → filter-scoped search.

## Cross-cutting (all 5)
1. Raw = immutable. Agent only writes compiled/wiki layer.
2. Schema / SKILL.md is the governance artifact (the real product).
3. `index.md` + `log.md` mandatory.
4. Hook events = primary automation surface.
5. Hybrid search (BM25 + semantic) preferred.

## 5 additions for our wiki (gaps)

| # | add | effort | impact |
|---|---|---|---|
| 1 | **Supersession chain**: `supersedes`/`superseded-by`/`verified` in frontmatter + auto-update on contradict | low | high — ages knowledge explicitly |
| 2 | **classify-message hook** on UserPromptSubmit: pattern-match prompt → inject template reminder | low | med — prevents layer confusion |
| 3 | **validate-write guard** blocking writes to `raw/` | trivial | high — enforces immutability |
| 4 | **Typed `relations:`** in frontmatter + monthly lint for orphan decay | med | med — richer retrieval |
| 5 | **Switch `log.md` to grep-friendly** `## [YYYY-MM-DD] op | title` format | trivial | med — shell-native history queries |

All 5 source projects MIT or no-license-blog — safe to borrow patterns.
