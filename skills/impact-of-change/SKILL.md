---
name: impact-of-change
description: "Use before committing or claiming work done to map a code edit to its blast radius — which symbols depend on the changed ones, plus a LOW/MEDIUM/HIGH risk score. Trigger on \"what breaks if I change this?\", \"who calls this function?\", \"what's the impact of this edit?\", \"is this change safe to ship?\", or as the pre-commit gate in a generate→verify loop. Parses `git diff` for changed symbols, queries graphify's CALLS edges for inbound dependents (depth<=3), and degrades to a labelled lexical grep when graphify is absent. Does NOT run tests or modify code — it tells verify-before-completion WHAT to verify. Forward impact only (no dead-symbol detection). Also: /impact-of-change."
status: proposed
effort: low
tools: [Bash, Read]
auto-install: false
disable-model-invocation: false
pulse_reminder: "before closing a task with edits, run impact.py — emit the blast radius (changed symbols → dependents → risk) so verify-before-completion knows which high-risk zones to test. Graph-precise when graphify is present; degraded/unverified grep otherwise — say which."
---

# impact-of-change

Answer **"what breaks if I change this?"** before a commit or a done-claim. Map
uncommitted edits (or a commit range) to their **blast radius**: which symbols
depend on the changed symbols, and a **risk score** (LOW/MEDIUM/HIGH) from
caller breadth plus how far the call chain reaches. It is graph-based
*planning*, not testing — it hands the high-risk list to
`verify-before-completion`, which runs the fresh tests.

Born **opt-in / untrusted** (`auto-install: false`, `status: proposed`): wire it
deliberately, promote after it has earned trust on real diffs.

## When to use

- Before editing or pre-commit: "what's the impact of changing X?", "are there
  callers of this function I should know about?", "is this safe to ship?"
- Composed with **semantic-diff**: semdiff says *which symbols changed*; this
  skill says *who depends on them*.
- Composed with **verify-before-completion**: emit the blast radius first, so the
  user verifies the high-risk zones (this skill never runs tests).
- Composed with **loop-engineering**: gate the "is the change safe enough to
  integrate?" decision in a generate→verify loop.

Do **not** use it as a linter (no style/quality checks), a formatter, a full
reachability analyzer (depth-bounded; answers "who calls me", not "who
transitively depends"), or a test runner.

## Protocol

1. Ensure a git working tree is present and (for precision) the graph is built:
   `graphify extract . --backend ollama` → `graphify-out/graph.json`
   (see [index-first](../index-first/SKILL.md) for the graphify recipe + staleness rule).
2. Run the analyzer:
   ```bash
   # uncommitted edits, markdown report
   python3 skills/impact-of-change/tools/impact.py --repo . --diff working
   # a specific commit, JSON for piping
   python3 skills/impact-of-change/tools/impact.py --diff <sha> --json
   # a range, deeper chain
   python3 skills/impact-of-change/tools/impact.py --diff main..HEAD --depth 3
   ```
3. Read the report: **Summary** (X changed, Y callers, risk=…), **Changed
   symbols**, **Affected symbols** (dependents + per-symbol risk), **Critical
   paths**, **Recommendations**.
4. Route the HIGH/MEDIUM symbols to `verify-before-completion` to run their
   tests. Surface ambiguity to the user; don't silently pick.

## How it scores risk

Per the spec thresholds, each changed symbol is scored from its inbound callers:

- **LOW** — ≤2 direct callers, all in tests/deprecated paths (or no callers).
- **MEDIUM** — 3–10 direct callers, or any indirect caller at depth ≥2.
- **HIGH** — >10 direct callers, OR a caller in an entry/critical path
  (`main`/`cli`/`api`/`app`/`handler`/`route`/…), OR a transitive chain at depth ≥3.

Overall report risk is the max across changed symbols.

## Degraded mode (graphify absent)

If `graphify-out/graph.json` is missing (or fails to load), the skill **does not
error or block**. It falls back to a **single-pass lexical grep** for each
changed symbol name (`\bname\s*\(` across tracked `.py`), marks every hit
`unverified`, and labels the whole report **DEGRADED-MODE** with a warning to run
`graphify extract`. Risk in this mode is coarse (lexical hit count only).

If the graph is present but **older than HEAD**, the report still runs but emits a
non-blocking **DRIFT** warning to refresh (`graphify update . --force`, or
re-extract after renames/deletes).

## Scope decisions (resolved)

- **Dead-symbol detection: out of scope** — forward impact only (who depends on
  the change), not backward garbage collection of newly-orphaned symbols.
- **Degraded depth: single lexical pass**, all hits unverified.
- **Staleness: a WARNING, not a blocker.**

## Output

Structured `dict` (→ JSON with `--json`, or markdown by default). Top-level keys:
`mode` (`graph`|`degraded`), `risk`, `summary`, `changed_symbols`, `affected`
(each: `symbol`, `risk`, `caller_count`, `max_depth`, `callers`, `files`,
`risk_reason`), `recommendations`, `warnings`. Parseable by downstream skills.

## Files

```
tools/
├── impact.py        # git diff → changed symbols → graphify CALLS edges → risk
└── test_impact.py   # standalone E1–E4 probes (assert + exit 1), temp-git fixture
```

## Tests

```bash
python3 skills/impact-of-change/tools/test_impact.py
```

Covers the spec's four probes: **E1** precision (changed leaf fn → dependents
match ground truth), **E2** degradation (graphify absent → grep report +
warning, never errors), **E3** risk (LOW private helper vs HIGH >10 callers),
**E4** structure (output is parseable JSON with the documented shape). The graph
path is driven by a fixture `graph.json` mirroring graphify's node-link shape;
the degrade path needs no graphify.
