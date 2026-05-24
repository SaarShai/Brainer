# EVAL — `index-first`

## Static cost (pending measurement)

Will be filled in by `eval/runner.py` once a task set is authored. Expected static cost: small (description-only resident, body loads on trigger).

## A/B savings (pending)

**Hypothesis:** On tasks that involve tracing references, finding callers, or reading multiple related files/docs, this skill should reduce tool-call count and output tokens versus a baseline that lets the agent grep-and-read freely.

**Reference numbers from upstream (codegraph repo, not our measurement):** ~35% cheaper, ~59% fewer tokens, ~70% fewer tool calls, ~49% faster across 7 real codebases. Gains scale with corpus size; small repos show narrower margins because native search is already cheap.

A direct A/B requires an index actually being installed (e.g., codegraph + MCP) in both arms. Without that, the skill has nothing to redirect to and the test degenerates.

## Methodology

- Sample size: N=3-10 local smoke; N≥50 on Kaggle T4 for any >20% savings claim.
- Tasks: TBD in `eval/tasks/index-first.yaml`. Should pair grep-heavy exploration prompts ("trace all callers of X", "find every route that maps to handler Y") across small / medium / large corpora.
- Backends: ollama / anthropic / mimo.

## Failure modes (anticipated)

- **Over-trigger on indexless corpora**: skill body loads, no index exists, agent burns context for no payoff. Mitigation: explicit "check first, fall back" step in protocol.
- **Stale-index trust**: if the index hasn't synced and the agent doesn't verify, results will mislead. Mitigation: caveat in skill body.
- **Confidence-score blindness**: agent picks top result even when it's low-confidence. Mitigation: explicit step in protocol + anti-pattern bullet.

---

## External tool: graphify (measured 2026-05-23, graphifyy 0.8.17)

