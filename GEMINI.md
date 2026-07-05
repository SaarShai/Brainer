# Brainer

Skills catalog: see [`skills/SKILLS_INDEX.md`](skills/SKILLS_INDEX.md).

Each skill loads on its own trigger; full bodies are not in the boot context. Run `./install.sh` to wire skills into the current host.

<!-- brainer:skills-catalog:start -->
## Repo-local trigger skills (resident at boot)

Skill bodies under `skills/<name>/` lazy-load on trigger. The names + 1-line
descriptions below are kept in this resident doc so a freshly booted (or
post-compaction) agent still knows what's available — so a model-invokable
trigger (e.g. `wiki-memory` for "have we done X") is recognised on sight
rather than re-derived from scratch.

### Slash-triggered (user types literally; model cannot auto-invoke)

These are literal text tokens you recognise yourself — NOT host-registered
commands. When the user's message starts with one of these tokens, load
`skills/<name>/SKILL.md` and follow it yourself, even if this host has no such
command installed (e.g. Codex, Antigravity) or shows an "unknown command"
error. Treat the rest of the message as the task. Don't improvise a hand-rolled
equivalent:

- `/baton` — Drop/grab a verified session-handoff file — pass in-progress work to the next agent (future session, another window, codex) via .brainer/baton/
- `/brainer-audit` — Use when the user explicitly activates Brainer audit mode, asks to audit this session, audit Brainer use, or track Brainer skill usage
- `/task-retrospective` — Use only when the user explicitly arms task audit mode: /retro, asks for task-retrospective, says this task will repeat and should be learned from, or requests an after-the-fact task learning audit
- `/think` — How an agent should think and approach problems — first-principles, reduce/simplify before adding, research-and-borrow before building, experiment-and-falsify, never hallucinate or flatter

### Model-invokable (host fires on matching context)

You don't need to dispatch these manually — but knowing they exist helps you
notice when context matches one (e.g. `wiki-memory` for "have we done X").

