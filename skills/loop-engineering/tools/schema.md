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

## What makes a `gate` machine-checkable (R1 allowlist)

A gate PASSES R1 only if it names at least one of:

- a command / test runner — `pytest`, `make test`, `cargo test`, `npm test`, `./check.sh`, `node run.mjs`, …
- a file the gate reads/asserts on — any `*.py *.sh *.js *.ts *.json *.yaml …` path;
- an assertion / exit / operator token — `assert`, `exit code 0`, `==`, `!=`, `$?`, `::`, `diff`, `grep`;
- an explicit marker — `regex:` / `schema:` / `cmd:` / `command:`.

This is an **allowlist**, not a prose denylist: `gate: the reviewer agrees` has no machine token and **FAILs** (the strict stance the article's "fast, deterministic, agent-runnable pass/fail signal" demands). An agent-judge gate must name the concrete check the agent runs.

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
