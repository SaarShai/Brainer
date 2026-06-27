# Skill Spec: `impact-of-change`

## WHAT / WHY

**User-visible outcome:** When a user edits code (locally uncommitted, or a proposed change), the skill maps those edits to their **blast radius** — which symbols in the codebase depend on the changed symbols, plus a **risk classification** (low/medium/high) based on the breadth and depth of the dependency chain.

**Scope:** Answer "what breaks if I change this?" before the user commits or claims work is done. Emits a structured report of affected symbols, callsites, and test coverage, so the user can either:
1. Run targeted re-verification on high-risk dependents.
2. Decide whether a broader test suite is needed.
3. Understand propagation risk for a refactor/rename.

**Non-goals:**
- Not a linter (does not check code quality or style).
- Not a formatter (does not suggest rewrites).
- Not a full reachability analyzer (depth bounded; answers "who calls me" not "who transitively depends").
- Does not execute or run tests (verify-before-completion does that).

**Assumptions:**
- The codebase has been indexed by `graphify` (command: `graphify extract . --backend ollama`), producing `graphify-out/graph.json`.
- A git working tree is present; `git diff` (uncommitted) or `git show <commit>` (committed) are available.
- The indexer is fresh enough that symbol names match the current AST (staleness rule from `index-first/SKILL.md` applies).

**Dependencies:**
- **graphify** (`graphify-out/graph.json`): the skill queries the call graph to resolve inbound edges (who calls the changed symbols).
- **git**: to extract the diff.
- **semantic-diff** (optional, complementary): `semantic-diff` produces AST diffs; this skill consumes *which symbols changed* and routes to graphify.
- **verify-before-completion**: after this skill reports a blast radius, the user should verify the high-risk zones (this skill does not run tests).

---

## TRIGGER / WHEN-TO-USE

**Model-invokable** (host wires a hook, or agent recognizes context):

1. **Before editing or after editing, pre-commit:** user asks "what's the impact of changing X?" or "are there callers of this function I should know about?"
2. **Composed with verify-before-completion:** before closing a task with edits, emit the blast radius so the user can decide how deeply to verify.
3. **Composed with semantic-diff:** `semantic-diff` identifies which symbols changed; this skill enriches that with "who depends on these symbols."
4. **Composed with loop-engineering:** in a multi-pass generator-verifier loop, this skill gates the "is the change safe enough to integrate?" decision.

**Interaction with other skills:**
- Does **not** replace `semantic-diff` (which is AST-level re-read optimization; this is impact/risk).
- Does **not** replace `verify-before-completion` (which runs fresh tests; this is *graph-based planning*).
- **Complements** both: "here's what changed (semdiff) + here's who depends on it (impact-of-change) + here's what to test (impact-of-change's high-risk list) → run verify-before-completion on those critical paths."

---

## TESTABLE REQUIREMENTS

1. **Git diff parsing:** Skill correctly extracts symbols (functions, methods, classes) that differ between two commits or in the working tree.

2. **Graph traversal:** Skill queries graphify's `CALLS` edges (and `MEMBER_OF` / `IMPLEMENTS` where applicable) to resolve inbound callers of changed symbols, depth ≤3 (default; configurable).

3. **Risk classification:** Each affected symbol is scored as one of:
   - **LOW**: ≤2 direct callers, all in tests or deprecated code paths.
   - **MEDIUM**: 3–10 direct callers, or 1+ indirect callers at depth 2.
   - **HIGH**: >10 direct callers, or callers in entry points / critical paths, or transitive depth ≥3 to user-facing surfaces.

4. **Graceful degradation (graphify absent):** If `graphify-out/graph.json` does not exist or is stale:
   - Skill falls back to a grep-based "best effort" (search codebase for lexical references to changed symbol names).
   - Returns a **degraded-mode** report with a clear warning ("impact estimated without graph; run `graphify extract .` for precision").
   - Does **not** error out or block the user.

5. **Output format:** Returns a structured markdown report containing:
   - Summary: "X symbols changed, Y affected callers, risk level = HIGH"
   - Changed symbols (table: symbol name, file, change type [added/deleted/modified]).
   - Affected symbols (table: symbol name, caller count, depth, files affected, risk score).
   - Critical paths (list of high-risk caller chains if depth ≤2).
   - Recommendations ("run tests on X", "check entry point Y", "this is a public API — verify backward-compat").

---

## ACCEPTANCE / SUCCESS CRITERIA

**Done means:**

1. ✓ Skill identifies all changed symbols in a git diff (functions, methods, classes).
2. ✓ For each changed symbol, skill emits a list of direct inbound callers from the graph.
3. ✓ Each affected caller is scored on risk (LOW/MEDIUM/HIGH) with a justification.
4. ✓ If graphify is absent, skill falls back gracefully with a clear warning.
5. ✓ Output is actionable: user can read the report and decide which test suite to run, or which code review comment to add.
6. ✓ Skill composes cleanly with `verify-before-completion` (user reads impact report, then runs verify).
7. ✓ Skill does **not** run tests, modify code, or make decisions on behalf of the user.
8. ✓ Round-trip time for a modest change (~5 symbols) is <5 seconds (graph is pre-indexed, no reindex on each call).

