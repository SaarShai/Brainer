# EVAL — `prompt-triage`

## Static cost (measured)

| field | tokens / size |
|---|---|
| description (always resident) | **69 tokens** (311 chars) |
| body (loaded on trigger)      | **871 tokens** (3226 chars) |
| tools/ payload                 | 21.1 KB |
| model pin                      | `any` |
| effort pin                     | `low` |

agentskills.io budget reference: description ≤ 1,536 chars (1% of a 200K context window).

## Live measurement (end-to-end routing, N=1 × 13 prompts)

Harness: `eval/runner_triage.py` — runs each corpus prompt twice: once routed to `mimo-v2.5-pro` (no triage), once routed by `classify.py` to `mimo-v2-flash` or `mimo-v2.5-pro` based on tier.

| metric | without triage | with triage | Δ |
|---|---:|---:|---:|
| total tokens | 6761 | 5345 | **-20.9%** |
| routing | all → `mimo-v2.5-pro` | cheap = 10 / expensive = 3 | — |
| classification accuracy | n/a | **100%** vs ground-truth tier | — |
| classifier latency | n/a | **49 ms** mean | — |

Interpretation: the regex fast-path correctly routes ~80% of typical prompts to a cheaper model, saving ~20% total tokens on a mixed-tier corpus. The static body cost (922 tokens) is fully offset within 6–8 routed prompts.

Raw: [`eval/results/prompt-triage.json`](../../eval/results/prompt-triage.json)


## Methodology

- Sample size: N=3-10 local smoke; N≥50 on Kaggle T4 for any >20% savings claim.
- Tasks: 3–5 representative prompts in `eval/tasks/prompt-triage.yaml`.
- Backends supported: `ollama`, `anthropic`, `mimo`, `mlx` (`--backend` arg).
- Judge: Xiaomi MiMo via `https://api.xiaomimimo.com/v1` (preferred for quality) or local Ollama.
- Rubric: per-task rubric embedded in the YAML.

## Failure modes

To be filled in after analysis of result outputs (see raw JSON for individual trial outputs).

## Moved from SKILL.md (2026-06-12 SkillReducer-criteria audit)

_Provenance/rationale below is maintainer context, not runtime instruction — relocated so the lazy-loaded body stays actionable._

## Cost math (informal)

- Without triage: opus reads prompt → thinks → acts → writes → verifies. ~3-8K tokens.
- With triage: hook (0 tokens) → opus reads directive + prompt → emits Task (~200 tokens) → haiku subagent does work (~500-2000 tokens).
- Net: ~70-90% token cost reduction on simple tasks (informal estimate; see EVAL.md for measured numbers).

## Lineage

- OpenRouter / Not Diamond routing layer.
- RouteLLM (ICLR 2025).
- Anthropic SDK Task tool + subagent_type.
- Orchestrator-worker multi-agent papers 2024-2026.

## 2026-06-12 self-audit (post fail-closed rebuild)

Measured on this machine (M3, python3.12, ollama qwen2.5:7b-instruct warm):

| Metric | Value |
|---|---|
| Hook latency (regex path, avg of 5) | ~113ms (python cold-start dominated) |
| Directive size when emitted | **76 tokens** (was 122 — boilerplate trimmed, empty `lean_context` dropped) |
| Hook cost when silent (hard/none/bypass/<0.7 conf) | 0 tokens |
| exp3 corpus N=48, deterministic (no LLM) | routing 100% on complex-protection: **0/18 complex → cheap**; tier 96.8% (1 conservative miss → opus) |
| exp3 corpus N=48, live ollama | routing 94.9%, tier 96.8%, split regex 22 / ollama 21 — **first live-LLM corpus run ever** (fallback was silently dead until 2026-06-12) |
| Cross-model misroute corpus (10 prompts, 5 complex) | qwen2.5 local 0/10 · gemma2:9b on M2 0/10 |
| Fuzz (empty/garbage/null/int/50KB/unicode payloads) | all exit 0, no partial directive output |
| Regression suite | `test_classify.py` 13 tests, offline, in `run_all_tests.sh`/CI |

Enforcement note: the directive is advisory by design — the main model can
(and sometimes should) override it; failure mode 3 documents this. Mining
showed overrides are usually correct on context-heavy prompts, so no
mechanical enforcement is added.

## 2026-06-12 live incidents #2/#3 — context-blind routing

