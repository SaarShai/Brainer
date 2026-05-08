# Extensions — external integrations and adoption notes

Token Economy core stays stdlib-first and model-agnostic. This file is a rolling log of external tools and integrations we've evaluated, what (if anything) we adopted, and what stays external.

Rules:
- Do not vendor third-party code by default.
- Install only when `./te doctor` or a benchmark shows the pain.
- Do not claim savings without local measurement.

---

## Tools already in this repo (do not re-vendor)

Wrap or reference these — don't add a new dependency that overlaps:

- **ComCom** — `projects/compound-compression-pipeline/` (compound input compression, 44.9% measured on SQuAD)
- **semdiff** — `projects/semdiff/` (AST-diff file re-reads, 95.5% measured on argparse.py)
- **context-keeper** — `projects/context-keeper/` (PreCompact memory extractor)
- **agents-triage** — `projects/agents-triage/` (UserPromptSubmit prompt classifier + subagent dispatch)
- **TurboQuant notes** — `concepts/turboquant-kv-cache.md`

---

## Adopted natively (external tool informed our own implementation)

### Omni → `./te output-filter`
Claude-specific pre/post hook output filter. We did not vendor Omni; we built an equivalent.
- Raw-output archive + rewind: `./te output-filter rewind`
- Savings stats: `./te output-filter stats`
- Custom rules: `./te output-filter rules --init`, then edit `.token-economy/output-filter-rules.txt`
- Session-aware suppression: `./te output-filter filter --session-aware` or `output_filter_session_aware: true`

Use Omni itself only when its host-specific hook integration is better than `hooks/output-filter/filter.sh`.

### context-mode → `./te context` + `hooks/output-filter`
Sandbox/cache pattern for reducing tool-output context. Token Economy equivalent: `te context`, `.token-economy/`, and `hooks/output-filter/filter.sh`. External recipe until locally measured against ours.

### token-savior → `./te profile`
Profile strategy notes. Token Economy profiles: `ultra` (default), `lean`, `nav`, `core`, `full`. Use `TOKEN_ECONOMY_PROFILE=<name>` or `./te profile set <name>`.

---

## Still external (use only when the built-in path is insufficient)

### RTK
Command-output filter for noisy shell/test/git/tree output. Reference config: `configs/rtk.config.toml`. Install from upstream, measure local reduction before enabling globally. Preserve exact error lines.

### Claude-Context
Hybrid codebase search. Use for large repos where simple `rg`, semdiff, and wiki-search are insufficient. Stays external due to vector/index service cost.

### code-review-graph
Tree-sitter / code-graph workflow for code review. Use for symbol-aware review on larger codebases. Do not replace semdiff for repeated file reads.

### QMD
Markdown/wiki search extension. Use only when wiki scale exceeds built-in SQLite FTS comfort. Built-in path remains `./te wiki search | timeline | fetch`.

### Cognee
Graph-memory extension. Use only when graph/vector memory is worth the extra service/dependency load. Core Token Economy memory tiers remain L0–L4.
