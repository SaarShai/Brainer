#!/usr/bin/env python3
"""A/B runner for skill evaluation.

For an in-context skill, runs the model twice on each task:
  1. Without the skill body in the system prompt.
  2. With the skill body prepended to the system prompt.

Captures input/output token counts, latency, and (optional) judge score.

Usage:
  python eval/runner.py --task eval/tasks/caveman-ultra.yaml --n 5
  python eval/runner.py --combo eval/combos/triage+caveman+keeper.yaml --n 5
  python eval/runner.py --task <yaml> --n 10 --judge gemma4:26b --model phi4:14b
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from pathlib import Path
from typing import Any

# Optional YAML
try:
    import yaml
except ImportError:
    yaml = None

import os
import urllib.request
import urllib.error

OLLAMA_URL = "http://127.0.0.1:11434/api/generate"


def call_ollama(model: str, system: str, prompt: str) -> dict[str, Any]:
    body = json.dumps({
        "model": model,
        "system": system,
        "prompt": prompt,
        "stream": False,
        "options": {"temperature": 0.0},
    }).encode()
    req = urllib.request.Request(OLLAMA_URL, data=body, headers={"Content-Type": "application/json"})
    t0 = time.time()
    with urllib.request.urlopen(req, timeout=300) as resp:
        data = json.loads(resp.read())
    return {
        "output": data.get("response", ""),
        "latency_ms": int((time.time() - t0) * 1000),
        "prompt_eval_count": data.get("prompt_eval_count", 0),
        "eval_count": data.get("eval_count", 0),
    }


def _openai_compat_chat(url: str, key: str, model: str, system: str, prompt: str) -> dict[str, Any]:
    """Shared call for OpenAI-compatible /chat/completions endpoints (MIMO, MLX server)."""
    body = json.dumps({
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": prompt},
        ],
        "max_tokens": 1024,
        "temperature": 0.0,
    }).encode()
    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"} if key else {"Content-Type": "application/json"}
    req = urllib.request.Request(url, data=body, headers=headers)
    t0 = time.time()
    try:
        with urllib.request.urlopen(req, timeout=180) as resp:
            data = json.loads(resp.read())
    except urllib.error.HTTPError as e:
        err = e.read().decode()
        raise RuntimeError(f"{url} {e.code}: {err}") from e
    text = data["choices"][0]["message"]["content"]
    usage = data.get("usage", {})
    return {
        "output": text,
        "latency_ms": int((time.time() - t0) * 1000),
        "prompt_eval_count": usage.get("prompt_tokens", 0),
        "eval_count": usage.get("completion_tokens", 0),
    }


def call_mimo(model: str, system: str, prompt: str) -> dict[str, Any]:
    key = os.environ.get("MIMO_API_KEY")
    if not key:
        raise RuntimeError("MIMO_API_KEY not set (source .brainer/secrets.env)")
    base = os.environ.get("MIMO_BASE_URL", "https://api.xiaomimimo.com/v1").rstrip("/")
    return _openai_compat_chat(f"{base}/chat/completions", key, model, system, prompt)


def call_mlx(model: str, system: str, prompt: str) -> dict[str, Any]:
    """Call the local MLX server (start with: python3 -m mlx_lm server --host 127.0.0.1 --port 8082)."""
    base = os.environ.get("MLX_BASE_URL", "http://127.0.0.1:8082/v1").rstrip("/")
    return _openai_compat_chat(f"{base}/chat/completions", "", model, system, prompt)


def call_anthropic(model: str, system: str, prompt: str) -> dict[str, Any]:
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        raise RuntimeError("ANTHROPIC_API_KEY not set")
    base = os.environ.get("ANTHROPIC_BASE_URL", "https://api.anthropic.com").rstrip("/")
    url = f"{base}/v1/messages"
    body = json.dumps({
        "model": model,
        "max_tokens": 1024,
        "system": system,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.0,
    }).encode()
    req = urllib.request.Request(url, data=body, headers={
        "x-api-key": key,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    })
    t0 = time.time()
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            data = json.loads(resp.read())
    except urllib.error.HTTPError as e:
        err = e.read().decode()
        raise RuntimeError(f"anthropic {e.code}: {err}") from e
    text_parts = [c.get("text", "") for c in data.get("content", []) if c.get("type") == "text"]
    usage = data.get("usage", {})
    return {
        "output": "".join(text_parts),
        "latency_ms": int((time.time() - t0) * 1000),
        "prompt_eval_count": usage.get("input_tokens", 0),
        "eval_count": usage.get("output_tokens", 0),
    }


def call_model(backend: str, model: str, system: str, prompt: str) -> dict[str, Any]:
    if backend == "ollama":
        return call_ollama(model, system, prompt)
    if backend == "anthropic":
        return call_anthropic(model, system, prompt)
    if backend == "mimo":
        return call_mimo(model, system, prompt)
    if backend == "mlx":
        return call_mlx(model, system, prompt)
    raise ValueError(f"unknown backend: {backend}")


def load_yaml(path: Path) -> dict[str, Any]:
    if yaml is None:
        raise RuntimeError("PyYAML required: pip install PyYAML")
    return yaml.safe_load(path.read_text())


def load_skill_body(skill_name: str, repo_root: Path) -> str:
    skill_md = repo_root / "skills" / skill_name / "SKILL.md"
    if not skill_md.exists():
        raise FileNotFoundError(f"SKILL.md not found: {skill_md}")
    text = skill_md.read_text()
    # Strip frontmatter; we want the protocol body for in-context loading.
    if text.startswith("---"):
        end = text.find("\n---\n", 4)
        if end != -1:
            text = text[end + 5:]
    return text.strip()


def run_task(task: dict, model: str, n: int, repo_root: Path, backend: str = "ollama") -> dict[str, Any]:
    """Run an A/B for one task n times. Returns aggregate stats."""
    skill_names = task["skills"] if isinstance(task.get("skills"), list) else [task["skill"]]
    base_system = task.get("system", "You are a helpful coding assistant.")

    # Compose the skill-loaded system message
    skill_bodies = [load_skill_body(s, repo_root) for s in skill_names]
    with_skill_system = base_system + "\n\n" + "\n\n---\n\n".join(skill_bodies)

    prompts = task["prompts"]
    results = {
        "task_id": task["id"],
        "skills": skill_names,
        "model": model,
        "n": n,
        "prompts": prompts,
        "rubric": task.get("rubric"),
        "without_skill": [],
        "with_skill": [],
    }

    for i in range(n):
        for j, p in enumerate(prompts):
            without = call_model(backend, model, base_system, p)
            with_ = call_model(backend, model, with_skill_system, p)
            results["without_skill"].append({"trial": i, "prompt_idx": j, **without})
            results["with_skill"].append({"trial": i, "prompt_idx": j, **with_})

    def summarize(rs: list[dict]) -> dict:
        return {
            "input_tokens_mean": statistics.mean(r["prompt_eval_count"] for r in rs),
            "output_tokens_mean": statistics.mean(r["eval_count"] for r in rs),
            "latency_ms_mean": statistics.mean(r["latency_ms"] for r in rs),
            "input_tokens_total": sum(r["prompt_eval_count"] for r in rs),
            "output_tokens_total": sum(r["eval_count"] for r in rs),
        }

    results["summary"] = {
        "without_skill": summarize(results["without_skill"]),
        "with_skill": summarize(results["with_skill"]),
    }
    s = results["summary"]
    out_delta = s["with_skill"]["output_tokens_mean"] - s["without_skill"]["output_tokens_mean"]
    s["delta_output_tokens"] = out_delta
    s["delta_output_pct"] = round(100 * out_delta / max(s["without_skill"]["output_tokens_mean"], 1), 2)
    in_delta = s["with_skill"]["input_tokens_mean"] - s["without_skill"]["input_tokens_mean"]
    s["delta_input_tokens"] = in_delta
    s["delta_input_pct"] = round(100 * in_delta / max(s["without_skill"]["input_tokens_mean"], 1), 2)
    return results


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--task")
    p.add_argument("--combo")
    p.add_argument("--n", type=int, default=5)
    p.add_argument("--backend", default="ollama", choices=["ollama", "anthropic", "mimo", "mlx"])
    p.add_argument("--model", default="phi4:14b")
    p.add_argument("--judge", default=None, help="optional judge model (e.g. gemma4:26b)")
    p.add_argument("--out", default=None, help="output JSON path; default eval/results/<task-id>.json")
    args = p.parse_args()

    if not args.task and not args.combo:
        p.error("--task or --combo required")

    yaml_path = Path(args.task or args.combo)
    task = load_yaml(yaml_path)
    repo_root = Path(__file__).resolve().parents[1]
    results = run_task(task, args.model, args.n, repo_root, backend=args.backend)

    out_path = Path(args.out or f"eval/results/{task['id']}.json")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(results, indent=2))

    s = results["summary"]
    print(f"\n=== {task['id']} (n={args.n} × {len(task['prompts'])} prompts, model={args.model}) ===")
    print(f"  input tokens:  {s['without_skill']['input_tokens_mean']:.0f} → {s['with_skill']['input_tokens_mean']:.0f} ({s['delta_input_pct']:+.1f}%)")
    print(f"  output tokens: {s['without_skill']['output_tokens_mean']:.0f} → {s['with_skill']['output_tokens_mean']:.0f} ({s['delta_output_pct']:+.1f}%)")
    print(f"  latency (ms):  {s['without_skill']['latency_ms_mean']:.0f} → {s['with_skill']['latency_ms_mean']:.0f}")
    print(f"  results: {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
