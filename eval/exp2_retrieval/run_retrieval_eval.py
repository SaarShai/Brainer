"""Retrieval-quality eval for the wiki-memory store.

Two independent layers:

  (A) DETERMINISTIC retrieval metrics — ALWAYS produced, no LLM, no network.
      For each labeled query we retrieve top-k page ids from wiki.py search and
      score against hand-labeled gold ids:
        - precision@k : fraction of retrieved that are gold
        - recall@k    : fraction of gold that were retrieved
        - MRR         : 1 / rank of the first gold hit (0 if none in top-k)
        - hit@k       : 1 if any gold id is in top-k
      These are the numbers we get no matter what happens with the LLM judge.

  (B) DeepEval LLM-JUDGED metrics — best-effort, local Ollama judge, no OpenAI.
        - ContextualPrecisionMetric : are relevant retrieved chunks ranked high?
        - ContextualRecallMetric    : does retrieved context cover the gold answer?
        - FaithfulnessMetric        : is a generated answer grounded in context?
        - AnswerRelevancyMetric     : does the answer address the query?
      The judge is a custom DeepEvalBaseLLM wrapping Ollama /api/generate. We use
      /api/generate (not /api/chat) and a large num_predict budget so reasoning
      models (deepseek-r1) can think and still emit the final JSON, which we
      strip of <think>...</think> before parsing. Runs on a bounded subset
      (--llm-subset) because each judged metric is many ~30-40s model calls.

Usage:
    python3 run_retrieval_eval.py                 # deterministic only
    python3 run_retrieval_eval.py --llm           # + LLM judge on a subset
    python3 run_retrieval_eval.py --llm --llm-subset 6 --judge-model deepseek-r1:32b
"""
from __future__ import annotations

import argparse
import json
import re
import statistics
import sys
import time
import urllib.request
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from retriever import WikiRetriever  # noqa: E402

QUERIES_PATH = HERE / "queries.jsonl"
RESULTS_DIR = HERE / "results"
SUMMARY_PATH = RESULTS_DIR / "summary.json"
OLLAMA_URL = "http://localhost:11434/api/generate"
THINK_RE = re.compile(r"<think>.*?</think>", re.DOTALL)


# --------------------------------------------------------------------------- IO
def load_queries() -> list[dict[str, Any]]:
    rows = []
    for line in QUERIES_PATH.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            rows.append(json.loads(line))
    return rows


# ------------------------------------------------------ deterministic metrics
def precision_at_k(retrieved: list[str], gold: set[str], k: int) -> float:
    top = retrieved[:k]
    if not top:
        return 0.0
    return sum(1 for r in top if r in gold) / len(top)


def recall_at_k(retrieved: list[str], gold: set[str], k: int) -> float:
    if not gold:
        return 0.0
    top = set(retrieved[:k])
    return sum(1 for g in gold if g in top) / len(gold)


def mrr(retrieved: list[str], gold: set[str]) -> float:
    for i, r in enumerate(retrieved, start=1):
        if r in gold:
            return 1.0 / i
    return 0.0


def hit_at_k(retrieved: list[str], gold: set[str], k: int) -> float:
    return 1.0 if any(r in gold for r in retrieved[:k]) else 0.0


