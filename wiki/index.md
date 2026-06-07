# Brainer Usage Index

Catalog for a target project that uses Brainer locally. Load only matched pages.

## Startup
- [[L0_rules]] + [[L1_index]] — lean startup memory tiers
- [[schema]] — repo-local markdown wiki contract
- `brainer.yaml` — local framework config

## Commands
- `./te doctor` — verify local framework health
- `./te wiki search "topic"` — find relevant wiki pointers
- `./te wiki timeline "<id>"` — inspect nearby context
- `./te wiki fetch "<id>"` — load a relevant page
- `./te wiki context "task"` — build an audited bounded context packet
- `./te code map "symbol or path"` — inspect compact code structure before file reads
- `./te wiki lint --strict` — validate wiki pages
- `./te context status` — inspect context budget
- `./te context checkpoint --handoff-template` — create a lean continuation packet
- `./te cost preflight "task"` — emit provider-free context/tool/session guidance before broad work
- `./te cost profile --transcript <path>` — flag repeated reads, oversized outputs, search-order leaks, refresh pressure
- `./te delegate classify "task"` — classify work for delegation
- `./te delegate cost-check "task"` — compatibility alias for `./te cost preflight`
- `./te delegate document --verified ...` — route verified durable evidence to wiki-documenter
- `./te pa --directive "/pa <prompt>"` — route context-light personal-assistant prompts

## Wiki Layout
- `raw/` — source summaries and imported evidence
- `projects/` — active target-project state
- `L2_facts/` — verified durable facts
- `L3_sops/` — reusable workflows and runbooks
- `queries/` — durable Q&A
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