---

## TEST-DESIGN

### Test Harness

**Fixture repo:** `test_fixture/impact_repo/`
- Hand-authored Python codebase (~30 functions, 4 modules) with known call edges.
- Pre-indexed with graphify (committed `graphify-out/graph.json`).
- Two variants (committed side-by-side):
  - `scenario_1/`: change a leaf function, assert dependents match ground truth.
  - `scenario_2/`: rename a public API, assert both old and new are flagged, risk = HIGH.
  - `scenario_3/`: add a function (no dependents yet), assert empty impact list, risk = LOW.

### E1 Probe (Precision)

1. **Ground-truth setup:** manually annotate expected dependents for each scenario.
2. **Run impact-of-change:** on each scenario's diff.
3. **Assertion:** affected symbol list matches ground truth.
4. **Edge case:** verify renamed symbols are detected as [deleted old + added new], not conflated.

### E2 Behavior (Degradation & Gracefulness)

1. **Graphify-absent case:** delete `graphify-out/graph.json`, re-run impact-of-change.
2. **Assertion:** skill returns `degraded-mode` report with grep-based best-effort AND a clear warning message.
3. **Assertion:** user can still act on the report (lexical references are listed, even if not graph-precise).

### E3 Risk Classification (Judgment)

1. **High-risk anchor:** manually create a scenario where a changed function is called by 15 entry-point handlers.
2. **Assertion:** skill classifies as `HIGH`, suggests full test suite coverage.
3. **Low-risk anchor:** change a private helper function with 1 internal caller.
4. **Assertion:** skill classifies as `LOW`, suggests unit test sufficiency.

### E4 Integration (Composition)

1. Run `semantic-diff` on a changed file, capture changed symbols.
2. Feed those symbols into `impact-of-change`.
3. **Assertion:** output is well-structured and actionable to a user reading it before `verify-before-completion`.

### Regression Test Suite

- After each feature addition, re-run E1–E4 on the fixture repo.
- CI gate: skill must pass all four probes before merge.

---

## OPEN QUESTIONS

[NEEDS CLARIFICATION: Should the skill also detect **dead symbols** created by a change (e.g., if you rename a function and miss one callsite, the old function becomes dead)? Or is that out-of-scope and belong in a separate linter? Current assumption: dead code detection is NOT in scope here — focus is forward impact, not backward garbage collection.]

[NEEDS CLARIFICATION: When graphify is absent, how deep should the grep-based fallback go? Current assumption: single pass, lexical search for symbol names; regex-based call detection (heuristic `\bsymbol_name\s*\(`) to reduce false positives, but mark all hits as "unverified".]

[NEEDS CLARIFICATION: Should the skill emit a suggestion to run `graphify update` if the graph is older than the last N commits? Current assumption: yes — a drift warning, but not a blocker.]

---

## IMPLEMENTATION SKETCH (non-binding)

**Invocation:** `/impact-of-change` or `impact_of_change(diff="<git_sha_range_or_working>", depth=3)`.

**Algorithm outline:**

1. Parse `git diff` (or `git show`) to extract changed symbols (use tree-sitter + the same parser as `semantic-diff`).
2. For each changed symbol `S`, query graphify:
   ```
   graphify query "(caller)-[:CALLS]->(S)"
   ```
3. For each returned caller, repeat at depth-1 (recursive, bounded by `depth=3`).
4. Accumulate all paths; score each by degree and entry-point proximity.
5. Format markdown report.
6. If graphify fails, fall back to grep + emit degraded-mode warning.

**Output:** markdown report to stdout, optionally written to `.brainer/impact_<commit_hash>.md`.

---

## RELATED SKILLS / PRIOR ART

- **codebase-memory-mcp `detect_changes`**: the direct inspiration. Maps git diff to affected symbols + risk classification. This spec operationalizes that idea within Brainer's architecture (graphify as the graph, lexical fallback, composition with verify-before-completion).
- **semantic-diff**: identifies *which symbols changed* in a file; this skill enriches that with *who depends on them*.
- **verify-before-completion**: runs tests on the changed code; this skill helps the user decide *which* tests are critical (the high-risk list).
- **index-first**: a guiding principle — prefer structured queries over grep; this skill is an application of that principle to change impact analysis.

---

## ACCEPTANCE GATE

Before moving from spec → prototype:

- [ ] User confirms the three [NEEDS CLARIFICATION] questions (or states them as irrelevant).
- [ ] Fixture repo is set up with 3+ scenarios and ground-truth annotations.
- [ ] Test harness (E1–E4) is runnable in CI.
- [ ] Graphify is confirmed as the canonical graph source (no alternative graph layer proposed).
