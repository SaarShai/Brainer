#!/usr/bin/env python3
"""Ollama port of eval/runner_triage.py (which is MiMo-hardcoded).

The tracked eval/runner_triage.py reads os.environ["MIMO_API_KEY"] for BOTH the
"cheap" and "expensive" generation calls and has no Ollama path, so it cannot run
on a Kaggle T4 with a local Ollama server. We don't edit tracked repo files, so
this sibling shipped under eval/kaggle_ollama/ reproduces the same measurement
against Ollama:

  - WITHOUT triage: route every prompt to the "expensive" model.
  - WITH triage: run skills/prompt-triage/tools/classify.py (regex fast-path via
    AGENTS_TRIAGE_NO_OLLAMA=1) to get a tier, route simple/medium -> cheap,
    hard/unknown -> expensive. Generate, measure tokens.

On a single T4 the natural mapping is cheap==expensive==qwen2.5:7b-instruct (one
model loaded), so the token *savings* signal will be ~0 unless you pass two
distinct local models; the classification-accuracy + routing-decision metrics are
still meaningful. Pass --cheap/--expensive to use two models if both fit in VRAM.

Usage:
  python3 runner_ollama_triage.py \
    --corpus eval/tasks/prompt-triage-corpus.yaml \
    --classify skills/prompt-triage/tools/classify.py \
    --cheap qwen2.5:7b-instruct --expensive qwen2.5:7b-instruct \
    --n 50 --out /kaggle/working/eval-results/prompt-triage.json
"""
from __future__ import annotations

import argparse
import json
import os
import statistics
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

try:
    import yaml
except ImportError:
    yaml = None

OLLAMA_URL = "http://127.0.0.1:11434/api/generate"


def call_ollama(model: str, prompt: str, system: str = "You are a helpful coding assistant.") -> dict:
    body = json.dumps({
        "model": model,
        "system": system,
        "prompt": prompt,
        "stream": False,
        "options": {"temperature": 0.0},
    }).encode()
    req = urllib.request.Request(OLLAMA_URL, data=body, headers={"Content-Type": "application/json"})
    t0 = time.time()
    try:
        with urllib.request.urlopen(req, timeout=300) as resp:
            data = json.loads(resp.read())
        return {
            "output": (data.get("response") or "").strip(),
            "prompt_tokens": data.get("prompt_eval_count", 0),
            "completion_tokens": data.get("eval_count", 0),
            "latency_ms": int((time.time() - t0) * 1000),
        }
    except Exception as e:
        return {
            "output": f"<ERR: {e}>",
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "latency_ms": 0,
            "error": str(e),
        }


def classify_prompt(prompt: str, classify_script: Path) -> dict:
    env = os.environ.copy()
    env["AGENTS_TRIAGE_NO_OLLAMA"] = "1"  # regex fast-path; deterministic, offline
    t0 = time.time()
    try:
        proc = subprocess.run(
            [sys.executable, str(classify_script)],
            input=json.dumps({"prompt": prompt}),
            capture_output=True, text=True, timeout=10, env=env,
        )
        out = proc.stdout.strip()
        if not out:
            return {"tier": "unknown", "_classify_ms": int((time.time() - t0) * 1000), "reason": "no output"}
        data = json.loads(out.splitlines()[-1])
        data["_classify_ms"] = int((time.time() - t0) * 1000)
        return data
    except Exception as e:
        return {"tier": "unknown", "_classify_ms": int((time.time() - t0) * 1000), "reason": f"err:{e}"}


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--corpus", required=True)
    p.add_argument("--classify", required=True, help="path to skills/prompt-triage/tools/classify.py")
    p.add_argument("--cheap", default="qwen2.5:7b-instruct")
    p.add_argument("--expensive", default="qwen2.5:7b-instruct")
    p.add_argument("--n", type=int, default=1)
    p.add_argument("--out", default="prompt-triage.json")
    args = p.parse_args()

    if yaml is None:
        print("PyYAML required", file=sys.stderr)
        return 2

    corpus = yaml.safe_load(Path(args.corpus).read_text())
    classify_script = Path(args.classify)
    if not classify_script.exists():
        print(f"classify.py not found: {classify_script}", file=sys.stderr)
        return 2

    results = {
        "corpus": args.corpus,
        "backend": "ollama",
        "cheap_model": args.cheap,
        "expensive_model": args.expensive,
        "n": args.n,
        "prompts": [it["text"] for it in corpus["prompts"]],
        "expected_tiers": [it["expected_tier"] for it in corpus["prompts"]],
        "without_triage": [],
        "with_triage": [],
        "classifications": [],
    }

    # WITHOUT triage: everything to expensive.
    for trial in range(args.n):
        for i, it in enumerate(corpus["prompts"]):
            r = call_ollama(args.expensive, it["text"])
            r.update({"trial": trial, "prompt_idx": i, "routed_to": args.expensive})
            results["without_triage"].append(r)

    # WITH triage: classify once per prompt (deterministic), generate N times.
    for i, it in enumerate(corpus["prompts"]):
        cls = classify_prompt(it["text"], classify_script)
        cls["prompt_idx"] = i
        cls["expected_tier"] = it["expected_tier"]
        results["classifications"].append(cls)
        tier = cls.get("tier", "unknown")
        target = args.cheap if tier in ("simple", "medium") else args.expensive
        for trial in range(args.n):
            r = call_ollama(target, it["text"])
            r.update({"trial": trial, "prompt_idx": i, "routed_to": target, "classified_tier": tier})
            results["with_triage"].append(r)

    def sum_tokens(rs):
        return {
            "prompt_total": sum(r["prompt_tokens"] for r in rs),
            "completion_total": sum(r["completion_tokens"] for r in rs),
            "total": sum(r["prompt_tokens"] + r["completion_tokens"] for r in rs),
            "latency_total_ms": sum(r["latency_ms"] for r in rs),
        }

    wo = sum_tokens(results["without_triage"])
    wi = sum_tokens(results["with_triage"])
    correct = sum(1 for c in results["classifications"] if c.get("tier") == c.get("expected_tier"))
    n_prompts = len(results["classifications"])
    results["summary"] = {
        "without_triage": wo,
        "with_triage": wi,
        "delta_total_tokens": wi["total"] - wo["total"],
        "delta_total_pct": round(100 * (wi["total"] - wo["total"]) / max(wo["total"], 1), 2),
        "classification_accuracy": round(correct / max(n_prompts, 1), 3),
        "classification_ms_mean": round(statistics.mean(c.get("_classify_ms", 0) for c in results["classifications"]), 1) if n_prompts else 0,
        "routing": {
            "cheap": sum(1 for r in results["with_triage"] if r["routed_to"] == args.cheap),
            "expensive": sum(1 for r in results["with_triage"] if r["routed_to"] == args.expensive),
        },
    }

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(results, indent=2))

    s = results["summary"]
    print(f"\n=== prompt-triage ollama (n={args.n} x {n_prompts} prompts) ===")
    print(f"  classification accuracy: {s['classification_accuracy']:.0%}")
    print(f"  routing: cheap={s['routing']['cheap']} / expensive={s['routing']['expensive']}")
    print(f"  tokens WITHOUT: {wo['total']}  WITH: {wi['total']}  delta: {s['delta_total_tokens']:+d} ({s['delta_total_pct']:+.1f}%)")
    print(f"  results: {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
