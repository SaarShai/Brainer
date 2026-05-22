#!/usr/bin/env python3
"""Retrieval A/B for wiki-memory.

For each question:
  A. Vanilla — cold-answer with no wiki context.
  B. Retrieved — wiki-search returns top-k hits; their previews are
     injected into the system prompt, then the same question is asked.

Both runs use the same model (mimo-v2-flash). Measure:
  - input tokens (B carries the retrieved context, so it's larger)
  - output tokens (terser when grounded; verbose when guessing)
  - judge score on correctness (mimo-v2-flash, simple rubric)

Headline metric: did retrieval IMPROVE the answer per token spent?

Usage:
  python3 eval/runner_wiki.py [--n 1]
"""
from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
import time
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "skills" / "wiki-memory" / "tools"))

from wiki import WikiStore  # noqa: E402


QUESTIONS = [
    # Questions whose answers live in our wiki
    "What's semantic-diff and how much can it save on file re-reads?",
    "What's our context-keeper extracting from a transcript before compaction?",
    "How does the compound compression pipeline (ComCom) work?",
    "What's the difference between context-keeper v1 and v2?",
    "What does the delegate-router project do?",
    "Summarize the relay-session feature and when to use it.",
    "What's the wiki-governance approach in this repo?",
    "What did our 2026-04-17 semantic-diff prior-art survey conclude about Difftastic?",
]


def call_mimo(model: str, system: str, prompt: str, max_tokens: int = 400) -> dict:
    key = os.environ["MIMO_API_KEY"]
    base = os.environ.get("MIMO_BASE_URL", "https://api.xiaomimimo.com/v1").rstrip("/")
    body = json.dumps({
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": prompt},
        ],
        "max_tokens": max_tokens,
        "temperature": 0.0,
    }).encode()
    req = urllib.request.Request(
        f"{base}/chat/completions",
        data=body,
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
    )
    t0 = time.time()
    with urllib.request.urlopen(req, timeout=120) as r:
        d = json.loads(r.read())
    msg = d["choices"][0]["message"]
    usage = d.get("usage", {})
    return {
        "output": (msg.get("content") or "").strip(),
        "prompt_tokens": usage.get("prompt_tokens", 0),
        "completion_tokens": usage.get("completion_tokens", 0),
        "latency_ms": int((time.time() - t0) * 1000),
    }


def judge_score(model: str, question: str, candidate: str) -> int | None:
    """Quick 0-5 rubric. Reuses mimo-v2-flash for cheap, deterministic scoring."""
    rubric = (
        "Rate the candidate 0-5 on whether it correctly and concretely answers the question. "
        "5 = correct, specific, uses concrete details. "
        "4 = correct, slightly vague. "
        "3 = partial / general. "
        "2 = mostly wrong / overly speculative. "
        "1 = wrong. "
        "0 = refused / blank. "
        "Reply digit only on first line."
    )
    r = call_mimo(
        model,
        "You are an evaluation judge. Be strict, terse.",
        f"QUESTION:\n{question}\n\nCANDIDATE:\n{candidate}\n\n{rubric}",
        max_tokens=20,
    )
    txt = r["output"].strip()
    for ln in txt.splitlines():
        ln = ln.strip()
        if ln and ln[0].isdigit():
            return int(ln[0])
    return None


