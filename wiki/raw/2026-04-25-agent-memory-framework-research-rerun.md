---
schema_version: 2
title: "Agent memory framework research rerun"
type: raw
domain: external-source
tier: episodic
confidence: 0.7
created: 2026-04-25
updated: 2026-04-25
verified: 2026-04-25
sources: ["gemini --approval-mode plan --output-format json", "Ollama gemma4:26b local API call"]
supersedes: []
superseded-by:
tags: [research, memory, retrieval, mcp, local-models]
---

# Agent memory framework research rerun

## Source

- Hosted research: `gemini --approval-mode plan --output-format json -p "<agent memory/wiki/context-efficiency survey prompt>"`
- Local research: `gemma4:26b` through Ollama local API on the M1/M-family local model lane.
- Both used the same task prompt: survey public repos, skills, MCP servers, papers, and docs for LLM agent memory/wiki/context-efficiency frameworks similar to a repo-local Markdown wiki with progressive retrieval.

## Gemini Output

Gemini covered a broader ecosystem set:

- ByteRover: hierarchical context tree and progressive retrieval; useful for lifecycle/state ideas, but claims need independent validation before adoption.
- Graphiti/Zep: temporal knowledge graph and MCP-compatible memory; strong for decision history, but too infrastructure-heavy for the default Token Economy path.
- Cognee: GraphRAG and graph/vector memory; possible optional layer after simpler wiki retrieval is measured.
- Aider repo-map: Tree-sitter/PageRank style symbol map; high-value pattern for compact code context.
- LLM Wiki: interlinked Markdown wiki; validates Token Economy's file-native memory direction.
- Codebase-Memory MCP: persistent structural code graph; promising but needs license/freshness/test inspection.
- GAAI-style markdown governance: decision logs and governance rules; useful as lint/governance pressure rather than a runtime dependency.
- Claude Code memory/rules/skills: good procedural instruction layer; static inclusion does not scale as the primary memory layer.

## Local Gemma Output

The M1 local `gemma4:26b` pass was narrower and more implementation-shaped:

- Aider repo-map ranked highest for code tasks: structural code maps can prevent broad file reads.
- MCP servers were framed as the implementation bridge for just-in-time retrieval.
- Graphiti, Zep, and Cognee were useful semantic/graph layers but carried infrastructure and extraction risks.
- Claude Code rules/skills were treated as governance/procedural context, not scalable memory.

## Combined Takeaways

- Keep Markdown wiki as canonical memory.
- Use SQLite/search/MCP as local retrieval surfaces.
- Add code-map/repo-map structure as the next native layer for code tasks.
- Treat graph, vector, temporal memory, and Basic Memory-style aliases as optional future layers after measured failures in the current stack.
- Keep provider-specific cache guidance as cite-only unless a concrete Token Economy adapter is built.

## Adoption Result

- Implemented: `./te wiki context`, `./te delegate document --verified`, skill-crystallizer v1, and `./te code map`.
- Deferred: graph/temporal memory, Basic Memory-style aliases, lifecycle status fields, deeper Codebase-Memory inspection, and host `SessionEnd` hook wiring.

## Related

- [[concepts/framework-hardening-adoption]]
- [[projects/wiki-search/README]]
- [[projects/skill-crystallizer/README]]
- [[concepts/local-model-setup]]
