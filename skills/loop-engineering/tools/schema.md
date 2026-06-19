# Loop-spec schema (`loop_lint.py` input)

A loop spec is a flat `key: value` block. Three accepted carriers:

- a fenced ` ```loop … ``` ` block inside any `.md` (SKILL.md / PLAN.md);
- a standalone `.yaml` / `.yml` file (one spec, or several split by `---`);
- a `.json` file (one object, or a list of objects);
- `-` to read a spec from stdin.

No PyYAML dependency — values are read as plain strings after the first `:`.

## Fields

| Field | Required | Meaning |
|---|---|---|
| `name` | recommended | label for the spec in lint output |
| `topology` | recommended | the shape: `open\|closed · inner\|outer · single\|fleet` (any non-letter separator). Missing → **R6 WARN** |
| `generator` | yes (closed) | the actor that produces the work |
| `verifier` | yes (closed) | the SEPARATE actor that runs the gate. `== generator` → **R3 FAIL**; empty on a closed loop → **R3 FAIL** |
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

**R7 IRREVERSIBLE-NO-HUMAN (WARN):** if `stop` / `gate` / `generator` names an irreversible action (deploy / merge to main / migrate / `rm -rf` / force-push / charge / refund / rotate secret / npm publish) and there is **no human in the loop** (no approve/sign-off/escalate gate, no human-token verifier) → WARN. Silence it by giving a human approval gate or a human verifier — the security tax: an unattended loop is an unattended attack surface.

**R8 NO-MEMORY-CONTRACT (WARN):** if a loop is scheduled/event-triggered, fleet-shaped, or outer-loop-shaped, it must say what survives the context window: `anchor_files`, `state_store`, `recall`, and `writeback`. This is advisory for v1 so small inner fix loops stay lightweight, but a long-running loop without these fields is expected to re-derive, repeat work, or drift.

**R9 FLEET-STATE-NO-CONCURRENCY (WARN):** if a fleet has a `state_store`, it must also name `state_concurrency`. Use `single_writer` when only the orchestrator writes state, `optimistic_revision` when workers read a revision/hash and retry on conflict, and `worktree_isolated` when each worker writes isolated state that only merges through aggregation.

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
