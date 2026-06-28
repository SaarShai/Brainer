# Brainer Usage Index

Catalog for a target project that uses Brainer locally. Load only matched pages.

## Startup
- [[L0_rules]] + [[L1_index]] — lean startup memory tiers
- [[schema]] — repo-local markdown wiki contract
- `brainer.yaml` — local framework config

## Commands

> There is no `./te` wrapper binary (it was planned, never shipped). Call each
> tool directly: wiki commands via `python3 skills/wiki-memory/tools/wiki.py …`;
> other capabilities via their owning skill's tool under `skills/<skill>/tools/`.

Wiki commands (this skill):
- `python3 skills/wiki-memory/tools/wiki.py search "topic"` — find relevant wiki pointers
- `python3 skills/wiki-memory/tools/wiki.py timeline "<id>"` — inspect the page's link graph (backlinks/outbound/neighbors — follow them as next-hops)
- `python3 skills/wiki-memory/tools/wiki.py fetch "<id>"` — load a relevant page
- `python3 skills/wiki-memory/tools/wiki.py context "task"` — build an audited bounded context packet
- `python3 skills/wiki-memory/tools/code_map.py "symbol or path"` — inspect compact code structure before file reads
- `python3 skills/wiki-memory/tools/wiki.py lint --strict` — validate wiki pages

Other framework capabilities (each provided by its own skill — invoke that skill's tool directly; there is no `./te`):
- doctor — verify local framework health
- context status / checkpoint — inspect context budget · create a lean continuation packet
- cost preflight / profile — pre-work context/tool guidance · transcript cost analysis
- delegate classify / cost-check / document — delegation routing and verified-evidence handoff
- pa — route context-light personal-assistant prompts

## Wiki Layout

Primary knowledge folders — new pages go here, picked by *kind* (all catalogued in L1):
- `concepts/` — atomic technique/idea pages (the bulk of curated knowledge)
- `patterns/` — reusable workflows and runbooks
- `projects/` — active target-project state
- `queries/` — durable Q&A

Other folders (not L1-catalogued):
- `people/` — referenced humans (entity scaffolding; reach via search)
- `raw/` — source summaries and imported evidence (immutable; search-only, never a write target)

L-tier buckets (available, often empty — not the primary store):
- `L2_facts/` — verified durable facts (in practice filed under `concepts/`/`queries/`)
- `L3_sops/` — reusable runbooks (in practice filed under `patterns/`)
- `L4_archive/` — cold history kept only when useful

## Extension Points
- `adapters/README` — project-local agent adapters
- `token_economy/code_map.py` — compact structural code-map provider
- [[concepts/framework-hardening-adoption]] — ranked adoption matrix and current hardening learnings
- [[concepts/lean-execution]] — plan/context/delegation pruning rules and source synthesis
- [[projects/delegate-router]] — model-agnostic routing plus local cost preflight/profile
- [[concepts/prefix-caching]] — stable-prefix rules for prompt cache friendliness
- [[raw/2026-05-16-ai-coding-bill-reduction-article]] — source-summary for the user-provided cost-reduction article
- [[raw/2026-04-25-agent-memory-framework-research-rerun]] — Gemini and local Gemma research outputs
- [[concepts/local-model-setup]] — current M1/M1B/M2 local model policy
- [[templates/page.template]] — wiki page template
- [[templates/source-summary.template]] — source summary template
- [[templates/decision.template]] — decision template
