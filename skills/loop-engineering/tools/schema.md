# Loop-spec schema (`loop_lint.py` input)

A loop spec is a flat `key: value` block, read from a fenced ` ```loop ` block in any `.md` (e.g. SKILL.md / PLAN.md), a `.yaml`/`.yml` file (one spec, or several split by `---`), a `.json` file (one object or a list of objects), or `-` for stdin.

No PyYAML dependency — values are read as plain strings after the first `:`.

## Fields

| Field | Required | Meaning |
|---|---|---|
| `name` | recommended | label for the spec in lint output |
| `topology` | recommended | the shape: `open\|closed · inner\|outer · single\|fleet` (any non-letter separator). Missing → **R6 WARN** |
| `generator` | yes (closed) | the actor that produces the work |
| `verifier` | yes (closed) | the SEPARATE actor that runs the gate. `== generator` → **R3 FAIL**; empty on a closed loop → **R3 FAIL**. Must be BLIND to the generator's reasoning/code/skill content — seeing only the task + the outputs, never the generator's self-justification, since a verifier that reads it inherits the same bias even when it is a different actor. |
| `gate` | **yes** | a machine-checkable pass/fail signal. Prose with no command/test-id/assertion/path → **R1 FAIL** |
| `stop` | **yes** | the completion condition the loop runs until. Missing → **R2 FAIL** |
| `budget` | **yes** | a numeric cap (`max_iterations` / `max_tokens` / `max_wallclock`). Missing or `unbounded` → **R2 FAIL** |
| `accepted_open_loop` | open only | `true` declares "no feedback gate is intentional"; silences **R4** |
| `quorum` / `aggregate` | fleet only | the convergence gate for parallel results; absent (and no quorum/reviewer/merge token in the gate) → **R5 WARN** |
| `anchor_files` | scheduled/fleet/outer | fixed files re-read before every pass, e.g. `VISION.md`, `PROMPT.md`, `AGENTS.md`, `SKILL.md`, or the task packet. Missing on scheduled/fleet/outer loops → **R8 WARN** |
| `state_store` | scheduled/fleet/outer | durable pass state path or system, e.g. `LOOP-STATE.json`, a markdown board, or wiki-backed state. Missing on scheduled/fleet/outer loops → **R8 WARN** |
| `recall` | scheduled/fleet/outer | exact pre-pass retrieval procedure: read `state_store`, query wiki-memory, fetch timeline/pages, or load the task board. Missing on scheduled/fleet/outer loops → **R8 WARN** |
| `writeback` | scheduled/fleet/outer | exact post-pass persistence procedure: record attempts, verifier verdict, failures, next action, and changed facts. Missing on scheduled/fleet/outer loops → **R8 WARN** |
| `state_concurrency` | fleet with state | one of `single_writer`, `optimistic_revision`, or `worktree_isolated`. Missing/invalid on fleet specs with `state_store` → **R9 WARN** |
| `output_actions` | unattended + side-effecting | the allowlist of world-mutating actions the loop MAY take (`post-comment`, `close-issue`, `add-label`, `merge`, `email`, …), each ideally with a per-action cap (`close-issue max 5`). Required once an unattended loop names a side-effecting action; missing → **R10 WARN**; a value of `*`/`all` is not an allowlist → **R10 WARN** |
| `stuck` | fix loops | the stuck detector that fires the escalation, e.g. `same command 3×`, `same error 2×`, `2 iters no movement`. Declaring it opts the loop into **R11**: a stuck policy with no `advisor` warns. |
| `advisor` | on `stuck` | the DIVERGENT panel consulted when stuck — a preferably cross-vendor, read-only set of models that propose structurally-different approaches/tools/methods and feed the **generator** (never the gate). Source it from [`skills/_shared/model_roster.py`](../../_shared/model_roster.py). `== verifier` → **R11 WARN** (propose-and-judge is self-grading). |
| `redaction` | cross-vendor egress | what is scrubbed from the prompt before repo-derived content leaves the host for a third-party model (secrets / `.env` / keys / PII). Required once `advisor`/`verifier`/`egress` names a cross-vendor panel; missing → **R12 WARN (R12a)**. The scrub is *enforced* in [`model_roster.py`](../../_shared/model_roster.py) `render_prompt`; this field makes the data surface declarable + auditable. |
| `consent` | unattended + egress | the gate that authorizes the first cross-vendor egress on an UNATTENDED loop (no human present to approve at runtime). Missing on a scheduled/fleet/outer/long-running loop that egresses → **R12 WARN (R12b)**. Enforced at the tool: `model_roster --run` refuses without `--consent` / `MODEL_ROSTER_EGRESS_CONSENT=1`. |
| `egress` | optional | an explicit cross-vendor-egress declaration (alternative trigger for **R12** when the panel is not named in `advisor`/`verifier`). |
| `verifier_blind` | LLM verifier on unattended/cross-vendor loop | `true` declares the verifier sees only the task + the outputs, never the generator's reasoning; `false` declares it is NOT blind → **R13 WARN**. Absent on such a loop → **R13 WARN** (unless the `verifier` string says "fresh context"/"blind"). |
| `verifier_inputs` | alternative to `verifier_blind` | what the verifier is fed, e.g. `task, outputs`. A value naming the generator's `reasoning`/`rationale`/`chain-of-thought` → **R13 WARN**; a clean value (task + outputs) satisfies R13. |

**R7 IRREVERSIBLE-NO-HUMAN (WARN):** if `stop` / `gate` / `generator` names an irreversible action (deploy / merge to main / migrate / `rm -rf` / force-push / charge / refund / rotate secret / npm publish) and there is **no human in the loop** (no approve/sign-off/escalate gate, no human-token verifier) → WARN. Silence it by giving a human approval gate or a human verifier.

**R8 NO-MEMORY-CONTRACT (WARN):** if a loop is scheduled/event-triggered, fleet-shaped, or outer-loop-shaped, it must say what survives the context window: `anchor_files`, `state_store`, `recall`, and `writeback`. This is advisory for v1 so small inner fix loops stay lightweight, but a long-running loop without these fields is expected to re-derive, repeat work, or drift.

**R9 FLEET-STATE-NO-CONCURRENCY (WARN):** if a fleet has a `state_store`, it must also name `state_concurrency`. Use `single_writer` when only the orchestrator writes state, `optimistic_revision` when workers read a revision/hash and retry on conflict, and `worktree_isolated` when each worker writes isolated state that only merges through aggregation.

**R10 OUTPUT-SURFACE-UNBOUNDED (WARN):** if a loop is unattended (scheduled / event-triggered / outer / fleet / long-running) AND names a side-effecting world action (post / comment / close / label / merge / commit / push / open-PR / create-issue / delete / email / publish / deploy / charge / refund) in `generator` / `stop` / `gate`, it must declare an `output_actions` allowlist: the actions it MAY take, each with a per-action cap, **default-deny, enforced by the harness rather than asked for in the prompt.** Missing → WARN; an allowlist of `*` / `all` is not a control and still WARNs. This **inverts** R7's catastrophic-verb blocklist: R7 stops deploy/merge/charge without a human; R10 stops the *mundane-but-unbounded* case — a moderation bot that can `close`/`label`/`comment` at scale because nothing capped it. Silence it by enumerating capped actions. Scoped to unattended loops only — a watched inner loop's human IS the output gate, so it never fires there. Ported from GitHub Agentic Workflows `safe-outputs:` (`allowed:` actions + `max:` per action).

**R11 STUCK-NO-ADVISOR (WARN):** two distinct triggers, both about the multi-model escalation a stalled loop should make:
1. A spec that declares a `stuck` policy but names no `advisor` — the stuck agent retries harder against its own blind spot instead of consulting a fresh perspective. Silence it by naming an `advisor` panel sourced from [`skills/_shared/model_roster.py`](../../_shared/model_roster.py) (cross-vendor, read-only, fired on the stuck condition).
2. An `advisor` that resolves to the same actor as the `verifier`. The advisor is **divergent** (proposes new approaches/tools/methods, feeds the generator); the verifier is **convergent** (judges pass/fail, IS the gate). One actor doing both judges a fix it proposed — self-grading by another door, the same hole R3 closes for generator/verifier. Keep them separate vendors; `model_roster.pick_panel(exclude_lane=…)` drops the orchestrator's own lane so the panel is genuinely independent. Opt-in: R11 stays silent until `stuck` (trigger 1) or `advisor` (trigger 2) is declared, so plain inner fix loops are never nagged.

**R12 CROSS-VENDOR-EGRESS (WARN):** the moment a loop's `advisor`/`verifier` panel sends repo-derived content to a third-party model (cross-vendor / `model_roster` / OpenRouter / Fusion / codex / gemini / glm / z.ai / an "external panel"), two privacy controls are expected — borrowed from [ksimback/looper](https://github.com/ksimback/looper)'s privacy layer, generalized from glob lists to secret-shape detection:
1. **R12a — `redaction`:** name what is scrubbed before egress. The scrub is *enforced* in [`model_roster.py`](../../_shared/model_roster.py) `render_prompt` (every copy-paste dispatch and `--run` funnels through it, reusing [`audit_redact.py`](../../_shared/audit_redact.py)); the field makes the surface auditable in the spec.
2. **R12b — `consent`:** only for UNATTENDED loops (scheduled/fleet/outer/long-running), where no human approves the first send at runtime. Enforced at the tool: `model_roster --run` refuses egress without `--consent` / `MODEL_ROSTER_EGRESS_CONSENT=1`.

R12 fires only when an egress signal is actually present, so a same-host / local-only loop is never nagged. Related: a VERIFIER panel's quorum is recomputed *after* dispatch by `model_roster.verifier_quorum` (R11b) — a 1-member or even panel is a weak gate (`which != usable` drops members), not a passed gate.

**R13 VERIFIER-BLINDNESS (WARN):** a separate verifier is necessary but not sufficient — it must also be **blind** to the generator's reasoning/self-justification, or it inherits the same bias even as a different actor (the deepest form of "design the verifier"). This is a **declare-to-audit** field, not a static proof (a flat text spec cannot prove information isolation) — exactly the shape of R12's `redaction`. It fires only when (a) the `verifier` is an LLM/agent actor (a machine gate like `pytest` is blind by construction) **and** (b) blindness matters — the loop is unattended (scheduled/fleet/outer/long-running) **or** the verifier is a cross-vendor panel. Then: an undeclared blindness surface → WARN; `verifier_blind: false` or a `verifier_inputs` that includes the generator's reasoning → WARN. Silence it by declaring `verifier_blind: true`, setting `verifier_inputs: task, outputs`, or naming a "fresh context"/"blind" verifier. Opt-in scope (like R8/R10/R11/R12) keeps plain inner fix loops unnagged. R13 closes the asymmetry where egress/concurrency/memory each had a declarable field but the blind-verifier rule — the skill's deepest — had none.

## What makes a `gate` machine-checkable (R1 allowlist)

A gate PASSES R1 only if it names at least one of:

- a command / test runner — `pytest`, `make test`, `cargo test`, `npm test`, `./check.sh`, `node run.mjs`, …
- a **command-anchored** code file — a path after `./`, an absolute path, or a runner (`pytest tests/x.py`). A bare `config.py` dropped mid-prose does **not** count;
- an assertion against a **code-like operand** — `exit_code == 0`, `status == pass`, `assert`, `exit code 0`, `$?`, `::`, `diff`, `grep`. A bare `==` between two prose words (`tone == the CEO's voice`) does **not** count;
- an explicit marker — `regex:` / `schema:` / `cmd:` / `command:`;
- a **human decision** — an explicit approve / sign-off / escalate / select / pick / decide / confirm by a **human** actor (`Saar approves`, `owner sign-off`, `the user picks`). The article endorses "a handoff to a human with the run data attached." An **autonomous agent** "approving" by feel (`the reviewer agent approves`) is **not** a gate — it is the LLM-judge hole R1 refuses; name the concrete check the agent runs.