# ----------------------------------------------------- local Ollama LLM judge
def _ollama_generate(model: str, prompt: str, num_predict: int = 2048, timeout: int = 300) -> str:
    payload = json.dumps(
        {
            "model": model,
            "prompt": prompt,
            "stream": False,
            "options": {"temperature": 0.0, "num_predict": num_predict},
        }
    ).encode("utf-8")
    req = urllib.request.Request(OLLAMA_URL, data=payload, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    if data.get("error"):
        raise RuntimeError(f"ollama error: {data['error']}")
    return data.get("response", "")


def _strip_think(text: str) -> str:
    """Drop <think>...</think> reasoning blocks (deepseek-r1 / qwen thinking)."""
    text = THINK_RE.sub("", text)
    # If an unclosed <think> remains (budget ran out mid-think), drop from it on.
    if "<think>" in text:
        text = text.split("<think>", 1)[0]
    return text.strip()


def _extract_json(text: str) -> dict[str, Any] | None:
    """Best-effort: find the first balanced {...} object in the text."""
    start = text.find("{")
    while start != -1:
        depth = 0
        for i in range(start, len(text)):
            c = text[i]
            if c == "{":
                depth += 1
            elif c == "}":
                depth -= 1
                if depth == 0:
                    blob = text[start : i + 1]
                    try:
                        return json.loads(blob)
                    except json.JSONDecodeError:
                        break
        start = text.find("{", start + 1)
    return None


def build_local_judge(model: str, num_predict: int):
    """Return a DeepEvalBaseLLM that talks to local Ollama /api/generate.

    Implements schema-constrained generation by injecting the pydantic JSON
    schema into the prompt, stripping <think> blocks, and coercing the parsed
    JSON into the requested schema. On any failure we return a benign default
    instance so a single bad judge call cannot abort the whole metric run.
    """
    from deepeval.models.base_model import DeepEvalBaseLLM
    from pydantic import BaseModel

    def _default_for(schema: type[BaseModel]) -> BaseModel:
        fields: dict[str, Any] = {}
        for name, field in schema.model_fields.items():
            ann = field.annotation
            ann_str = str(ann)
            if "list" in ann_str.lower() or "List" in ann_str:
                fields[name] = []
            elif ann is bool or "bool" in ann_str:
                fields[name] = False
            elif ann is float or ann is int or "float" in ann_str or "int" in ann_str:
                fields[name] = 0
            else:
                fields[name] = ""
        try:
            return schema(**fields)
        except Exception:  # noqa: BLE001
            return schema.model_construct(**fields)

    class LocalOllamaJudge(DeepEvalBaseLLM):
        def __init__(self, model_name: str):
            self.model_name = model_name
            self.calls = 0
            self.coerce_failures = 0

        def load_model(self):
            return self.model_name

        def get_model_name(self) -> str:
            return f"ollama:{self.model_name}"

        def generate(self, prompt: str, schema=None, **kwargs):  # noqa: ANN001
            self.calls += 1
            full = prompt
            if schema is not None:
                try:
                    js = json.dumps(schema.model_json_schema())
                except Exception:  # noqa: BLE001
                    js = "{}"
                full = (
                    f"{prompt}\n\n"
                    "IMPORTANT: Respond with ONLY a single JSON object that conforms to this JSON schema. "
                    "No markdown, no prose, no code fences.\n"
                    f"JSON schema: {js}\n"
                    "JSON:"
                )
            raw = _ollama_generate(self.model_name, full, num_predict=num_predict)
            cleaned = _strip_think(raw)
            if schema is None:
                return cleaned
            parsed = _extract_json(cleaned)
            if parsed is not None:
                try:
                    return schema.model_validate(parsed)
                except Exception:  # noqa: BLE001
                    self.coerce_failures += 1
            else:
                self.coerce_failures += 1
            return _default_for(schema)

        async def a_generate(self, prompt: str, schema=None, **kwargs):  # noqa: ANN001
            return self.generate(prompt, schema=schema, **kwargs)

    return LocalOllamaJudge(model)


def run_llm_metrics(rows_to_judge: list[dict[str, Any]], judge, k: int) -> dict[str, Any]:
    """Run DeepEval contextual + grounding metrics on a subset of queries."""
    from deepeval.metrics import (
        AnswerRelevancyMetric,
        ContextualPrecisionMetric,
        ContextualRecallMetric,
        FaithfulnessMetric,
    )
    from deepeval.test_case import LLMTestCase

    metrics_factory = {
        "contextual_precision": lambda: ContextualPrecisionMetric(model=judge, threshold=0.5, async_mode=False, verbose_mode=False),
        "contextual_recall": lambda: ContextualRecallMetric(model=judge, threshold=0.5, async_mode=False, verbose_mode=False),
        "faithfulness": lambda: FaithfulnessMetric(model=judge, threshold=0.5, async_mode=False, verbose_mode=False),
        "answer_relevancy": lambda: AnswerRelevancyMetric(model=judge, threshold=0.5, async_mode=False, verbose_mode=False),
    }

    per_query: list[dict[str, Any]] = []
    for row in rows_to_judge:
        q = row["query"]
        contexts = row["_contexts"][:k]
        # Use the gold answer as the system's "actual_output" so faithfulness /
        # answer-relevancy measure whether the gold answer is grounded in and
        # relevant to what the retriever surfaced. expected_output drives
        # contextual recall (does retrieved context cover the expected answer).
        gold_answer = row.get("gold_answer") or ""
        tc = LLMTestCase(
            input=q,
            actual_output=gold_answer,
            expected_output=gold_answer,
            retrieval_context=contexts or ["[no context retrieved]"],
        )
        scores: dict[str, Any] = {}
        for name, factory in metrics_factory.items():
            entry: dict[str, Any] = {}
            try:
                m = factory()
                t0 = time.time()
                m.measure(tc)
                entry = {"score": m.score, "reason": (m.reason or "")[:300], "seconds": round(time.time() - t0, 1)}
            except Exception as exc:  # noqa: BLE001
                entry = {"score": None, "error": repr(exc)[:300]}
            scores[name] = entry
        per_query.append({"id": row["id"], "query": q, "metrics": scores})
        sys.stderr.write(f"[llm] judged {row['id']} ({q[:50]}...)\n")
        sys.stderr.flush()

    # Aggregate means per metric over successful scores.
    agg: dict[str, Any] = {}
    for name in metrics_factory:
        vals = [pq["metrics"][name].get("score") for pq in per_query if isinstance(pq["metrics"][name].get("score"), (int, float))]
        agg[name] = {
            "mean": round(statistics.mean(vals), 4) if vals else None,
            "n": len(vals),
            "n_failed": len(per_query) - len(vals),
        }
    return {"aggregate": agg, "per_query": per_query}


# ----------------------------------------------------------------------- main
def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--k", type=int, default=5, help="top-k for retrieval metrics (default 5)")
    ap.add_argument("--wiki-root", default=None, help="wiki root (default: repo/wiki)")
    ap.add_argument("--llm", action="store_true", help="also run DeepEval LLM-judged metrics (local Ollama)")
    ap.add_argument("--llm-subset", type=int, default=6, help="how many queries to LLM-judge (default 6)")
    ap.add_argument("--judge-model", default="deepseek-r1:32b", help="Ollama model for the judge")
    ap.add_argument("--num-predict", type=int, default=2048, help="judge token budget per call (reasoning models need headroom)")
    args = ap.parse_args()

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    queries = load_queries()
    retriever = WikiRetriever(wiki_root=args.wiki_root)
    sys.stderr.write(f"[eval] retriever mode={retriever.mode}, {len(queries)} queries, k={args.k}\n")

    # ---- (A) deterministic metrics, always ----
    per_query: list[dict[str, Any]] = []
    p_list, r_list, mrr_list, hit_list = [], [], [], []
    for row in queries:
        gold = set(row["gold_page_ids"])
        res = retriever.retrieve(row["query"], k=args.k, fetch_bodies=args.llm)
        retrieved = res["ranked_ids"]
        p = precision_at_k(retrieved, gold, args.k)
        rec = recall_at_k(retrieved, gold, args.k)
        mr = mrr(retrieved, gold)
        ht = hit_at_k(retrieved, gold, args.k)
        p_list.append(p); r_list.append(rec); mrr_list.append(mr); hit_list.append(ht)
        # carry contexts for the LLM layer without re-fetching
        row_ctx = res.get("contexts", [])
        per_query.append(
            {
                "id": row["id"],
                "query": row["query"],
                "page_type": row.get("page_type"),
                "gold_page_ids": row["gold_page_ids"],
                "retrieved_ids": retrieved,
                f"precision@{args.k}": round(p, 4),
                f"recall@{args.k}": round(rec, 4),
                "mrr": round(mr, 4),
                f"hit@{args.k}": ht,
                "first_gold_rank": next((i + 1 for i, x in enumerate(retrieved) if x in gold), None),
            }
        )
        # stash contexts on the original row for reuse in LLM layer
        row["_contexts"] = row_ctx

    det = {
        f"precision@{args.k}": round(statistics.mean(p_list), 4),
        f"recall@{args.k}": round(statistics.mean(r_list), 4),
        "mrr": round(statistics.mean(mrr_list), 4),
        f"hit@{args.k}": round(statistics.mean(hit_list), 4),
        "n_queries": len(queries),
    }
    sys.stderr.write(f"[eval] deterministic: {json.dumps(det)}\n")

    summary: dict[str, Any] = {
        "experiment": "exp2_retrieval — wiki-memory retrieval quality",
        "k": args.k,
        "retriever_mode": retriever.mode,
        "wiki_root": str(retriever.wiki_root),
        "deterministic": {
            "aggregate": det,
            "per_query": per_query,
        },
        "llm_judged": None,
    }

    # ---- (B) DeepEval LLM judge, best-effort ----
    if args.llm:
        llm_caveats: list[str] = []
        try:
            import deepeval  # noqa: F401

            judge = build_local_judge(args.judge_model, args.num_predict)
            # judge only rows that have a gold_answer + contexts
            judgeable = [r for r in queries if r.get("gold_answer") and r.get("_contexts")]
            subset = judgeable[: args.llm_subset]
            sys.stderr.write(f"[eval] LLM-judging {len(subset)} queries with {args.judge_model} (this is slow)\n")
            t0 = time.time()
            llm_result = run_llm_metrics(subset, judge, args.k)
            llm_result["judge_model"] = f"ollama:{args.judge_model}"
            llm_result["judge_calls"] = getattr(judge, "calls", None)
            llm_result["judge_coerce_failures"] = getattr(judge, "coerce_failures", None)
            llm_result["wall_seconds"] = round(time.time() - t0, 1)
            llm_result["subset_size"] = len(subset)
            summary["llm_judged"] = llm_result
        except Exception as exc:  # noqa: BLE001
            llm_caveats.append(f"LLM judge failed: {exc!r}")
            summary["llm_judged"] = {"error": repr(exc)[:500], "caveats": llm_caveats}
            sys.stderr.write(f"[eval] LLM judge failed: {exc!r}\n")

    # Don't clobber an expensive prior LLM-judged block on a deterministic-only
    # run. If --llm was not passed and a previous summary already carries a
    # non-null llm_judged aggregate, carry it forward (tag it as stale so it's
    # never mistaken for a fresh judgement of this run's retrieval).
    if not args.llm and summary["llm_judged"] is None and SUMMARY_PATH.exists():
        try:
            prior = json.loads(SUMMARY_PATH.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:  # noqa: BLE001
            sys.stderr.write(f"[eval] could not read prior summary to preserve llm_judged: {exc!r}\n")
            prior = {}
        prior_llm = prior.get("llm_judged")
        if prior_llm is not None:
            prior_llm = dict(prior_llm)
            prior_llm["stale"] = True
            prior_llm["note"] = "carried over from an earlier --llm run; not re-judged on this deterministic-only run"
            summary["llm_judged"] = prior_llm
            sys.stderr.write("[eval] preserved prior llm_judged block (deterministic-only run)\n")

    SUMMARY_PATH.write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
    sys.stderr.write(f"[eval] wrote {SUMMARY_PATH}\n")
    print(json.dumps(summary["deterministic"]["aggregate"], indent=2))
    if summary.get("llm_judged") and "aggregate" in summary["llm_judged"]:
        print(json.dumps(summary["llm_judged"]["aggregate"], indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
