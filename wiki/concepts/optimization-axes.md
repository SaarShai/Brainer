---
type: concept
tags: [framework, categorization, meta]
confidence: high
---

# Optimization axes — what each tool optimizes

Seven axes. Every tool in this repo declares which axis it targets (frontmatter `axis:` field). Lets us spot gaps and avoid rebuilding what's covered.

| axis | id | what it optimizes |
|---|---|---|
| A. Input compression | `input_compression` | per-prompt input-token cost |
| B. Tool-output filtering | `output_filter` | per-call noise → signal ratio |
| C. Cross-session memory | `cross_session_memory` | compound savings + quality over time |
| D. Verification / quality | `verification` | reliability under compression/automation |
| E. Knowledge organization | `knowledge_org` | fast lookup, productivity, context management |
| F. Measurement / trust | `measurement` | confidence in claimed savings |
| G. Skill crystallization | `skill_crystallization` | one-time work → reusable asset |

## Current tools by axis

| tool | axis | status |
|---|---|---|
| [[projects/compound-compression-pipeline/RESULTS\|ComCom]] | A. input_compression | eval-v3 passed |
| [[projects/semdiff/README\|semdiff]] | B. output_filter (file reads) | MCP shipped |
| native output-filter hook | B. output_filter (terminal stdout) | raw recovery + stats + rules shipped |
| [[projects/context-keeper/README\|context-keeper v1]] | C. cross_session_memory (intra-session only) | hook active |
| [[projects/context-keeper-v2/README\|context-keeper v2]] | C. cross_session_memory (true cross-session) | skeleton |
| skip_detector | D. verification | integrated |
| verify.py / verify_anthropic.py | D. verification | shipped |
| rename_detect | D. verification (semdiff companion) | integrated |
| Token Economy wiki (this) | E. knowledge_org | live |
| [[projects/wiki-search/README\|wiki-search]] | E. knowledge_org (retrieval) | skeleton |
| [[bench/README\|bench]] | F. measurement | 7 datasets |
| eval-v3/v4 harnesses | F. measurement | SQuAD+CoQA |
| [[projects/skill-crystallizer/README\|skill-crystallizer]] | G. skill_crystallization | skeleton |

## Governance axis (meta — cuts across all 7)

| concept | see |
|---|---|
| Wiki frontmatter + supersession + hooks | [[concepts/wiki-governance]] |
| Karpathy wiki spinoffs surveyed | [[raw/2026-04-18-karpathy-wiki-spinoffs]] |

## Borrowed patterns (external → our axes)

| source | idea | axis | applied to |
|---|---|---|---|
| GenericAgent L0-L4 | memory tier schema | C | context-keeper-v2 |
| claude-mem 3-layer | index → timeline → fetch | E | wiki-search |
| GenericAgent "no execution, no memory" | write-gate | C, G | write-gate lib |
| Karpathy wiki | 3-layer raw/wiki/schema | E | this wiki |
| Superpowers | mandatory skill checks + evidence gates | G, D | on-demand skills + verification-before-completion |
| omni | stdout filter, raw rewind, stats, rules | B, F | native output-filter hook |
| rejected: cognee | graph memory | C | too code/python-heavy for our scope |

## Rules for new tools

1. Every new tool declares its `axis:` in frontmatter.
2. If a proposed tool overlaps an existing axis, it must beat the incumbent on a measurable metric, or be rejected.
3. Gaps (axes with no tool) are open-tickets in [[ROADMAP]].
