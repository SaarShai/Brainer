# Brainer

Skills catalog: see [`skills/SKILLS_INDEX.md`](skills/SKILLS_INDEX.md).

Each skill loads on its own trigger; full bodies are not in the boot context. Run `./install.sh` to wire skills into the current host.

## Project goals (why Brainer exists — weigh every change against these)

The Brainer skills exist to, in any project they are installed in:

1. **Optimize token-use efficiency** — less context spent for the same outcome.
2. **Maximize agent efficiency and reliability** — faster, correct, verifiable work.
3. **Facilitate learning and self-improvement** — lessons captured once, reused everywhere.
4. **Manage memory and the wiki** — durable, curated, retrievable project knowledge.
5. **Operationalize loops** — recurring/multi-session work runs without hand-holding.
6. **Provide instructions, suggestions, mindsets and thinking guidelines** to any agent working in the host project.

A change that adds machinery without clearly serving one of these — or that costs
more tokens/complexity than it saves — is out of scope. Prefer removing over adding.

<!-- brainer:skills-catalog:start -->
## Repo-local trigger skills (resident at boot)

Skill bodies under `skills/<name>/` lazy-load on trigger; the 1-line
descriptions below stay resident so a freshly booted (or post-compaction)
agent still recognises a trigger on sight instead of re-deriving it.

### Slash-triggered (user types literally; model cannot auto-invoke)

Literal tokens you recognise yourself — NOT host-registered commands. If the
user's message starts with one, load `skills/<name>/SKILL.md` and follow it
yourself even if this host has no such command (e.g. Codex, Antigravity) or
shows "unknown command". Treat the rest of the message as the task; don't
improvise a hand-rolled equivalent:

- `/baton` — Drop/grab a verified session-handoff file — pass in-progress work to the next agent (future session, another window, codex) via .brainer/baton/
- `/brainer-audit` — Use when the user explicitly activates Brainer audit mode, asks to audit this session, audit Brainer use, or track Brainer skill usage
- `/brainer` — Use when the user explicitly says `/brainer` or asks to use any relevant Brainer skill: inspect the optional-method reference, select the smallest task-relevant set, and apply only exported methods or complete skill contracts as declared
- `/caveman-ultra` — Experimental/manual terse-output style retained for paired evaluation
- `/fable-mode` — Experimental/manual five-gate work discipline retained for paired evaluation
- `/lean-execution` — Experimental/manual lean-work protocol retained for paired evaluation
- `/learn-skill` — Experimental/manual skill-learning workflow retained for paired evaluation
- `/loop-engineering` — Experimental/manual loop-design workflow retained for paired evaluation
- `/plan-first-execute` — Experimental/manual planning protocol retained for paired evaluation
- `/prompt-triage` — Experimental manual router for paired evaluation
- `/requirements-ledger` — Experimental/manual visible requirements-ledger workflow retained for paired evaluation
- `/self-improvement-loops` — Govern loops that optimize their own agent machinery.
- `/standing-orders` — Experimental standing-directive probes retained for shadow telemetry and paired evaluation
- `/task-retrospective` — Use only when the user explicitly arms task audit mode: /retro, asks for task-retrospective, says this task will repeat and should be learned from, or requests an after-the-fact task learning audit
- `/team-lead` — Experimental/manual orchestration protocol retained for paired evaluation
- `/think` — How an agent should think and approach problems — first-principles, reduce/simplify before adding, research-and-borrow before building, experiment-and-falsify, never hallucinate or flatter
- `/verify-before-completion` — Experimental/manual FULL verification workflow retained for paired evaluation
- `/wayfinder` — Experimental/manual decision-recovery workflow retained for paired evaluation

### Model-invokable (host fires on matching context)

No manual dispatch needed — but knowing these exist helps you notice a
context match (e.g. `wiki-memory` for "have we done X").

