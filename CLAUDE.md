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

- `/brainer-audit` — Use when the user explicitly activates Brainer audit mode, asks to audit this session, audit Brainer use, or track Brainer skill usage
- `/task-retrospective` — Use only when the user explicitly activates task audit mode, asks for task-retrospective, says this task will repeat and should be learned from, requests an after-the-fact task learning audit, or types /retro
- `/think` — How an agent should think and approach problems — first-principles, reduce/simplify before adding, research-and-borrow before building, experiment-and-falsify, never hallucinate or flatter

### Model-invokable (host fires on matching context)

You don't need to dispatch these manually — but knowing they exist helps you
notice when context matches one (e.g. `wiki-memory` for "have we done X").

- `cache-lint` — Audit a Claude Code project for prompt-cache hygiene against Anthropic's six cache rules (ordering, dynamic-content injection, tool stability, model switching, breakpoint sizing, fork safety)
- `caveman-ultra` — Terse output style
- `compliance-canary` — Use when a long session drifts — the single always-on drift watcher: one UserPromptSubmit hook combining a periodic skill-rule re-anchor (every N turns), symptomatic per-skill drift probes (filler creep, word-count growth, unverified done-claims, self-closing without asking, looping tool errors, rule fade), and a request ledger that keeps every user request OPEN until completed or the user closes it (so nothing the user asked for is silently dropped)
- `context-keeper` — PreCompact hook that extracts structured state (files, commands, errors, numbers, decisions, failures) from the transcript before compaction
- `eval-gate` — Score AI output against a written rubric before it ships — an LLM-as-judge quality gate for content output (drafts, posts, answers) and product output (an agent's reply, an extraction, a generated payload)
- `impact-of-change` — Use before committing or claiming work done to map a code edit to its blast radius — which symbols depend on the changed ones, plus a LOW/MEDIUM/HIGH risk score
- `index-first` — Prefer pre-built indexes over chains of grep/read/scan
- `lean-execution` — Prune plans, process, context, and delegation to the smallest safe path
- `learn-skill` — Turn a pointed-at source (local dir, doc URL, a workflow you just did, or pasted notes) into a reusable Brainer skill
- `loop-engineering` — Use BEFORE building any multi-step agentic loop, generator→verifier pipeline, fan-out/fleet, or iterate-until-correct/retry loop — INCLUDING an automated / unattended / scheduled / nightly process that regenerates, revises, or rebuilds artifacts and keeps retrying each until it passes a check, any self-correcting or "keep going until it's good enough" automation, and any build-and-verify or generate-and-grade pipeline
- `output-filter` — Use when terminal output is noisy with ANSI / progress bars / duplicate lines and you want to keep the agent's eyes on signal
- `plan-first-execute` — Plan before executing non-trivial or spec-worthy tasks
- `prompt-triage` — Use on every UserPromptSubmit (pre-model hook) to classify the prompt and emit a directive telling the main model which subagent/model should handle it
- `requirements-ledger` — Use whenever the user states anything carrying intent — an ask, a question, a constraint, a preference, a compound "do X, Y, and Z" (one row per conjunct), or an implicit ask embedded in prose
- `semantic-diff` — AST-node-level diff for file re-reads
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

_Auto-generated by `./install.sh` — do not hand-edit between sentinels._
<!-- brainer:skills-catalog:end -->