[graphify](https://github.com/safishamsi/graphify) builds an AST-based code graph (`graphify-out/graph.json`) plus optional Leiden community clusters. We measured it as a candidate index for this skill's "composite verb over chained primitives" pattern. Headline: when an agent asks symbol-precision questions and graphify is present, **`graphify explain` matches grep+read on evidence at -93% tokens** in our 12-question A/B on this repo's `skills/`. The integration ships in [SKILL.md](SKILL.md) as a recipe — no new skill folder.

### Retrieval A/B (n=12 questions on token-economy `skills/`, code-only graph)

Harness: [`eval/runner_graphify.py`](../../eval/runner_graphify.py). All token counts are char/4 heuristic; "evidence rate" = fraction of questions whose output contained ≥1 expected keyword.

| Arm | Tokens | Tool calls | Evidence | Δ tokens vs grep |
|---|---|---|---|---|
| grep+read baseline (3 files × 200 lines) | 27,790 | 33 | 91.7% | — |
| `graphify query "<NL question>"` | 7,977 | 12 | 50.0% | **−71.3%** |
| `graphify explain "<NodeLabel>"` | 1,826 | 12 | **91.7%** | **−93.4%** |

**Verdict**: `explain` is the dominant verb for symbol questions — same answer quality, ~15× cheaper. `query` (the natural-language one) is much weaker — its NL→start-node resolver picks generic matches over the obvious symbol; only use it for concept exploration where no symbol is named.

### Build-cost curve (code-only extract, single-shot with clustering)

Harness: [`eval/runner_graphify_costcurve.py`](../../eval/runner_graphify_costcurve.py).

| Repo | Code files | Source | Wall time | Nodes | Edges | Communities | Graph size |
|---|---|---|---|---|---|---|---|
| small (token-economy `skills/`) | 83 | 207MB* | 17.3s | 507 | 810 | 58 | 0.4MB |
| medium (flask) | 84 | 0.6MB | **1.6s** | 1,195 | 1,793 | 128 | 0.9MB |
| large (django) | 3,023 | 21MB | 57.9s | 41,373 | 127,537 | 2,694 | **55.7MB** |

\* small includes a venv leftover in the source tree; graphify still only processed 83 code files.

Scaling: roughly linear in code-file count. Cost is **near-zero** for typical project sizes (<1k files). Large monorepos (~3k files) build in under a minute; graph file becomes large enough (~50MB) that the agent should never read it raw, only query through the CLI.

### Quality probes

Harness: [`eval/runner_graphify_quality.py`](../../eval/runner_graphify_quality.py). Corpus: token-economy `skills/`.

- **Edge precision** (30 random EXTRACTED edges checked against ±5-line window in the cited source): **29/30 = 96.7%**. The single miss is a structural `contains` edge on an entry-node placeholder, not a code-claim defect. Real precision on code-claim edges is effectively 100% in this sample.
- **Path soundness** (3 curated paths): 3/3 returned a valid path; 2/3 within expected hop bound. The third returned a shorter path than expected — a graphify shortcut via a `method` edge that's correct but skips an intermediate. Not a bug, but worth noting the hop count isn't a stable property.
- **Staleness behavior (the alarm finding)**: renamed `def read_page` → `def read_page_RENAMED`, ran `graphify update . --force`. After update, **`graphify explain ".read_page()"` still succeeds** AND `.read_page_RENAMED()` also succeeds. `update` is **additive only** — it never removes nodes. Stale labels accumulate across refactors.

### Combo: graphify + wiki-memory (n=12 questions across code/project/hybrid kinds)

Harness: [`eval/runner_graphify_combo.py`](../../eval/runner_graphify_combo.py). Tests whether agents should hit one store or both for mixed *what + why* questions.

| Subset (n) | Arm | Tokens | Tool calls | Evidence |
|---|---|---|---|---|
| **ALL (12)** | grep baseline | 26,959 | 34 | 75% |
|  | wiki alone | 1,985 | 12 | 75% |
|  | graphify alone | **1,504** | 12 | 91.7% |
|  | **combo (graphify + wiki)** | 3,527 | 24 | **100%** |
| code (4) | grep | 12,644 | 14 | 100% |
|  | wiki | 640 | 4 | 25% |
|  | **graphify** | 676 | 4 | **100%** |
|  | combo | 1,328 | 8 | 100% |
| project (6) | grep | 8,995 | 13 | 50% |
|  | **wiki** | 970 | 6 | **100%** |
|  | graphify | 351 | 6 | 83% |
|  | combo | 1,341 | 12 | 100% |
| hybrid (2) | grep | 5,320 | 7 | 100% |
|  | wiki | 375 | 2 | 100% |
|  | graphify | 477 | 2 | 100% |
|  | combo | 858 | 4 | 100% |

**Interpretation:**
- The combo arm gets **100% evidence at −87% tokens vs grep**. Even if the agent doesn't route by question type, always-combining is a viable default.
- Route-by-kind is better: graphify alone wins on code questions (100% at 676 tokens); wiki alone wins on project questions (100% at 970 tokens). Combining for hybrid questions or as fallback when the first store misses pays a ~2× token cost.
- Graphify alone is the safest *single*-store default: 91.7% across kinds, cheapest, captures both code and the subset of project pages that have matching node labels (e.g. `WriteGate`, `delegate`).
- This validates the boundary clause already in [`wiki-memory/SKILL.md`](../wiki-memory/SKILL.md): graphify = *what/how/connected*; wiki = *why/decision*. When the first store misses, the **kind** of the question tells you which to try next.

### Issue matrix (status as of 2026-05-23, after upstream fixes applied to local install)

| Risk | Detection | Status |
|---|---|---|
| Stale graph after rename/delete | `update` left old nodes (now eviction by source_file path) | **FIXED locally** in `graphify/watch.py`; staleness probe verdict flipped `staleness_undetectable` → `good_staleness_signal` |
| `affected` / `benchmark` crash on `extract --no-cluster` graphs | Both expected `links` key, found `edges` | **FIXED locally** in `graphify/affected.py` + `graphify/benchmark.py` with the same edges→links normalization already present in `global_graph.py` |
| `cluster-only` silently misleads on node-count drift | Printed "graph.json updated" while refusing to write | **FIXED locally** in `graphify/__main__.py`: added `--force` flag, exit code 2 with clear refusal otherwise |
| `query` picks wrong start node on symbol questions | 50% evidence rate in A/B | Open — skill text steers `explain` first; an upstream fix would need NL→symbol resolver work |
| LLM-extracted concept nodes (when run with a backend) | Not tested here — semantic backend unavailable | Open: re-measure with Anthropic/Gemini key when available |
| Cost on doc-heavy repos | Not measured (code-only run) | Open: requires working semantic backend |

Upstream PRs filed against [safishamsi/graphify](https://github.com/safishamsi/graphify) for the three FIXED items (each ships a regression test, full 1,261-test suite passes on each branch):

- [#1002](https://github.com/safishamsi/graphify/pull/1002) — `fix: accept "edges" schema in affected and benchmark commands`
- [#1003](https://github.com/safishamsi/graphify/pull/1003) — `fix(cluster-only): add --force flag + non-zero exit when overwrite refused`
- [#1004](https://github.com/safishamsi/graphify/pull/1004) — `fix(update): evict nodes from re-extracted files, not just by id-match`

Patches are also applied locally to our `.venvs/graphify/` install until the PRs land.

### Ship gate

Per the integration plan's decision gates:
- **Δtokens < −30% AND Δjudge ≥ 0** → ship as default. **PASS** with `explain` verb (−93%, evidence rate parity).
- Concerns: staleness behavior + `query` weakness — both are now documented in [SKILL.md](SKILL.md) so the agent steers correctly.

**Decision: ship as default integration in `index-first` / `wiki-memory` skill text** (already applied to those skills). No new skill folder. Reassess if upstream graphify releases fix the additive-update behavior — would let us simplify the refresh recipe.