- `cache-lint` — Audit a Claude Code project for prompt-cache hygiene against Anthropic's six cache rules (ordering, dynamic-content injection, tool stability, model switching, breakpoint sizing, fork safety), plus a rule-7 tool-surface audit (resident-but-unused MCP servers)
- `compliance-canary` — Use when a long session may drift or needs verification-compliance monitoring
- `context-keeper` — PreCompact hook that extracts structured state (files, commands, errors, numbers, decisions, failures) from the transcript before compaction, so the summarizer can't silently drop facts; a SessionEnd hook also archives the raw transcript to .brainer/sessions/raw/ (git-ignored)
- `eval-gate` — Score AI output against a written rubric before it ships — an LLM-as-judge quality gate for content output (drafts, posts, answers) and product output (an agent's reply, an extraction, a generated payload)
- `impact-of-change` — Use before committing or claiming work done to map a code edit to its blast radius — which symbols depend on the changed ones, plus a LOW/MEDIUM/HIGH/UNKNOWN risk score
- `index-first` — Prefer pre-built indexes over chains of grep/read/scan
- `output-filter` — Use when terminal output is noisy with ANSI / progress bars / duplicate lines and you want to keep the agent's eyes on signal
- `propagate` — Use when the user asks to propagate, sync, roll out, or push Brainer skill changes to the sibling/consumer repos (screenery-lean, product images repo, farey-hecke, PROMPTER, …) after work in the canonical Brainer repo, or asks to harvest lessons, reap lessons, or bring learnings back from a sibling
- `security-oversight` — Use before committing or claiming work done to triage a code edit for INTRODUCED security risk — leaked secrets, dangerous sinks, untrusted deps, risky auth logic
- `semantic-diff` — AST-node-level diff for file re-reads
- `wiki-memory` — Repo-local markdown wiki with progressive retrieval (search → timeline → fetch) and gated writes (verified facts only)
- `wiki-refresh` — Reconcile wiki-memory pages against the current codebase — Keep / Update / Consolidate / Replace / Delete drifted ones
- `write-gate` — Decide whether a candidate fact deserves persistent memory

### Durable memory store (`wiki/`)

Curated why/decision/failure-lesson layer at `wiki/`. Query before re-deriving
(e.g. "have we done X"): read `wiki/L1_index.md`, then
`python3 skills/wiki-memory/tools/wiki.py search "<q>"` → `timeline` → `fetch`.
Maintained by `wiki-memory` (write) / `wiki-refresh` (reconcile vs code).

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
  happy-path-only (error path ignored), a fix cascading across files (Runaway
  Refactor), or building what an existing tool already provides (Reinvented
  Wheel — STOP, run a borrow check) — STOP, restate the goal, narrow scope.
- **Borrow first.** Before building machinery, name the existing tool checked
  and why it fails; otherwise the brief is malformed. Deep: `/think`.
- **Frontier ownership.** Top-tier agents own the end-to-end goal and hard
  judgment. Run independent, gated work concurrently on the cheapest reliable
  lanes; retain direct work only when no suitable lane is reachable or the
  explicit ~<30-line judgment-dense exception applies.
  Continue, correct, synthesize, and verify until done; stop only for missing
  authority or a real blocker. Full contract: `skills/_shared/ORCHESTRATION.md`
  §6.
- **Task routing.** Before root/child mutation, receipt: artifacts,
  SPEC'D/GATED, size, authority, route, owner, exception. Project/AGENTS.md
  authority beats generic default; speed never waives required routes.
  Delegate SPEC'D+GATED >~30-line work; frontier owns unresolved diagnosis.
  Late receipt: stop, re-route rest, cold-review early edits.

### Host capability matrix (honest degradation)

Host capability & degradation matrix (claude/codex/gemini): see
`docs/HOST_CAPABILITY_MATRIX.md` — the RULE still binds on a host lacking a
hook; enforce it manually.

_Auto-generated by `./install.sh` — do not hand-edit between sentinels._
<!-- brainer:skills-catalog:end -->
