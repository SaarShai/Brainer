# GOAL — Brainer as a hardened suite for other projects

_Set 2026-06-12 by the optimization session. Successor sessions: read this before re-deriving priorities. Update targets only with measurement; never weaken a gate to pass it._

## Mission

Brainer is **scaffolding consumed by other projects** — a dependency-light suite of skills, hooks, and small tools that makes any AI coding agent cheaper (tokens), longer-lived (context), smarter over time (learning + memory), and better at handing work to the right worker (delegation). The product is the suite; this repo is never the target project.

Every skill must be: **robust** (survives host quirks, bad input, re-install), **tested** (deterministic suite where scriptable, cross-model A/B where model-dependent), **functional** (works on a fresh host via `./install.sh`), **gainful** (measured-positive or explicitly load-bearing), **reliable** (same result twice), **efficient** (costs less than it saves).

## Measurable targets by axis

| Axis | Target | Now | Guard |
|---|---|---|---|
| **Token usage** | Always-on tax ≤ 1,100 tok at 16 skills (≈69/skill avg); shrink via SkillReducer audit, not by gutting trigger phrases; every default-installed skill measured-positive or load-bearing | ~1,080 tok, 16 default skills (the "998" was a 15-skill figure) | `static_cost.py` re-run on catalog change; new skill ⇒ `EVAL.md` before default-on |
| **Context window** | Re-reads via semantic-diff (95%+ saved); search via index-first; compaction recall ≥ 97% transcript compression with 100% URL / ≥67% number recall | measured | deterministic suites in `skills/*/tools/tests/` |
| **Learning / self-improvement** | Lesson that recurs after documentation ⇒ MECHANICAL gate (hook/lint/eval), never more prose; lessons used 2× ⇒ promoted into a SKILL.md | ladder defined; promotion manual | `compliance-canary` probes; retrospective HARD RULE |
| **Memory** | Zero unverified writes (write-gate); wiki-refresh drift detection F1 = 1.0; retrieval evidence-rate 100% on project-history Qs | measured (exp14, exp2/6) | gated writes only; `wiki lint` in CI |
| **Delegation / orchestration** | prompt-triage: 0 complex prompts routed to cheap workers (incl. long/multi-part prompts); cheapest-capable model per task; subagent briefs carry goal/scope/exclusions/return-format | **violated 2026-06-12**: this session's own kickoff prompt → `research-lite/sonnet` @ conf 0.6 | triage eval corpus must include long multi-objective prompts; misroute = red |

## Suite-level definition of done

1. `./install.sh` idempotent + self-healing on all three hosts (claude-code, codex, gemini); broken links/hooks prune on re-install.
2. One command runs every deterministic test the repo ships; exit code is the verdict.
3. Model-dependent claims carry ≥2-model-family evidence (local ollama / M1 / M2 / Kaggle) before headline status.
4. Catalog stays pruned: a skill that is unmeasured AND redundant gets cut, not kept.
5. Session knowledge survives: gated wiki write per session; GOAL.md targets re-checked, not re-invented.

## Anti-goals

- No framework dependencies (crewai/langgraph/etc. are pattern sources, not imports).
- No default-on skill without a measured number or explicit load-bearing rationale.
- No prose rule where a mechanical gate can stand (hook, lint, CI, eval criterion).
- No new skill when a section in an existing skill covers it (catalog tax is real: ~70 tok/skill).

## Standing backlog (ranked; refresh per session)

See `wiki/projects/` + `eval/FINDINGS.md` for evidence. As of 2026-06-12:

1. ~~**prompt-triage complex-prompt misroute**~~ — **DONE 2026-06-12**: dead-fallback-tag auto-resolution, fail-closed, <0.7-conf silence, 1500-char length gate, 9-test regression lock, 2-family cross-model 0/10 violations. (delegation axis)
2. ~~**correction-capture**~~ — **DONE 2026-06-12** as canary `user_correction` probe kind + wiki-memory probe (no new skill; probe suffices). (learning axis)
3. ~~**Transcript telemetry**~~ — **v1 DONE 2026-06-12**: `scripts/mine_transcripts.py` (tool histograms, error signatures, triage audit, re-read offenders). Not yet: cache-bust $$ attribution (ccmeter's remaining edge). (token axis)
4. ~~**SkillReducer self-audit**~~ — **DONE 2026-06-12** (their pipeline has no public repo; criteria audit by subagent instead): all 16 descriptions pass routing checks; ~1,100 tokens of lineage/rationale moved from 7 runtime bodies to EVAL.md (worst-case body cost 17,458→16,649). Declined risky trims: verify-before-completion harvest block (reflex under-fire risk), caveman-ultra (measured-tuned). Note: hook-skill bodies do NOT load on hook fire — per-invocation payoff only. (token axis)
5. ~~**Workflow-tool orchestration patterns**~~ — **v1 DONE 2026-06-12**: `.claude/workflows/suite-health.js` — fan-out per-skill SKILL.md↔code reconcile + adversarial verify (the model-judgment complement to `run_all_tests.sh`); registered and syntax-validated. Deploy-stack workflows judged ceremony (install.sh already deploys); `eval/combos/` YAMLs stay as eval configs. (orchestration axis)
6. **output-filter wiring** — decided 2026-06-12: nothing to auto-wire; PostToolUse cannot rewrite already-returned output, pipe-form is the real mechanism (behavioral). Biggest mined offender (wiki lint 22KB JSON) fixed at source instead. Re-open only if a host gains output-rewriting hooks.