This is an **allowlist**, not a prose denylist: `gate: the reviewer agrees` / `gate: looks correct` name no real check and **FAIL** (the strict stance the article's "fast, deterministic, agent-runnable pass/fail signal" demands).

`budget` must bind a number to a cap unit — `max_iterations=20`, `max_tokens: 100000`, `20 turns`, `30m`. A stray digit in prose (`run until inbox has 0 unread`) is **unbounded** and FAILs R2.

## Visualize a spec (`--diagram`)

`loop_lint.py --diagram <file>` emits a Mermaid generator→gate→verifier loop for each spec, **derived from the parsed fields** (never invented), with the lint findings overlaid: the indicted node is coloured (R1 → the gate, R3 → generator + verifier, R2 → stop + budget, R6 → topology) and every finding is listed in a `lint findings` subgraph. A clean spec shows a single green `OK` node. Exit code stays the lint verdict (2/1/0), so `--diagram` is still a CI gate. Wrap the output in a ` ```mermaid ` fence to render it in GitHub / Obsidian / VS Code.

## Freeze a snapshot (`--resolve`)

`loop_lint.py --resolve <file>` emits an **immutable audit snapshot** (`loop.resolved` JSON) of each spec: normalized fields + the lint verdict at freeze time, flagged `unattended: true/false`. Borrowed from looper's `loop.resolved.json` but deliberately narrowed — it is a **replay/drift surface** ("rerun the exact spec we verified last Tuesday"), **NOT a resume checkpoint**: it carries no run state and no runner, so `loop_lint` stays a linter, not an orchestrator. It earns its keep for outer/fleet/scheduled loops; inner loops get a snapshot too but flagged `unattended:false`. Exit code stays the lint verdict, so `--resolve` composes in CI.

## Example (passes clean)

```loop
name: zig-to-rust-port
topology: closed · inner · fleet
generator: opus port agent (one per file)
verifier: sonnet reviewer agents, 2 per file, + refuter panel
gate: cargo build && cargo test --quiet
stop: build clean and ≥99.8% of the existing suite green
budget: max_iterations=40
quorum: 2 reviewers agree + refuter finds nothing
anchor_files: SPEC.md, AGENTS.md, skills/loop-engineering/SKILL.md
state_store: work/LOOP-STATE.json
recall: read state_store and wiki-memory timeline before each pass
writeback: record attempts, verifier verdict, failures, next action after each pass
state_concurrency: worktree_isolated
```

## A non-iterating pipeline is a budget=1 loop

A fixed once-through pipeline (A→B→C, each stage runs once, nothing retries) is **not a separate artifact** — it is a closed loop with `budget: max_iterations=1`. Give it a machine `gate` and a `verifier` separate from each stage's producer and it lints clean — no `stages:`/`edges:` keys, no second tool. The moment a stage loops back to retry an earlier one it is a real loop: raise the budget.

```loop
name: import-pipeline
topology: closed · inner · single
generator: import + transform stages
verifier: validate stage + final schema check (separate actor)
gate: python3 ./validate.py && python3 ./check_schema.py out.json
stop: out.json written and passes the schema check
budget: max_iterations=1
```

## Example (fails: R1 + R2 + R3)

```loop
name: vibe-loop
topology: open · inner · single
generator: claude
verifier: claude
gate: looks correct
stop: when it feels done
```

- R1 FAIL — `gate: looks correct` has no machine-checkable signal.
- R2 FAIL — no `budget` cap (and `stop` is not measurable).
- R3 FAIL — `generator == verifier` (self-grading).
- R4 WARN — open loop without `accepted_open_loop: true`.