Two same-day production misroutes after the hardening pass:
1. "summarize … what this current suite of skills does" → `local-ollama` directive. A context-blind subagent can't answer a question about the session; main model had to evaluate-and-override (directive was net-negative tokens).
2. LLM fallback routed a triage-policy question to `local-ollama/haiku`.

Fixes (locked by `test_session_context_prompts_stay_silent`, `test_no_local_models_in_routing_surface`):
- **context-guard**: prompts referencing the current session/conversation short-circuit to hard/none before any classifier runs.
- **platform-models-only policy**: `local-ollama` and `local:*` removed from RULES, the LLM schema, and `_VALID_AGENTS`. Triage routes only to in-platform small models (haiku/sonnet). Local models remain available for explicit manual dispatch.
- LLM prompt gained a context-reference → `agent="none"` rule.

Design lesson: a directive the main model must override costs MORE than no directive — every guard errs toward silence.

## 2026-06-12 round-3 stress/bench + codex adversarial pass

Benchmarks (this device): hook regex/guard path p50 67ms; LLM fallback warm 655–928ms under a single 2s TOTAL deadline (was 1s tags + 2s generate = 3s worst case). Fuzz 2×5,000 garbage/adversarial prompts: 0 crashes, 0 local-model leaks, 0 sub-0.7 directives, 0 length-gate bypasses.

Historical replay (`scripts/replay_triage.py`, now suite check #34): of 25 prompts that ever received a directive, 21 now correctly silent, 4 still routed (all short git-mechanical), 0 violations. New downgrade: `^commit...` rule drops to 0.6 when prompt >120 chars (multi-clause close-outs bundle non-mechanical work).

Codex round-3 fixes: `_validate_llm_result` clamps out-of-platform `model` values to tier defaults (haiku/sonnet/opus only); CONTEXT_HINTS gained contractions/modifiers ("we've built", "you just changed", "this thread", "our previous conversation") and DROPPED "this repo/branch/codebase" (filesystem state is subagent-readable — "commit and push this branch" keeps its cheap route); confidence-gate test made non-vacuous.

## 2026-06-12 field incidents #4/#5 (PROMPTER deploy + live session)

4. "can you run simulations in prompter..." → LLM fallback verdict `quick-fix/sonnet` @0.8 — quick-fix is a file-edit agent; LLM prompt now pins agent definitions (quick-fix = small scoped FILE EDITS only).
5. PROMPTER history replay: 4-objective brief ("look through X... find a method... document it... otherwise research...") → `research-lite/0.8` via regex. Fix: `_multi_objective()` — ≥3 imperative-opening sentences ⇒ complex-work guard, fail-closed without LLM. Locked by `test_multi_objective_prompt_never_routes_cheap`.

Replay after fix: Brainer 27 prompts → 4 routed (git-mechanical only); PROMPTER 12 → 2 routed ("commit and push" ×2). 0 violations both.

## 2026-06-12 simulated-week sweep (incident class #7 + brief-gate)

Full prompt history (229 real prompts, Brainer + PROMPTER) through the live classifier. Round 1: 116/228 routed (51%) — exposed the LLM fallback routing conversational continuations ("continue.", "do PROMPTER", "please apply all fixes", "let's forget m1"). Fixes:
- **CONTINUATION_RE** (anchored): continue/proceed/yes/ok/do it/apply all/let's/that's/retry… → context-guard.
- **short-unmatched**: <80 chars + no regex rule hit ⇒ silent without spending the LLM call (self-contained short tasks are what RULES encode).
- **Downgrade veto**: LLM "simple" cannot reopen a regex-downgraded route (the >120-char git close-out had reopened via LLM).
- **brief-gate** (hard, rank of length-gate): ≥3 imperative-start sentences or ≥3 newlines ⇒ hard/none even against an LLM "medium" (the screenery 4-objective brief had re-routed via medium).
- CONTEXT_HINTS additions: "you updated", "are you sure", "your role/goal/instructions".

Round 2 after guards: 79/229 (34%); round 3 with brief-gate hard: **67/230 (29%)** — haiku 45, sonnet 20, opus 2; spot-check clean (sheet edits, wiki notes, one-line fixes, git mechanicals).

Savings estimate IF all routed turns dispatched (assumptions: ~20k input/800 output tok per routed turn; opus $15/$75, sonnet $3/$15, haiku $1/$5 per Mtok): **~$20.88 over the ~6-week corpus ≈ $3.48/week** — modest in $, but each route also keeps ~20k tokens out of the main context window, which is the bigger win on long sessions.
