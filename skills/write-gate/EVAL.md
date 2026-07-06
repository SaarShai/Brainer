# write-gate — EVAL

## Mechanism in one line

Score candidate text on signal features (decisions / errors / architecture / code / numbers / entity overlap, minus filler / speculation); reject if below threshold; additionally reject decision-class facts that lack a why-clause.

## Published numbers from lineage projects

| Source | Reported |
|---|---|
| [ogham-mcp/ogham-mcp](https://github.com/ogham-mcp/ogham-mcp) | 91.8% QA, 97.2% R@10 on LongMemEval with signal-score lifecycle (FRESH→STABLE→EDITING + 5%/30d decay) |
| [codenamev/claude_memory](https://github.com/codenamev/claude_memory) | 100% truth-maintenance on a 100-case FEVER-derived test set; why-clause requirement is core to that result |

## Built-in smoke tests

`python tools/test_write_gate.py` — 7 tests covering:

- decisions without why-clause are rejected
- decisions with why-clause pass
- pure filler / recap is rejected
- concrete error+fix passes
- architecture + code + numbers passes
- pure speculation is rejected
- entity-overlap is capped at +1.5 (cannot single-handedly satisfy the gate)

## Project-local A/B (target)

Once write-gate is wired into `wiki-memory`'s `new` path:

- **Acceptance rate** — fraction of candidate writes that pass. Target: 50–70%. Higher means the gate is too loose; lower means we're starving the wiki.
- **Retrieval evidence-rate** — measured by existing `runner_wiki.py`. Target: no drop vs the pre-gate baseline, ideally a small uptick from less noise in the index.
- **Page-creation rate** — pages added per session. Target: down ≥40% with no drop in evidence-rate.

Status: design + smoke tests shipped; project-local A/B pending the wiki-memory integration commit.

## Anti-falsifications

- If acceptance rate falls below 30% in real use, the threshold is too high. Lower to 2.5 and re-run.
- If retrieval evidence-rate drops despite acceptance staying healthy, the gate is rejecting useful facts — likely the speculation / filler weights are over-aggressive. Inspect rejected candidates for false positives.
- If the wiki accumulates decisions WITHOUT reasons over a 50-page sample, the why-clause check is being bypassed. Trace `wiki/log.md` for override entries.

## Known limits

- Heuristic regex / phrase matching; cannot catch a decision phrased entirely in metaphor.
- English-only. Phrase tables would need translation for non-English wikis.
- No semantic novelty check — a write that scores high but duplicates an existing page still passes the gate. Dedup is `wiki-memory`'s job.

## Failure modes

Premortem ([`LEARNING_CONTRACT`](../_shared/LEARNING_CONTRACT.md) §8):

- **Silent-failure path** — callers write to persistent stores without invoking the gate at
  all; the gate can't reject a call that never happens. `wiki.py new_page()` closes this for
  its own path (calls `gate_candidate()` in-code, not by convention), but a hand-edit to
  `CLAUDE.md`/`AGENTS.md` or a raw `mcp__memory__*` write bypasses the gate entirely with no
  error surfaced anywhere — the pollution looks identical to a gated write until someone
  reads it back.
- **Rot-when-unwatched** — the phrase tables (decision markers, why-clause connectives,
  filler/speculation regex) are tuned to today's writing style; as skills and users drift
  toward new phrasing ("landed on X" instead of "chose X"), true decisions silently stop
  scoring the decision-marker weight and slip through the why-clause requirement unchecked.
  Nothing currently re-validates the phrase tables against fresh wiki content.
- **No-hooks host** — write-gate is a CLI invoked in-band (`write_gate.py gate`), not a hook,
  so it works identically on Codex/Gemini per `docs/HOST_CAPABILITY_MATRIX.md` ("skills are
  text-portable; tools are plain python3/bash") — the exposure is procedural, not
  hook-availability: nothing forces the caller to run it before writing except the
  instruction in this file and the in-code wiring at wiki-memory's own write path.

## Moved from SKILL.md (2026-06-12 SkillReducer-criteria audit)

_Provenance/rationale below is maintainer context, not runtime instruction — relocated so the lazy-loaded body stays actionable._

## What this prevents

Without a content gate, memory fills with:
- "We decided to use library X" with no reason → can't be re-evaluated later
- Recaps of conversation already in the transcript
- Speculation cached as fact
- Trivia inflated into procedures

Result: noisy memory → wrong context injected → worse answers. This skill makes write-side quality the bottleneck instead of post-hoc cleanup.

## Measured gain (2026-06-13, `eval/gains.py` + `eval/ablation.py`)

The gate keeps **38% of candidate-memory tokens out of durable storage** vs ungated (admit-all) on the labeled corpus — quantifies the memory-pollution prevented. H1 ablation confirms the 7 positive features are load-bearing and the filler/speculation penalties ARE decisive at the decision boundary (a hedged fact `…maybe holds 320MB…` scores +2.0 REJECT vs +3.5 KEEP without the penalty); boundary cases added to `write_gate_labeled.jsonl` so those penalties are now regression-covered. FP=0 preserved.
