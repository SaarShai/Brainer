#!/usr/bin/env python3
"""Compress-context QUALITY A/B on SQuAD v2 with MiMo as target+judge.

Pairs with `runner_compress.py` (mechanical token-reduction proof) and
`eval_v3.py`/`eval_v4_coqa50.py` (Ollama-coupled). This one runs the
quality side of the with-quality claim — model-answer correctness on
extractive QA — and uses MiMo for both target and judge so it can scale
on Kaggle without an Ollama backend.

Conditions per item:
  A. full context (baseline)
  C. compressed_v2 (question-aware + critical-zone, target rate=0.5)

Metrics: tokens saved, score delta (judge 0-3 → mean), refusal/miss rate.

Usage:
  . .token-economy/secrets.env && export MIMO_API_KEY
  python3 eval/runner_compress_quality.py --n 50 --rate 0.5 \\
      --target mimo-v2-flash --judge mimo-v2-flash
"""
from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "skills" / "compress-context" / "tools"))
sys.path.insert(0, str(REPO_ROOT / "bench"))

TARGET_PROMPT = (
    "CONTEXT:\n{ctx}\n\nQUESTION: {q}\n"
    "ANSWER (terse, factual, 1-2 sentences, no preamble):"
)

JUDGE_PROMPT = (
    "Score MODEL_ANSWER 0-3 vs GROUND_TRUTH for QUESTION.\n"
    "3=correct+complete, 2=correct core, 1=partial, 0=wrong.\n"
    "ONLY one-line JSON: {{\"score\":<0-3>}}\n\n"
    "QUESTION: {q}\nGROUND_TRUTH: {gt}\nMODEL_ANSWER: {ans}"
)


def mimo_chat(model: str, system: str, prompt: str, max_tokens: int = 256) -> dict[str, Any]:
    key = os.environ.get("MIMO_API_KEY")
    if not key:
        raise RuntimeError("MIMO_API_KEY not set (source .token-economy/secrets.env)")
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
    try:
        with urllib.request.urlopen(req, timeout=180) as resp:
            data = json.loads(resp.read())
    except urllib.error.HTTPError as e:
        err = e.read().decode()
        raise RuntimeError(f"mimo {e.code}: {err}") from e
    text = data["choices"][0]["message"]["content"]
    usage = data.get("usage", {})
    return {
        "text": text,
        "latency_ms": int((time.time() - t0) * 1000),
        "prompt_tokens": usage.get("prompt_tokens", 0),
        "completion_tokens": usage.get("completion_tokens", 0),
    }


def judge_score(model: str, q: str, gt: str, ans: str) -> int:
    prompt = JUDGE_PROMPT.format(q=q, gt=gt, ans=ans[:600])
    try:
        out = mimo_chat(model, "You are a strict evaluator.", prompt, max_tokens=64)
    except Exception as e:
        print(f"judge err: {e}", file=sys.stderr)
        return -1
    text = out["text"].strip()
    start = text.find("{")
    end = text.rfind("}")
    if start < 0 or end < 0:
        return -1
    try:
        obj = json.loads(text[start : end + 1])
        s = int(obj.get("score", -1))
        return s if 0 <= s <= 3 else -1
    except Exception:
        return -1


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--n", type=int, default=50, help="number of SQuAD items")
    p.add_argument("--rate", type=float, default=0.5, help="compress target rate")
    p.add_argument("--target", default="mimo-v2-flash")
    p.add_argument("--judge", default="mimo-v2-flash")
    p.add_argument("--out", default="eval/results/compress-context-quality.json")
    args = p.parse_args()

    from pipeline_v2 import compress as compress_v2  # noqa: E402
    from adapters.squad import load as load_squad  # noqa: E402

    print(f"loading SQuAD v2 ({args.n} items)...")
    items = load_squad(n=args.n)
    print(f"loaded {len(items)} items.")

    results = []
    sav_pcts = []
    score_a = []
    score_c = []
    for i, item in enumerate(items):
        q = item["question"]
        gt = item["answer"]
        ctx_full = item["context"]
        try:
            ctx_c, meta = compress_v2(ctx_full, rate=args.rate, question=q)
        except Exception as e:
            print(f"[{i}] compress fail: {e}", file=sys.stderr)
            continue

        try:
            ans_a = mimo_chat(args.target, "", TARGET_PROMPT.format(ctx=ctx_full, q=q))
            ans_c = mimo_chat(args.target, "", TARGET_PROMPT.format(ctx=ctx_c, q=q))
        except Exception as e:
            print(f"[{i}] target fail: {e}", file=sys.stderr)
            continue

        s_a = judge_score(args.judge, q, gt, ans_a["text"])
        s_c = judge_score(args.judge, q, gt, ans_c["text"])

        tok_in = ans_a["prompt_tokens"]
        tok_in_c = ans_c["prompt_tokens"]
        sav = (1 - tok_in_c / max(tok_in, 1)) * 100
        sav_pcts.append(sav)
        if s_a >= 0:
            score_a.append(s_a)
        if s_c >= 0:
            score_c.append(s_c)

        results.append({
            "id": item["id"],
            "q": q,
            "gt": gt,
            "ans_full": ans_a["text"],
            "ans_compressed": ans_c["text"],
            "tokens_full_prompt": tok_in,
            "tokens_compressed_prompt": tok_in_c,
            "savings_pct": round(sav, 1),
            "score_full": s_a,
            "score_compressed": s_c,
            "compress_meta": meta,
        })
        if (i + 1) % 5 == 0:
            print(f"[{i+1}/{len(items)}] mean savings so far: {statistics.mean(sav_pcts):.1f}%")

    summary = {
        "harness": "runner_compress_quality.py",
        "target": args.target,
        "judge": args.judge,
        "n_attempted": len(items),
        "n_scored": len(results),
        "rate": args.rate,
        "mean_savings_pct": round(statistics.mean(sav_pcts), 2) if sav_pcts else None,
        "stdev_savings_pct": round(statistics.stdev(sav_pcts), 2) if len(sav_pcts) > 1 else None,
        "mean_score_full": round(statistics.mean(score_a), 3) if score_a else None,
        "mean_score_compressed": round(statistics.mean(score_c), 3) if score_c else None,
        "delta_score": (
            round(statistics.mean(score_c) - statistics.mean(score_a), 3)
            if score_a and score_c else None
        ),
        "items": results,
    }
    out_path = REPO_ROOT / args.out
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(summary, indent=2))
    print(f"\nwrote {out_path}")
    print(f"mean savings: {summary['mean_savings_pct']}%  "
          f"Δscore: {summary['delta_score']} "
          f"(full={summary['mean_score_full']} -> compressed={summary['mean_score_compressed']})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