- `cache-lint` — Audit a Claude Code project for prompt-cache hygiene against Anthropic's six cache rules (ordering, dynamic-content injection, tool stability, model switching, breakpoint sizing, fork safety), plus a rule-7 tool-surface audit (resident-but-unused MCP servers)
- `caveman-ultra` — Terse output style
- `compliance-canary` — Use when a long session drifts — the single always-on drift watcher: one UserPromptSubmit hook combining symptomatic per-skill drift probes (filler creep, verbosity growth, unverified done-claims, looping tool errors), a periodic skill-rule re-anchor, and a request ledger that keeps every user request OPEN until completed or user-closed
- `context-keeper` — PreCompact hook that extracts structured state (files, commands, errors, numbers, decisions, failures) from the transcript before compaction, so the summarizer can't silently drop facts; a SessionEnd hook also archives the raw transcript to .brainer/sessions/raw/ (git-ignored)
- `eval-gate` — Score AI output against a written rubric before it ships — an LLM-as-judge quality gate for content output (drafts, posts, answers) and product output (an agent's reply, an extraction, a generated payload)
- `impact-of-change` — Use before committing or claiming work done to map a code edit to its blast radius — which symbols depend on the changed ones, plus a LOW/MEDIUM/HIGH risk score
- `index-first` — Prefer pre-built indexes over chains of grep/read/scan
- `lean-execution` — Prune plans, process, context, and delegation to the smallest safe path
- `learn-skill` — Turn a pointed-at source (local dir, doc URL, a workflow you just did, or pasted notes) into a reusable Brainer skill
- `loop-engineering` — Use BEFORE building any multi-step agentic loop, generator→verifier pipeline, fan-out/fleet, or iterate-until-correct/retry loop — including any unattended / scheduled / nightly process that regenerates artifacts and retries until a check passes, and any build-and-verify or generate-and-grade pipeline
- `output-filter` — Use when terminal output is noisy with ANSI / progress bars / duplicate lines and you want to keep the agent's eyes on signal
- `plan-first-execute` — Plan before executing non-trivial or spec-worthy tasks
- `prompt-triage` — Use on every UserPromptSubmit (pre-model hook) to classify the prompt and emit a directive telling the main model which subagent/model should handle it
- `propagate` — Use when the user asks to propagate, sync, roll out, or push Brainer skill changes to the sibling/consumer repos (screenery-lean, product images repo, farey-hecke, PROMPTER, …) after work in the canonical Brainer repo
- `requirements-ledger` — Use whenever the user states anything carrying intent — an ask, a question, a constraint, a preference, a compound "do X, Y, and Z" (one row per conjunct), or an implicit ask embedded in prose
- `security-oversight` — Use before committing or claiming work done to triage a code edit for INTRODUCED security risk — leaked secrets, dangerous sinks, untrusted deps, risky auth logic
- `semantic-diff` — AST-node-level diff for file re-reads
- `team-lead` — Use when the user says lead, orchestrate, use your team, use builders — or marks a task important/challenging while the session model is ANY top-tier frontier model (Fable-class, Opus-class, GPT-5.x/Codex, or peer)
- `verify-before-completion` — Use before claiming work is done, fixed, passing, committed, or ready
- `wiki-memory` — Repo-local markdown wiki with progressive retrieval (search → timeline → fetch) and gated writes (verified facts only)
- `wiki-refresh` — Reconcile wiki-memory pages against the current codebase — Keep / Update / Consolidate / Replace / Delete drifted ones
- `write-gate` — Decide whether a candidate fact deserves persistent memory

### Durable memory store (`wiki/`)

This repo carries a curated knowledge store at `wiki/` — the *why/decision/
failure-lesson* layer (rationale, trade-offs, incidents, procedures), distinct
from auto-extracted code structure. Relevant when the task references past work,
prior decisions, or "have we done X". Query it before re-deriving: read
`wiki/L1_index.md` first, then `python3 skills/wiki-memory/tools/wiki.py search "<q>"`
→ `timeline` → `fetch`. Maintained by `wiki-memory` (write) and `wiki-refresh`
(reconcile vs code).

### Code-craft directives (resident at boot)

Always-on rules for writing code — they apply on every coding turn, not only when
a skill happens to trigger:

- **Surgical diffs.** Smallest reversible change; touch only what the ask needs;
  match local style; never reformat code you didn't change. Justify every changed
  line by the task — revert "while I was in there" edits. (`lean-execution` covers
  this when invoked; this is the always-on copy. The `whitespace_only_edit` +
  `dependency-manifest-changed` `compliance-canary` probes enforce it mechanically.)
- **Failure-mode interrupt.** If mid-task you slide into scope-creep (Kitchen
  Sink), premature abstraction (abstract only on the 3rd repeat — rule of three),
  happy-path-only (error path ignored), or a fix cascading across files (Runaway
  Refactor) — STOP, restate the goal, narrow scope.

### Host capability matrix (honest degradation)

- **claude-code** — full: hooks (PreCompact/SessionEnd/UserPromptSubmit/SessionStart) + Agent-tool subagents (builder/verifier lanes).
- **codex** — hooks ported via `.codex/hooks.json` (compaction checkpoint, session archive, canary); NO Agent tool → team-lead lanes go through CLI dispatch (team-lead §2 fallback).
- **gemini** — hooks migrated via `gemini hooks migrate` into `.gemini/settings.json` (PreCompress checkpoint, SessionEnd archive, BeforeAgent canary/triage); verify on first live session.
- **cursor** — NO session-lifecycle hooks: no canary, no compaction checkpoint. Re-read the pulse rules at each phase boundary yourself and drop a `/baton` before ending long work.
- Any host: skills are text-portable; tools are plain python3/bash. If a rule references a hook this host lacks, the RULE still binds — you enforce it manually.

_Auto-generated by `./install.sh` — do not hand-edit between sentinels._
<!-- brainer:skills-catalog:end -->

