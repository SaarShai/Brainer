# exp2_retrieval — wiki-memory retrieval-quality eval

Does a query surface the **right** lesson page, and is an answer **grounded** in
what was retrieved? This eval measures the shipped wiki-memory store
(`skills/wiki-memory/tools/wiki.py`) on hand-labeled queries.

Two layers, deliberately decoupled:

| layer | judge | always runs? | answers |
|---|---|---|---|
| **A. deterministic** | none (set math) | **yes** | did the right page id rank high? |
| **B. LLM-judged** | local Ollama | best-effort | is retrieved context relevant + is the answer grounded? |

Layer A never depends on the LLM. If the DeepEval/Ollama wiring breaks, we
*still* get precision@k / recall@k / MRR / hit@k.

## Files

- `queries.jsonl` — 35 hand-labeled queries: `{id, query, gold_page_ids, gold_answer, page_type}`.
  Gold ids were discovered with `wiki.py search` and then hand-verified against
  page bodies. Spans concept / pattern / project / person pages, plus a few
  hard / near-miss queries (person pages that lose to their citing concept page;
  a fuzzy "how do you measure savings" query).
- `retriever.py` — `WikiRetriever`: wraps `wiki.py` `search` (ranked hits) +
  `fetch` (page bodies). Prefers in-process import of `WikiStore`; falls back to
  the subprocess CLI (parsing the real stdout JSON contract) if import fails.
- `run_retrieval_eval.py` — runs both layers, writes `results/summary.json`.
- `results/summary.json` — mean metrics + per-query rows.

## Deterministic metrics (layer A)

Top-k = 5. Gold = hand-labeled page id(s) per query.

- **precision@k** — fraction of the top-k that are gold. Low by construction
  here: most queries have 1 gold page but we retrieve 5, so the ceiling is ~0.2.
- **recall@k** — fraction of gold ids found in the top-k. The headline number:
  "did we surface the right page at all?"
- **MRR** — 1 / rank of the first gold hit. "How high did the right page rank?"
- **hit@k** — 1 if any gold id is in the top-k.

## LLM-judged metrics (layer B, DeepEval + local Ollama)

- **ContextualPrecisionMetric** — are relevant retrieved chunks ranked above
  irrelevant ones?
- **ContextualRecallMetric** — does the retrieved context cover the expected
  (gold) answer?
- **FaithfulnessMetric** — is the answer grounded in the retrieved context (no
  hallucinated claims)?
- **AnswerRelevancyMetric** — does the answer actually address the query?

The test case feeds the **gold answer** as both `actual_output` and
`expected_output`, with the fetched page bodies as `retrieval_context`. So
faithfulness/recall here ask: "is the curated answer supported by, and covered
by, what the retriever surfaced for this query?"

### Local judge wiring (no OpenAI key)

DeepEval's metrics call `model.generate_with_schema(prompt, schema=PydanticCls)`.
We supply a custom `DeepEvalBaseLLM` (`build_local_judge`) that:

1. Hits Ollama **`/api/generate`** (not `/api/chat` — see caveats) with
   `temperature=0` and a large `num_predict` (default 2048).
2. Strips `<think>...</think>` blocks (reasoning models like `deepseek-r1`
   spend most of their budget thinking before emitting the final JSON).
3. Parses the first balanced JSON object and `model_validate`s it into the
   requested pydantic schema; on any failure, returns a benign default instance
   so one bad judge call can't abort the whole metric run (`coerce_failures` is
   counted in the summary).

## Reproduce

```bash
# Layer A only (fast, system python3 is fine — needs only the retriever):
python3 eval/exp2_retrieval/run_retrieval_eval.py --k 5

# Layers A + B (needs deepeval; use the venv):
python3 -m venv eval/exp2_retrieval/.venv
eval/exp2_retrieval/.venv/bin/pip install deepeval
eval/exp2_retrieval/.venv/bin/python eval/exp2_retrieval/run_retrieval_eval.py \
    --k 5 --llm --llm-subset 4 --judge-model deepseek-r1:32b --num-predict 2048
```

`--llm-subset` bounds how many queries get LLM-judged (each query is 4 metrics ×
several ~30-110s model calls — the full set would run for hours on a 32B local
model). Deterministic metrics always cover all 35 queries.

## Local models present (`ollama list`)

- `deepseek-r1:32b` — **working judge** via `/api/generate` (reasoning model;
  needs the `<think>` strip + large budget). ~30-110s per metric.
- `qwen3.6:35b-a3b-q4km` — thinking model; emitted empty completions at the
  budgets tried (kept thinking). Not used.
- `gemma4:26b` — **404s** on `/api/generate` (`model 'gemma4:26b' not found`)
  despite appearing in `ollama list`. Not usable.
