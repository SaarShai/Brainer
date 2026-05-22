#!/usr/bin/env python3
"""End-to-end measurement for the prompt-triage hook skill.

Method:
  For each prompt in a corpus:
    A. WITHOUT triage: send prompt to the "expensive" model. Measure tokens.
    B. WITH triage: run classify.py. Use the tier output to route:
         simple/medium -> "cheap" model
         hard/unknown  -> "expensive" model
       Send the prompt to the routed model. Measure tokens.
  Sum across the corpus. Output:
    - total tokens A vs B
    - per-tier hit rate (classifier predictions vs ground-truth labels)
    - routing decisions and savings

Usage:
  python3 eval/runner_triage.py \
    --corpus eval/tasks/prompt-triage-corpus.yaml \
    --cheap mimo-v2-flash \
    --expensive mimo-v2.5-pro \
    --n 3
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


def call_mimo(model: str, prompt: str, system: str = "You are a helpful coding assistant.") -> dict:
    key = os.environ["MIMO_API_KEY"]
    base = os.environ.get("MIMO_BASE_URL", "https://api.xiaomimimo.com/v1").rstrip("/")
    max_tokens = 800 if "pro" in model else 400
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
    with urllib.request.urlopen(req, timeout=120) as resp:
        data = json.loads(resp.read())
    msg = data["choices"][0]["message"]
    usage = data.get("usage", {})
    return {
        "output": (msg.get("content") or "").strip(),
        "prompt_tokens": usage.get("prompt_tokens", 0),
        "completion_tokens": usage.get("completion_tokens", 0),
        "latency_ms": int((time.time() - t0) * 1000),
    }


def classify_prompt(prompt: str, classify_script: Path, no_ollama: bool = True) -> dict:
    """Invoke classify.py and parse its JSON output."""
    env = os.environ.copy()
    if no_ollama:
        env["AGENTS_TRIAGE_NO_OLLAMA"] = "1"
    t0 = time.time()
    try:
        # classify.py reads JSON from stdin: {"prompt": "..."}
        proc = subprocess.run(
            [sys.executable, str(classify_script)],
            input=json.dumps({"prompt": prompt}),
            capture_output=True,
            text=True,
            timeout=10,
            env=env,
        )
        out = proc.stdout.strip()
        if not out:
            return {"tier": "unknown", "agent": "none", "model": "opus", "confidence": 0.0, "reason": "no output", "_classify_ms": int((time.time() - t0) * 1000)}
        data = json.loads(out.splitlines()[-1])
        data["_classify_ms"] = int((time.time() - t0) * 1000)
        return data
    except Exception as e:
        return {"tier": "unknown", "agent": "none", "model": "opus", "confidence": 0.0, "reason": f"err:{e}", "_classify_ms": int((time.time() - t0) * 1000)}


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--corpus", required=True, help="YAML with `prompts` list, each {text, expected_tier}")
    p.add_argument("--cheap", default="mimo-v2-flash")
    p.add_argument("--expensive", default="mimo-v2.5-pro")
    p.add_argument("--n", type=int, default=1)
    p.add_argument("--out", default="eval/results/prompt-triage.json")
    p.add_argument("--no-ollama", action="store_true", default=True, help="regex fast-path only")
    args = p.parse_args()

    if yaml is None:
        print("PyYAML required", file=sys.stderr)
        return 2

    corpus = yaml.safe_load(Path(args.corpus).read_text())
    classify_script = Path(__file__).resolve().parents[1] / "skills/prompt-triage/tools/classify.py"

    results = {
        "corpus": args.corpus,
        "cheap_model": args.cheap,
        "expensive_model": args.expensive,
        "n": args.n,
        "prompts": [p["text"] for p in corpus["prompts"]],
        "expected_tiers": [p["expected_tier"] for p in corpus["prompts"]],
        "without_triage": [],
        "with_triage": [],
        "classifications": [],
    }

    # WITHOUT triage: route every prompt to expensive
    for trial in range(args.n):
        for i, p_item in enumerate(corpus["prompts"]):
            r = call_mimo(args.expensive, p_item["text"])
            r["trial"] = trial
            r["prompt_idx"] = i
            r["routed_to"] = args.expensive
            results["without_triage"].append(r)

    # WITH triage: classify each prompt, route accordingly. Classification once per
    # prompt (deterministic regex), generation N times.
    for i, p_item in enumerate(corpus["prompts"]):
        cls = classify_prompt(p_item["text"], classify_script, no_ollama=args.no_ollama)
        cls["prompt_idx"] = i
        cls["expected_tier"] = p_item["expected_tier"]
        results["classifications"].append(cls)
        # route by tier
        tier = cls.get("tier", "unknown")
        target = args.cheap if tier in ("simple", "medium") else args.expensive
        for trial in range(args.n):
            r = call_mimo(target, p_item["text"])
            r["trial"] = trial
            r["prompt_idx"] = i
            r["routed_to"] = target
            r["classified_tier"] = tier
            results["with_triage"].append(r)

    # Aggregate
    def sum_tokens(rs):
        return {
            "prompt_total": sum(r["prompt_tokens"] for r in rs),
            "completion_total": sum(r["completion_tokens"] for r in rs),
            "total": sum(r["prompt_tokens"] + r["completion_tokens"] for r in rs),
            "latency_total_ms": sum(r["latency_ms"] for r in rs),
        }

    wo = sum_tokens(results["without_triage"])
    wi = sum_tokens(results["with_triage"])
    correct = sum(
        1 for c in results["classifications"]
        if c.get("tier") == c.get("expected_tier")
    )
    n_prompts = len(results["classifications"])
    results["summary"] = {
        "without_triage": wo,
        "with_triage": wi,
        "delta_total_tokens": wi["total"] - wo["total"],
        "delta_total_pct": round(100 * (wi["total"] - wo["total"]) / max(wo["total"], 1), 2),
        "classification_accuracy": round(correct / max(n_prompts, 1), 3),
        "classification_ms_mean": round(statistics.mean(c.get("_classify_ms", 0) for c in results["classifications"]), 1),
        "routing": {
            args.cheap: sum(1 for r in results["with_triage"] if r["routed_to"] == args.cheap),
            args.expensive: sum(1 for r in results["with_triage"] if r["routed_to"] == args.expensive),
        },
    }

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(results, indent=2))

    s = results["summary"]
    print(f"\n=== prompt-triage (n={args.n} x {n_prompts} prompts) ===")
    print(f"  classification accuracy: {s['classification_accuracy']:.0%}")
    print(f"  classify time (mean):    {s['classification_ms_mean']:.0f} ms")
    print(f"  routing: cheap={s['routing'][args.cheap]} / expensive={s['routing'][args.expensive]}")
    print(f"  total tokens WITHOUT triage: {wo['total']}")
    print(f"  total tokens WITH    triage: {wi['total']}")
    print(f"  delta:                       {s['delta_total_tokens']:+d} ({s['delta_total_pct']:+.1f}%)")
    print(f"  results: {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
