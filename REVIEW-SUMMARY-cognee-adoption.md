# Review packet — cognee adoption review + cbm re-audit

**For:** an independent reviewing agent. **Status:** committed `c616708`, pushed to
`github.com/SaarShai/Brainer` main. **Your job:** challenge the conclusions below.
Every claim cites evidence you can re-check. Attack the reasoning, not just the code.

---

## 0. How to verify (do this first)

- **Re-run the gate:** `bash scripts/run_all_tests.sh --quiet` → expect `85/85 PASS`.
- **The one code change:** `git show c616708 -- skills/impact-of-change/tools/impact.py`
- **Source repos reviewed** (heavy frameworks; read, not adopted wholesale).
  External public repos — NOT part of Brainer's repo. The `file:line` citations
  below are against these **exact revisions** (both repos move; clone the pinned
  SHA or line numbers will drift):
  - cognee — https://github.com/topoteretes/cognee @ `1913271821c84cec1630dd5b15ceb17dee8ace55`
    (`git clone https://github.com/topoteretes/cognee && git -C cognee checkout 1913271`)
  - cbm (codebase-memory-mcp) — https://github.com/DeusData/codebase-memory-mcp @ `b075f0506ce4286219edd1bc3dccb196f2ed7cb0`
    (`git clone https://github.com/DeusData/codebase-memory-mcp && git -C codebase-memory-mcp checkout b075f05`)
- **What is NOT in the Brainer online repo:** (1) this summary file (untracked —
  you are holding it directly); (2) the session ledger (`.brainer/` is gitignored;
  its content is in §10); (3) the cognee/cbm sources above (their own repos, pin as
  shown). Everything else cited (`skills/…`, `wiki/…`, `scripts/…`) is at Brainer
  commit `c616708` on `github.com/SaarShai/Brainer` main.
- **Brainer = the adoption target:** lightweight, offline-first, repo-local skills
  library for coding agents. Philosophy: "gate over prose" — machine-checkable
  gates + file-state over LLM dialogue. No vector DB, no graph DB server, no
  mandatory LLM calls. Memory = curated markdown in `wiki/` + small Python tools.

---

## 1. What was asked, in order

1. Review cognee the same way a prior session reviewed cbm: adversarially,
   independently, with **GLM-5.2 cross-check**; list what to adopt.
2. Challenge: *"when you conclude 'already covered', are you checking in-depth
   whether the reference does it better?"*
3. Apply the same in-depth re-check to **everything adopted before cognee** (cbm).
4. Have GLM-5.2 review the conclusions and collaborate; then do **(a)** cbm reject
   re-audit, **(b)** bank the method-rule + verdict to the wiki, **(c)** build the
   inheritance-edge delta — in order. Commit + push.

---

## 2. Method (how every verdict was reached)

- **Independent + adversarial + cross-model.** For each candidate, read *both*
  sides' actual code head-to-head. A reviewing agent (general-purpose) or GLM-5.2
  was dispatched to form an independent verdict and, where relevant, to *refute*
  mine (default-to-disagree, file:line required or disqualified).
- **The standard "covered" must meet** (the method-rule this review produced):
  a "we already cover this / reject — covered" verdict is a *quality claim*. It
  must cite the **specific Brainer consumer `file:line`** that exercises the exact
  capability — not merely an adjacent tool that exists. See
  `wiki/concepts/adoption-covered-needs-merits-citation.md`.
- **Two reject classes, only one needs the deep read:**
  - *categorical-axiom* (needs infra Brainer rejects — vector/graph DB, LSP engine,
    RDF) → safe to reject on scope.
  - *similarity-asserted* ("a Brainer skill covers it") → a quality claim; needs
    the merits citation.

---

## 3. Cognee review — verdict

cognee is an AI-memory platform (ECL pipelines, graph+vector hybrid, eval
framework, session distillation, feedback loops). Almost all of it is the infra
Brainer rejects by design. After head-to-head reads + GLM cross-check:

| Candidate (cognee) | Verdict | Evidence |
|---|---|---|
| **Per-criterion rubric scoring** (`eval_framework/evaluation/metrics/rubric.py` — judge each criterion independently YES/NO → fraction) | **ADOPT — HIGH. NOT YET BUILT.** | Brainer `eval-gate` scores *holistically* (one `0-5` digit + reason: `skills/eval-gate/tools/eval_gate.py:62,78-80`). Per-criterion = a FAIL names *which* criterion failed (actionable). Top cognee-specific adopt; **still open.** |
| **Use/feedback reinforcement** (`tasks/memify/apply_feedback_weights.py` — EMA `w+α·(rating−w)` + frequency) | NARROW — measure-first | Brainer already has frequency (`wiki.py _bump_usage`) + reuse→trust promotion (`consolidate`, capped: verified never by popularity) + decay + contradiction (`resolve`). Only missing half: a *negative* "retrieved-but-wrong" signal. Don't build speculatively. |
| Session→lesson distillation (`modules/session_distillation/distill.py`) | covered | Brainer `task-retrospective`→`write-gate`→`wiki` gates on deterministic novelty (`overlap`) + trust-tiered conflict (`resolve`). cognee's only distinct edge = *unattended* harvest — a deliberate Brainer anti-bloat choice, not a gap. |
| Temporal / bi-temporal intervals (`tasks/temporal_awareness/*`) | **concede (not "covered")** | cognee genuinely better, but needs a graph DB + LLM extraction. Out-of-scope, not covered. |
| Dedup, retriever-router, hybrid retrieval, code-graph extractor, DataPoint registry, task-batching, agent decorator, user scoping, LLM retry, eval-adapter | covered / reject | covered by `overlap`/`consolidate`, `index-first`, `graphify`+`impact-of-change`, `eval-gate` backends; or reinvent existing / need rejected infra. |
| Vector DB · graph DB/Cypher · RDF/ontology · OTEL/cloud · DLT/alembic | categorical reject | infra Brainer rejects by design. |

---

## 4. The pivotal correction (challenge #2 → #3)

The challenge exposed a real method failure. **"Covered by graphify" was asserted
from a catalog-line name-match, not a head-to-head of emitted-vs-consumed
relations.** Verified facts:

- graphify's `graph.json` emits relations **`{contains, method, inherits, calls}`**
  (tool-verified: `graphify update` on a `Base`/`Child` hierarchy produced
  `child -inherits-> base`).
- `impact-of-change` built its dependent index from **`CALL_RELATIONS = {"calls"}`
  only** (`impact.py:37`, `:217` pre-change) — it **discarded the `inherits`
  edges already in the graph**. A base-class change never reached its subclasses.
- The **same miss sat undetected in the prior cbm review** — cbm emits `"INHERITS"`
  / `"EXTENDS"` edge constants (`internal/cbm/extract_defs.c`, verified ×2 each).

So a shallow "covered" silently dropped a real, cheap, in-philosophy improvement.

---

## 5. cbm reject re-audit (step a) — GLM cross-verified

| cbm capability | Verdict |
|---|---|
| Inheritance / subclass blast-radius (`INHERITS`/`EXTENDS` edges + `trace_path` across hierarchies) | **(b) offline-adoptable — real miss → built in step (c)** |
| Cross-module type resolution (Hybrid-LSP, `README.md:492` — resolves `a.b.c()` across modules; tree-sitter can't) | **(c) categorical concede** — needs the C LSP engine |
| Dead-code (zero-callers) | (a) covered — `impact.py:289` logic present, just unpackaged |
| Multi-relation graph queries / Cypher-lite (`query_graph`) | (b) adoptable but **defer** (YAGNI; inheritance is the valuable instance) |
| Cross-service HTTP route↔call-site linking | (b) adoptable but **defer** (niche for Brainer) |
| C engine · SQLite graph · openCypher executor | categorical reject (infra) |

**GLM's notable catch (refined, didn't break):** `INHERITS` is listed at cbm
`README.md:163` ("Edge types — *selected*") but omitted from the authoritative
schema list at `README.md:408`. The README is stale; the **C source proves
emission**. The Brainer delta never depended on cbm anyway — it rests on
graphify, tool-proven.

---

## 6. IMPLEMENTED this session (step c) — the only code shipped

**`impact-of-change` now consumes the `inherits` edges it was discarding.**
Commit `c616708`. Files:

- `skills/impact-of-change/tools/impact.py`:
  - `INHERIT_RELATIONS = {"inherits"}`; `DEP_RELATIONS = CALL_RELATIONS | INHERIT_RELATIONS`.
  - `build_indexes` builds inbound adjacency from `DEP_RELATIONS`, storing
    `(source_id, relation)` per edge.
  - `callers_of` reverse-BFS over both relations; each dependent carries
    `via ∈ {"subclass","caller"}`. A changed base class now reaches its subclasses
    (depth-1 subclass) and their callers (transitive).
- `skills/impact-of-change/tools/test_impact.py`: new **E5** — `Base ← Child`
  (`via=subclass`, d1) + `use()` calls `Child` (`via=caller`, d2); guard that the
  old `calls`-only code returned zero dependents for a base class.

**Verification:**
- `bash scripts/run_all_tests.sh` → **85/85 PASS** (E1–E4 regression-free).
- GLM-5.2 **adversarial diff-review = SHIP**: 7 constructed attacks survive
  (self-cycle, mutual cycle, mixed transitivity, ambiguous `via`, 15-subclass risk
  scoring, degraded-mode), 0 bugs.

---

## 7. BANKED to wiki (step b)

- **NEW** `wiki/concepts/adoption-covered-needs-merits-citation.md` — the durable
  method-rule (covered ⇒ cite the consumer file:line; check emitted-vs-consumed;
  distinguish categorical vs similarity rejects). Reusable for every future
  adoption review.
- **UPDATED** `wiki/concepts/framework-hardening-adoption.md` — matrix row 12
  (cognee verdict + re-audit correction).
- GLM reviewed both → flagged 2 over-claims ("never propagated" read as graphify's
  fault; "stronger" unbacked) → both reframed. Wiki lint clean.

---

## 8. Open items the reviewer should weigh (NOT built)

1. **A1 — per-criterion rubric mode for `eval-gate`** (HIGH). The top
   cognee-specific in-philosophy adopt; concluded worth doing, **not yet built**.
   Should it be built next?
2. **B1 — negative "retrieved-but-wrong" feedback for wiki-memory** (narrow).
   Recommended *measure-first* (don't add a subjective quality weight against
   Brainer's evidence-over-popularity stance until drift data justifies it).
3. **cbm defers** — Cypher-lite multi-relation query; HTTP route↔call linking.
   Real but low-value/niche for Brainer's use case.
4. **Conceded (need infra Brainer rejects)** — bi-temporal intervals; Hybrid-LSP
   cross-module type resolution. Honest out-of-scope, not "covered."

---

## 9. How to challenge this (falsification targets)

- **Is the inheritance delta correct blast-radius, or a false positive?** A
  subclass depends on its base's interface; reverse-`inherits` from base → subclass
  is sound. Attack: construct a graph where it over-reaches.
- **Did I wrongly mark something "covered"?** Re-run the head-to-head: cite a
  cognee/cbm capability + the Brainer consumer `file:line` that supposedly covers
  it, and check emitted-vs-consumed.
- **Is "concede" hiding a lightweight offline form?** Especially temporal: is there
  a markdown-native bi-temporal form I conceded too fast?
- **Did GLM over-credit / under-credit?** I overrode GLM's dedup "gap" (it's
  cognee-ingestion-specific, N/A to Brainer's no-embedding stack). Re-check that.
- **Known limits (by design):** degraded grep mode can't see inheritance (lexical);
  `via` is first-arrival-wins under multiple paths (informational, not load-bearing);
  graphify must emit `inherits` (it does — but a graph built without it degrades to
  calls-only, same as before).

---

## 10. Collaboration trail (GLM-5.2)

- Independent cognee review (over-proposed 14; weak overlap filter — folded only
  what survived a merits check).
- Refuted my corrected cognee verdicts (agreed on inheritance/temporal/session-
  distill; its dedup "gap" I rejected with reason).
- Independent cbm re-audit + the `README:408` schema catch.
- Reviewed the wiki writes → 2 over-claim fixes.
- Adversarial diff-review of the code → SHIP, 0 bugs.

Ledger: `.brainer/ledger/37dbc809-3700-477b-8e18-593c021ea700.md` (rows R10–R13).
