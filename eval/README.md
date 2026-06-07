# eval/ — skill A/B measurement

Three-layer measurement strategy. Each layer answers a different question.

## Local setup

```bash
pip install -r eval/requirements.txt    # datasets, PyYAML, tiktoken
```

Kaggle preinstalls these; `eval/kaggle_notebook.py` handles its own pinning.

## Layer 1 — Static cost (no model required)

What a skill costs the agent just by existing in the catalog (description-tokens, always resident).
What it costs when triggered (body-tokens, loaded once on trigger).

```bash
python3 eval/static_cost.py                 # markdown table to stdout
python3 eval/static_cost.py --json > out    # JSON for tooling
```

Current snapshot saved at `eval/results/static_cost.json`.

## Layer 2 — A/B prompt savings (model required)

For each skill, run the same task prompt twice: once with the SKILL.md body prepended to the system message (skill loaded), once without. Measure input/output tokens + latency + judge quality.

```bash
python3 eval/runner.py --task eval/tasks/caveman-ultra.yaml --n 10 \
    --backend ollama --model phi4:14b
python3 eval/runner.py --combo eval/combos/caveman+lean.yaml --n 10 \
    --backend anthropic --model claude-haiku-4-5-20251001
```

Supported backends:

| backend | env requirement | notes |
|---|---|---|
| `ollama` | local Ollama daemon on :11434 | default. Free. Slower. |
| `anthropic` | `ANTHROPIC_API_KEY` exported to subprocess | paid (haiku is cheap). |

Backend selection is per-run. Add others by editing `runner.py:call_model`.

## Layer 3 — Judge (LLM-as-judge)

Quality score on the runner's outputs.

```bash
python3 eval/judge.py eval/results/caveman-ultra.json \
    --model gemma4:26b --backend ollama
# or with Xiaomi MiMo via HuggingFace inference:
HF_TOKEN=... python3 eval/judge.py eval/results/caveman-ultra.json \
    --backend hf --model XiaomiMiMo/MiMo-7B
```

Rubric is embedded in each task YAML (`rubric:` field). Default rubric in `judge.py`.

## Combos

`eval/combos/` holds multi-skill manifests. Same shape as `tasks/`, but `skills:` is a list and each prompt is run with all listed SKILL.md bodies concatenated.

Three combo manifests to author (Phase D scope):

1. `prompt-triage + caveman-ultra + context-keeper` — everyday load
2. `wiki-memory + verify-before-completion + semantic-diff` — research-style tasks

_(Earlier drafts listed `compress-context` and `delegate` combos — both skills were cut; those combos are dropped.)_

## Kaggle T4 (N ≥ 50 runs)

For any skill claiming >20% savings, repeat the runner on Kaggle's free T4 notebooks (30h/week). Template at `bench/notebooks/kaggle_eval_template.md`. Use vLLM for ~10× throughput vs local Ollama.

## Output

`eval/results/<task-id>.json` — raw per-trial token counts + outputs.
`eval/results/<task-id>.judged.json` — judge scores appended.

Then each skill's `EVAL.md` is updated by hand (or scripted) with the summary deltas + 95% CIs.

## Known fragilities (current environment)

- Local Ollama on this machine has corrupted manifests (the daemon reports `model not found` for models that `ollama list` shows). Workaround: pull a fresh small model (`ollama pull llama3.2:1b`) or switch to `--backend anthropic`.
- `ANTHROPIC_API_KEY` is gated by the host harness — exported by name but the value is not visible to subprocesses. Set the key explicitly in your shell (`export ANTHROPIC_API_KEY=sk-...`) before running.
- `HF_TOKEN` not configured. Required for the `hf` backend / MiMo judging. Set it once: `export HF_TOKEN=hf_...`.
