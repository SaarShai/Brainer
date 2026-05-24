# Inspiration & References

Repos and writeups that shaped this catalog or live in adjacent territory. Grouped by what they do, not by how directly they influenced us. Where a skill in this repo descends from one of these, the link is called out.

## Direct lineage (existing skills)

- [colbymchenry/codegraph](https://github.com/colbymchenry/codegraph) — pre-indexed code graph (tree-sitter + SQLite + MCP). Lineage for [`index-first`](skills/index-first/SKILL.md).
- [JuliusBrussee/caveman](https://github.com/JuliusBrussee/caveman) — terse output style. Lineage for [`caveman-ultra`](skills/caveman-ultra/SKILL.md).
- [mattpocock/skills](https://github.com/mattpocock/skills) — slash-command skill format. Lineage for [`handoff`](skills/handoff/SKILL.md).
- [karpathy/LLM-wiki gist](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f) — LLM-maintained markdown wiki as a compounding knowledge base. Lineage for [`wiki-memory`](skills/wiki-memory/SKILL.md).
- [forrestchang/andrej-karpathy-skills](https://github.com/forrestchang/andrej-karpathy-skills) — CLAUDE.md packaging of Karpathy's "think before coding / surgical changes / goal-driven loop" principles. Adjacent to [`plan-first-execute`](skills/plan-first-execute/SKILL.md) and [`lean-execution`](skills/lean-execution/SKILL.md).

## Code indexing / structural retrieval

- [safishamsi/graphify](https://github.com/safishamsi/graphify) — tree-sitter AST graph + Leiden communities + Obsidian export, packaged as a multi-host skill (Claude Code / Codex / Cursor / Gemini / Aider / OpenCode / …). Closest concrete realization of Karpathy's "LLM-maintained knowledge base" idea, applied to codebases. Recognized by [`index-first`](skills/index-first/SKILL.md) when `graphify-out/graph.json` is present; measured −93% tokens vs grep+read at parity evidence rate (12-Q A/B) using `graphify explain`. See [`skills/index-first/EVAL.md`](skills/index-first/EVAL.md) for full numbers + known issues.
- [zilliztech/claude-context](https://github.com/zilliztech/claude-context) — MCP semantic code search; hybrid BM25 + dense vector across whole codebases.
- [tirth8205/code-review-graph](https://github.com/tirth8205/code-review-graph) — tree-sitter graph + blast-radius traversal for code review (claims 8.2× token reduction).
- [Mibayy/token-savior](https://github.com/Mibayy/token-savior) — MCP: structural code index + memory + bash compactor.

## Output / context filters (wrap the agent's pipes)

- [danveloper/flash-moe](https://github.com/danveloper/flash-moe) — unrelated to token economy directly; C/Metal inference engine for 397B MoE on a 48GB MacBook. Included because the streaming-from-SSD trick is the same shape as "stream from index on disk instead of loading into context."
- [mksglu/context-mode](https://github.com/mksglu/context-mode) — MCP that sandboxes tool output, tracks session via SQLite, claims 98% raw-data reduction.
- [fajarhide/omni](https://github.com/fajarhide/omni) — smart terminal filter between agent and shell output (~90% token cut on noisy logs). Adjacent to [`output-filter`](skills/output-filter/SKILL.md).
- [mvanhorn/cli-printing-press](https://github.com/mvanhorn/cli-printing-press) — generates "agent-native" CLIs (auto-JSON when piped, typed exit codes, `--compact`, `--dry-run`).
- [mvanhorn/printing-press-library](https://github.com/mvanhorn/printing-press-library) — companion library to the above.
- [rtk-ai/rtk](https://github.com/rtk-ai/rtk) — CLI proxy that filters/compresses common dev-command output before it reaches the agent (claims 60-90% reduction).

## Memory & knowledge systems

- [topoteretes/cognee](https://github.com/topoteretes/cognee) — open-source "memory control plane" for agents; unified ingest + retrieval.
- [microsoft/memento](https://github.com/microsoft/memento) — reasoning-extension technique: blockwise CoT with summaries, evict from KV cache while preserving key info.
- [thedotmack/claude-mem](https://github.com/thedotmack/claude-mem) — SQLite + Chroma persistent memory across Claude Code sessions; auto-injects past observations.
- [breferrari/obsidian-mind](https://github.com/breferrari/obsidian-mind) — Obsidian vault template as durable agent memory.
- [rarce/git-wiki](https://github.com/rarce/git-wiki) — self-maintaining knowledge repo in your git repo; hybrid on-device search.
- [rohitg00 gist](https://gist.github.com/rohitg00/2067ab416f7bbe447c1977edaaa681e2) — extends Karpathy's wiki pattern with lifecycle (confidence, supersession, decay), typed-relationship graphs, BM25+vector+graph hybrid retrieval.

## Token-optimizer projects (overlapping pitches; click through for specifics)

- [ooples/token-optimizer-mcp](https://github.com/ooples/token-optimizer-mcp) — MCP combining caching + compression + tool intelligence; claims 95%+ reduction.
- [nadimtuhin/claude-token-optimizer](https://github.com/nadimtuhin/claude-token-optimizer)
- [alexgreensh/token-optimizer](https://github.com/alexgreensh/token-optimizer)
- [drona23/claude-token-efficient](https://github.com/drona23/claude-token-efficient)

## Agent frameworks / skill collections

- [garrytan/gstack](https://github.com/garrytan/gstack) — Claude Code as a 23-role virtual engineering team (CEO / designer / QA lead / release engineer / …) with enforced planning-building-reviewing-testing-shipping workflow.
- [crewaiinc/crewai](https://github.com/crewaiinc/crewai) — multi-agent orchestration framework (role-based crews, tasks, processes).
- [lsdefine/GenericAgent](https://github.com/lsdefine/GenericAgent) — minimal self-evolving agent (~3k LOC core, 9 atomic tools, ~100-line loop) for system-level local control.
- [ray-amjad/claude-code-workflow-creator](https://github.com/ray-amjad/claude-code-workflow-creator) — meta-skill that authors **workflow scripts** (JavaScript files) for Claude Code's unreleased `Workflow` tool (gated behind `CLAUDE_CODE_WORKFLOWS=1`). Deterministic multi-agent orchestration: `agent()`/`parallel()`/`pipeline()`/`phase()` as plain JS, only leaf `agent()` calls spend tokens, each in its own fresh-context window. Ships an api-reference, a 6-pattern playbook (fan-out, pipeline, barrier-dedup, loop-until-budget, judge panel, nested workflow), runnable examples, and a validator script. Adjacent to our dropped [`delegate`](README.md) skill — when the Workflow tool ships, our [`eval/combos/`](eval/combos/) YAMLs (caveman+lean, triage+caveman+keeper, etc.) could be re-expressed as workflow files for end-users who want a specific stack deployed deterministically.

## Drift mitigation (loop/goal/spec)

- [google-gemini/gemini-cli](https://github.com/google-gemini/gemini-cli) `loopDetectionService.ts` — production loop detector: identical tool-call ≥ 5× or identical sentence ≥ 10× triggers halt + recovery. Lineage for [`loop-breaker`](skills/loop-breaker/SKILL.md).
- [anthropics/claude-code#4277](https://github.com/anthropics/claude-code/issues/4277) — open feature request: no first-party loop detection in Claude Code. Documents the gap [`loop-breaker`](skills/loop-breaker/SKILL.md) fills.
- [othmanadi/planning-with-files](https://github.com/othmanadi/planning-with-files) — 3-file plan/findings/progress pattern with PreToolUse plan re-reads. Candidate lineage for a future `plan-anchor` skill (held; design questions on re-injection cadence vs. noise).
- [itsuzef/goalkeeper](https://github.com/itsuzef/goalkeeper) — fresh subagent judges work against a written Definition of Done after validator passes. Adjacent to [`verify-before-completion`](skills/verify-before-completion/SKILL.md) but DoD-driven rather than test-driven.
- [fiberplane/drift](https://github.com/fiberplane/drift) — tree-sitter AST anchors bind markdown blocks to source symbols + `@<git-sha>`; `drift check` fails CI on spec↔code divergence. Candidate for a future `spec-anchor` thin wrapper.
- [rohitg00/pro-workflow](https://github.com/rohitg00/pro-workflow) — converts user corrections into FTS5-indexed rules auto-injected at SessionStart so the same failure doesn't recur next session. Cross-session counterpart to [`loop-breaker`](skills/loop-breaker/SKILL.md)'s in-session detection.
- [rulebricks/claude-code-guardrails](https://github.com/rulebricks/claude-code-guardrails) — PreToolUse rule engine blocking fabricated/dangerous commands. Adjacent shape to [`loop-breaker`](skills/loop-breaker/SKILL.md) but rule-based rather than pattern-based.
- arXiv [2601.04170](https://arxiv.org/abs/2601.04170) "Agent Drift" — taxonomy (semantic/coordination/behavioral) + Agent Stability Index across 12 dimensions. Background; ASI itself doesn't fit a slash-skill (needs cross-session telemetry).

## Compliance decay / instruction adherence

Skill-rules fading from effective attention as sessions grow. Distinct from loop drift (above) — this is about *prose and tool-choice style* slipping away from rules established earlier.

- [Cline Focus Chain](https://docs.cline.bot/features/focus-chain) — closest production analog: re-injects the todo list every 6 messages. **Pulses todos, not skill rules.** User backlash on UX: [#5763](https://github.com/cline/cline/issues/5763) "Focus Chain is terrible and just breaks stuff", [#6105](https://github.com/cline/cline/issues/6105), [#5638](https://github.com/cline/cline/issues/5638). Lesson taken: stale pulse content is worse than no pulse — pulse stable things (rules), not volatile things (todos). Lineage for [`skill-pulse`](skills/skill-pulse/SKILL.md).
- [Cursor `alwaysApply: true`](https://forum.cursor.com/t/alwaysapply-true-rules-are-being-completely-ignored-now/158551) — every-prompt re-injection mechanism. Widely reported to fail in long sessions ([85458](https://forum.cursor.com/t/always-rules-intermittently-fail-in-long-sessions-in-cursor-49-6/85458), [157484](https://forum.cursor.com/t/alwaysapply-silently-ignored-in-rules-from-team-plugins/157484)). v0 baseline; lesson: same-text-every-time loses salience.
- [anthropics/claude-code#22421](https://github.com/anthropics/claude-code/issues/22421) — closed-not-planned feature request for "Periodic Directive Refresh." Reporter observed ~50% compliance by tool call 40, near-zero by 60. Documents the gap [`skill-pulse`](skills/skill-pulse/SKILL.md) fills.
- [delta-hq/cc-canary](https://github.com/delta-hq/cc-canary) (65★) — forensic / offline drift detector that scores JSONL session logs (read:edit ratios, reasoning-loop phrases, premature-stop). **Post-hoc only, no intervention.** Direct lineage for [`compliance-canary`](skills/compliance-canary/SKILL.md), which moves the same idea into the running session via UserPromptSubmit and adds per-skill `drift_probes.json` declarations.
- [umputun/570c77f8…](https://gist.github.com/umputun/570c77f8d5f3ab621498e1449d2b98b6) / [claudefa.st Skill Activation Hook](https://claudefa.st/blog/tools/hooks/skill-activation-hook) — UserPromptSubmit preamble injecting "evaluate → activate → implement." Fires once per prompt; addresses cold-start skill loading, **not** session-decay.
- [johnlindquist/23fac87f…](https://gist.github.com/johnlindquist/23fac87f6bc589ddf354582837ec4ecc) — every-N-prompts UserPromptSubmit hook refreshing the tools list. Same pulse shape as `skill-pulse` but pulses tool inventory instead of skill rules.
- [DoubleNode/claude-context-tick](https://github.com/DoubleNode/claude-context-tick) — state-gated UserPromptSubmit injection (timestamp on session-start / 15-min boundaries). Pattern (conditional injection) transfers; payload doesn't.
- [Michaelliv/pi-system-reminders](https://github.com/Michaelliv/pi-system-reminders) — reactive system-reminders SDK with 13 ported examples from Claude Code internals (bash-spiral, token-warn, post-compact). No periodic skill-decay reminder ships.
- [michaellivs.com — System reminders teardown](https://michaellivs.com/blog/system-reminders-steering-agents/) — best explainer of Anthropic's internal reactive reminder pattern.
- arXiv [2510.07777 — "Drift No More?"](https://arxiv.org/html/2510.07777) — **empirical basis for `skill-pulse`.** Tests reminder injections at turns 4 + 7 of 10-turn convos; KL divergence drops 6.45–11.81%; judge scores +0.5–0.6 (5-pt scale). Drift stabilizes at a noise-limited equilibrium, not a fixed plateau; pulses lower that equilibrium. Does NOT test cadence sweeps, format variations, or rotated phrasings.
- arXiv [2411.07037 — LIFBench](https://arxiv.org/abs/2411.07037) — benchmark for instruction-following stability across context length.
- arXiv [2402.10962](https://arxiv.org/abs/2402.10962) — significant drift within 8 rounds on Llama2-70B / GPT-3.5.
- arXiv [2512.10172 — Offscript](https://arxiv.org/abs/2512.10172) — auditor LLM identifies adherence failures in 86.4% of conversations (22.2% material). Judge / auditor pattern.

## Prompt engineering & background reading

- [EgoAlpha/prompt-in-context-learning](https://github.com/EgoAlpha/prompt-in-context-learning) — curated resource hub: papers, playgrounds, prompt-engineering techniques, real-world prompts. Useful as a survey, not as a tool.

---

If you spot something missing, open a PR adding a row.
