#!/usr/bin/env python3
"""LLM-as-judge for skill A/B output quality.

Default: local Ollama (gemma4:26b). Override with --model.
For Xiaomi MiMo via HF inference, set HF_TOKEN env var and pass --backend hf --model XiaomiMiMo/MiMo-7B.

Score: integer 0-5 against a rubric.
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
from typing import Any


OLLAMA_URL = "http://127.0.0.1:11434/api/generate"

DEFAULT_RUBRIC = """\
Rate the candidate output from 0 to 5 on whether it addresses the task correctly and concisely.

5 = correct, on-point, no filler
4 = correct, minor verbosity
3 = mostly correct, some filler or minor error
2 = partial answer, notable errors
1 = mostly wrong or off-topic
0 = blank, hallucinated, or refused

Respond with exactly one digit 0-5 on the first line, then a short reason on the next line.
"""


def judge_ollama(model: str, task_prompt: str, candidate: str, rubric: str) -> dict[str, Any]:
    system = "You are an evaluation judge. Be strict, fair, terse."
    body = (
        f"TASK:\n{task_prompt}\n\n"
        f"CANDIDATE:\n{candidate}\n\n"
        f"RUBRIC:\n{rubric}\n"
    )
    req_body = json.dumps({
        "model": model,
        "system": system,
        "prompt": body,
        "stream": False,
        "options": {"temperature": 0.0},
    }).encode()
    req = urllib.request.Request(OLLAMA_URL, data=req_body, headers={"Content-Type": "application/json"})
    t0 = time.time()
    with urllib.request.urlopen(req, timeout=300) as resp:
        data = json.loads(resp.read())
    out = data.get("response", "").strip()
    score = None
    for line in out.splitlines():
        line = line.strip()
        if line and line[0].isdigit():
            try:
                score = int(line[0])
                break
            except ValueError:
                pass
    return {"score": score, "raw": out, "latency_ms": int((time.time() - t0) * 1000)}


def judge_mimo(model: str, task_prompt: str, candidate: str, rubric: str) -> dict[str, Any]:
    """Judge via the official Xiaomi MiMo API (OpenAI-compatible).

    Prefer mimo-v2-flash for judging — it returns the rating directly without
    spending tokens on reasoning_content. The v2.5* family burns all available
    completion_tokens on reasoning_content for non-trivial inputs, leaving the
    visible content field empty.
    """
    key = os.environ.get("MIMO_API_KEY")
    if not key:
        raise RuntimeError("MIMO_API_KEY not set (source .token-economy/secrets.env)")
    base = os.environ.get("MIMO_BASE_URL", "https://api.xiaomimimo.com/v1").rstrip("/")
    body = json.dumps({
        "model": model,
        "messages": [
            {"role": "system", "content": "You are an evaluation judge. Be strict, fair, terse."},
            {"role": "user", "content": f"TASK:\n{task_prompt}\n\nCANDIDATE:\n{candidate}\n\nRUBRIC:\n{rubric}"},
        ],
        "max_tokens": 200,
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
    out = data["choices"][0]["message"]["content"].strip()
    score = None
    for line in out.splitlines():
        line = line.strip()
        if line and line[0].isdigit():
            try:
                score = int(line[0])
                break
            except ValueError:
                pass
    return {"score": score, "raw": out, "latency_ms": int((time.time() - t0) * 1000)}


def judge_hf(model: str, task_prompt: str, candidate: str, rubric: str) -> dict[str, Any]:
    """Stub for HF Inference API. Requires HF_TOKEN env var."""
    token = os.environ.get("HF_TOKEN")
    if not token:
        raise RuntimeError("HF_TOKEN not set; cannot use HF backend.")
    url = f"https://api-inference.huggingface.co/models/{model}"
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    body = json.dumps({
        "inputs": f"TASK: {task_prompt}\n\nCANDIDATE: {candidate}\n\nRUBRIC: {rubric}",
        "parameters": {"temperature": 0.0, "max_new_tokens": 80},
    }).encode()
    req = urllib.request.Request(url, data=body, headers=headers)
    t0 = time.time()
    with urllib.request.urlopen(req, timeout=300) as resp:
        data = json.loads(resp.read())
    out = (data[0]["generated_text"] if isinstance(data, list) else data.get("generated_text", "")).strip()
    score = None
    for line in out.splitlines():
        line = line.strip()
        if line and line[0].isdigit():
            try:
                score = int(line[0])
                break
            except ValueError:
                pass
    return {"score": score, "raw": out, "latency_ms": int((time.time() - t0) * 1000)}


def judge_results(results_path: Path, model: str, backend: str) -> dict[str, Any]:
    results = json.loads(results_path.read_text())
    rubric = results.get("rubric", DEFAULT_RUBRIC)
    if backend == "ollama":
        judge_fn = judge_ollama
    elif backend == "mimo":
        judge_fn = judge_mimo
    else:
        judge_fn = judge_hf

    def score_set(items: list[dict], prompts: list[str]) -> list[dict]:
        scored = []
        for it in items:
            prompt = prompts[it["prompt_idx"]]
            j = judge_fn(model, prompt, it["output"], rubric)
            scored.append({"prompt_idx": it["prompt_idx"], **j})
        return scored

    # We need the prompts; load the task yaml referenced by skill+id
    # Simpler: results doesn't carry prompts back. Caller should pass them.
    # For MVP, embed prompts in results during runner.run_task.
    if "prompts" not in results:
        raise RuntimeError("results JSON missing 'prompts'; re-run runner.py with newer version.")
    prompts = results["prompts"]
    scored_without = score_set(results["without_skill"], prompts)
    scored_with = score_set(results["with_skill"], prompts)
    valid_w = [s["score"] for s in scored_without if s["score"] is not None]
    valid_s = [s["score"] for s in scored_with if s["score"] is not None]
    out = {
        "judge_model": model,
        "judge_backend": backend,
        "scored_without_skill": scored_without,
        "scored_with_skill": scored_with,
        "judge_summary": {
            "without_mean": statistics.mean(valid_w) if valid_w else None,
            "with_mean": statistics.mean(valid_s) if valid_s else None,
            "delta": (statistics.mean(valid_s) - statistics.mean(valid_w)) if valid_w and valid_s else None,
        },
    }
    return out


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("results")
    p.add_argument("--model", default="mimo-v2-flash")
    p.add_argument("--backend", default="mimo", choices=["ollama", "hf", "mimo"])
    args = p.parse_args()

    results_path = Path(args.results)
    if not results_path.exists():
        print(f"not found: {results_path}", file=sys.stderr)
        return 2
    judged = judge_results(results_path, args.model, args.backend)

    out_path = results_path.with_suffix(".judged.json")
    out_path.write_text(json.dumps(judged, indent=2))
    s = judged["judge_summary"]
    print(f"\n=== judge: {args.model} ({args.backend}) ===")
    print(f"  without skill: {s['without_mean']}")
    print(f"  with skill:    {s['with_mean']}")
    print(f"  delta:         {s['delta']}")
    print(f"  results: {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