def build_retrieval_context(query: str, k: int = 3) -> tuple[str, list[str]]:
    """Use wiki-memory's WikiStore to fetch top-k page previews."""
    ws = WikiStore(str(REPO_ROOT / "wiki"))
    hits = ws.search(query, k)
    lines = []
    titles = []
    for h in hits:
        titles.append(h["id"])
        lines.append(f"### {h['title']}  ({h['id']})")
        lines.append(h.get("preview", ""))
    return "\n\n".join(lines), titles


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--n", type=int, default=1)
    p.add_argument("--model", default="mimo-v2-flash")
    p.add_argument("--out", default="eval/results/wiki-memory.json")
    args = p.parse_args()

    vanilla_sys = "You are a helpful coding assistant. Answer concisely."

    cold: list[dict] = []
    retrieved: list[dict] = []
    cold_scores: list[int | None] = []
    retrieved_scores: list[int | None] = []
    hit_lists: list[list[str]] = []

    for trial in range(args.n):
        for q in QUESTIONS:
            ctx_text, hits = build_retrieval_context(q, k=3)
            hit_lists.append(hits)
            grounded_sys = (
                vanilla_sys
                + "\n\nThe following wiki excerpts may be relevant; ground your answer in them when possible.\n\n"
                + ctx_text
            )
            a = call_mimo(args.model, vanilla_sys, q)
            b = call_mimo(args.model, grounded_sys, q)
            a["trial"] = trial; a["question"] = q
            b["trial"] = trial; b["question"] = q; b["hits"] = hits
            cold.append(a)
            retrieved.append(b)
            # Judge each
            cold_scores.append(judge_score(args.model, q, a["output"]))
            retrieved_scores.append(judge_score(args.model, q, b["output"]))

    def avg(xs):
        xs = [x for x in xs if x is not None]
        return round(statistics.mean(xs), 3) if xs else None

    def summarise(rs):
        return {
            "input_total": sum(r["prompt_tokens"] for r in rs),
            "output_total": sum(r["completion_tokens"] for r in rs),
            "total": sum(r["prompt_tokens"] + r["completion_tokens"] for r in rs),
            "input_mean": round(statistics.mean(r["prompt_tokens"] for r in rs), 1),
            "output_mean": round(statistics.mean(r["completion_tokens"] for r in rs), 1),
        }

    s_cold = summarise(cold)
    s_ret = summarise(retrieved)
    summary = {
        "harness": "runner_wiki.py",
        "n": args.n,
        "n_questions": len(QUESTIONS),
        "model": args.model,
        "cold": s_cold,
        "retrieved": s_ret,
        "judge_cold_mean": avg(cold_scores),
        "judge_retrieved_mean": avg(retrieved_scores),
        "judge_delta": (avg(retrieved_scores) - avg(cold_scores)) if avg(cold_scores) is not None and avg(retrieved_scores) is not None else None,
        "delta_input_pct": round(100 * (s_ret["input_total"] - s_cold["input_total"]) / max(s_cold["input_total"], 1), 2),
        "delta_output_pct": round(100 * (s_ret["output_total"] - s_cold["output_total"]) / max(s_cold["output_total"], 1), 2),
        "delta_total_pct": round(100 * (s_ret["total"] - s_cold["total"]) / max(s_cold["total"], 1), 2),
    }
    results = {"summary": summary, "questions": QUESTIONS, "cold": cold, "retrieved": retrieved}
    out_path = REPO_ROOT / args.out
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(results, indent=2))

    print(f"\n=== wiki-memory ({len(QUESTIONS)} questions × {args.n} trials, {args.model}) ===")
    print(f"  cold      input={s_cold['input_total']:5}  output={s_cold['output_total']:5}  total={s_cold['total']:5}  judge={summary['judge_cold_mean']}")
    print(f"  retrieved input={s_ret['input_total']:5}  output={s_ret['output_total']:5}  total={s_ret['total']:5}  judge={summary['judge_retrieved_mean']}")
    print(f"  Δinput:  {summary['delta_input_pct']:+.1f}%  (retrieval adds context cost)")
    print(f"  Δoutput: {summary['delta_output_pct']:+.1f}%  (grounding may shorten or lengthen)")
    print(f"  Δtotal:  {summary['delta_total_pct']:+.1f}%")
    print(f"  Δjudge:  {summary['judge_delta']:+.2f}  (higher = better with retrieval)" if summary['judge_delta'] is not None else "  Δjudge:  —")
    print(f"  results: {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
