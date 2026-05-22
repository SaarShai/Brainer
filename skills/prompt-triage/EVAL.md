# EVAL — `prompt-triage`

## Static cost (measured)

| field | tokens / size |
|---|---|
| description (always resident) | **89 tokens** (320 chars) |
| body (loaded on trigger)      | **922 tokens** (3204 chars) |
| tools/ payload                | 21.1 KB |
| model pin                     | `local` |
| effort pin                    | `low` |

(Note: the body is loaded into the *hook* process, not the model's context, so its size only matters at hook-execution time. The model receives the small classifier directive — typically <60 tokens.)

## Live measurement (end-to-end routing A/B, N=1 × 13 prompts)

Harness: `eval/runner_triage.py` — runs each prompt through two paths and sums total input+output tokens.

| metric | value |
|---|---|
| classification accuracy (vs ground-truth tier labels) | **100%** (13 of 13) |
| classify time (regex fast-path, no Ollama) | **49 ms / prompt** |
| routing: simple/medium → mimo-v2-flash (cheap) | 10 prompts |
| routing: hard/unknown → mimo-v2.5-pro (expensive) | 3 prompts |
| total tokens WITHOUT triage (always-expensive) | 6,761 |
| total tokens WITH triage (router on) | **5,345** |
| **Δ total tokens** | **−1,416 (−20.9%)** |

The regex fast-path alone correctly classified every prompt in the corpus. Ollama fallback would only fire on prompts that fail every regex; on this corpus, none did.

## Token-cost interpretation

For a session of roughly the same prompt mix:

- Every prompt incurs a fixed **49 ms / ~0 tokens** classification overhead (regex on the hook side).
- 77% of prompts (the simple/medium ones) get routed to a model ~3× cheaper than the default.
- 23% of prompts (the hard ones) still get the expensive model — no quality loss on the work that needs it.
- Aggregate end-to-end savings: **−21%** vs always-expensive on this corpus.

Savings scale linearly with the cheap-vs-expensive cost ratio. If the cheap tier is haiku and expensive is opus (where the cost ratio is ~15× rather than ~3×), the same routing split (77/23) would deliver ~70% savings.

## Corpus

13 prompts in `eval/tasks/prompt-triage-corpus.yaml`:
- 7 simple (factual, one-liner, wiki, git mechanical, install)
- 3 medium (research, investigate, survey)
- 3 hard (refactor architecture, design system, distributed lock service)

## Methodology

```bash
. .token-economy/secrets.env && export MIMO_API_KEY
python3 eval/runner_triage.py \
  --corpus eval/tasks/prompt-triage-corpus.yaml \
  --cheap mimo-v2-flash \
  --expensive mimo-v2.5-pro \
  --n 1 \
  --no-ollama
```

To enable the Ollama fallback (slower, used only when regex returns no signal):

```bash
unset AGENTS_TRIAGE_NO_OLLAMA  # or drop --no-ollama
```

## Limitations

- The corpus is small (N=13) and curated. A wider real-prompt distribution would tighten the accuracy CI.
- Cost ratio between cheap/expensive depends on the host: 3× here (MiMo flash vs pro), 15× on Anthropic (haiku vs opus). Headline % savings will track that ratio.
- Quality measurement (Δjudge) not yet run for this corpus. The classifier never sends hard prompts to the cheap model, so the routed-cheap subset should be unaffected; needs verification.

## Lineage

- OpenRouter / Not Diamond routing.
- RouteLLM (ICLR 2025).
- Orchestrator-worker multi-agent papers 2024-2026.
