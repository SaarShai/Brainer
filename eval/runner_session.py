#!/usr/bin/env python3
"""Real-session replay harness — the honest catalog-level A/B.

Strips user-turn texts from a real transcript JSONL, then for each prompt
runs it through the model TWICE:
  A. Vanilla system prompt (catalog NOT installed).
  B. Catalog system prompt = SKILLS_INDEX.md prepended (descriptions only,
     mimicking the always-on context tax the catalog imposes).

Then sums input/output tokens across the corpus and reports the net.

This isn't perfect — it loses conversational state and doesn't actually
invoke skill bodies — but it's the closest single-script approximation of
"if I installed this catalog and ran my real workflow, what happens to
token cost?"

Usage:
  python3 eval/runner_session.py <transcript.jsonl> \
    --model mimo-v2-flash --max-prompts 20 --n 1 \
    --backend mimo
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


def extract_text(content) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for b in content:
            if isinstance(b, dict) and "text" in b:
                parts.append(b["text"])
        return "\n".join(parts)
    if isinstance(content, dict) and "text" in content:
        return content["text"]
    return ""


def user_prompts(jsonl_path: Path, max_prompts: int | None = None) -> list[str]:
    out: list[str] = []
    for line in jsonl_path.read_text().splitlines():
        try:
            ev = json.loads(line)
        except Exception:
            continue
        # Claude Code transcript: top-level message with role
        msg = ev.get("message") or ev
        if not isinstance(msg, dict):
            continue
        if msg.get("role") != "user":
            continue
        text = extract_text(msg.get("content", "")).strip()
        if not text or len(text) < 4:
            continue
        # skip system/tool-result content masquerading as user
        if text.startswith("<tool_use_") or text.startswith("Caveat:"):
            continue
        out.append(text)
        if max_prompts and len(out) >= max_prompts:
            break
    return out


def load_catalog_system(repo_root: Path) -> str:
    """Mimic 'catalog installed' by concatenating skill descriptions."""
    skills_dir = repo_root / "skills"
    parts = []
    parts.append("You are a helpful coding assistant. The following skills are available; invoke them by name when their trigger matches the request.\n")
    for d in sorted(skills_dir.iterdir()):
        if not d.is_dir() or d.name.startswith("_"):
            continue
        md = d / "SKILL.md"
        if not md.exists():
            continue
        text = md.read_text()
        # Pull description out of frontmatter
        if text.startswith("---"):
            end = text.find("\n---\n", 4)
            if end != -1:
                fm = text[4:end]
                for line in fm.splitlines():
                    if line.startswith("description:"):
                        desc = line.split(":", 1)[1].strip()
                        parts.append(f"- {d.name}: {desc}")
                        break
    return "\n".join(parts)


def call_mimo(model: str, system: str, prompt: str, retries: int = 3) -> dict:
    key = os.environ["MIMO_API_KEY"]
    base = os.environ.get("MIMO_BASE_URL", "https://api.xiaomimimo.com/v1").rstrip("/")
    body = json.dumps({
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": prompt},
        ],
        "max_tokens": 600,
        "temperature": 0.0,
    }).encode()
    last_err = None
    for attempt in range(retries):
        try:
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
        except Exception as e:
            last_err = e
            time.sleep(2 ** attempt)
    return {"output": f"<err: {last_err}>", "prompt_tokens": 0, "completion_tokens": 0, "latency_ms": 0, "error": str(last_err)}


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("transcript")
    p.add_argument("--model", default="mimo-v2-flash")
    p.add_argument("--backend", default="mimo", choices=["mimo"])
    p.add_argument("--max-prompts", type=int, default=10)
    p.add_argument("--n", type=int, default=1)
    p.add_argument("--out", default="eval/results/session-replay.json")
    args = p.parse_args()

    transcript = Path(args.transcript)
    if not transcript.exists():
        print(f"not found: {transcript}", file=sys.stderr)
        return 2

    repo_root = Path(__file__).resolve().parents[1]
    prompts = user_prompts(transcript, args.max_prompts)
    print(f"[1/3] {len(prompts)} user-prompts extracted from {transcript.name}")

    vanilla_sys = "You are a helpful coding assistant."
    catalog_sys = load_catalog_system(repo_root)
    print(f"[2/3] catalog system prompt: {len(catalog_sys)} chars")

    print(f"[3/3] running {args.n}x {len(prompts)} prompts × 2 conditions = {2 * args.n * len(prompts)} calls")
    no_catalog = []
    with_catalog = []
    for trial in range(args.n):
        for i, p_text in enumerate(prompts):
            print(f"  trial {trial+1}/{args.n} prompt {i+1}/{len(prompts)} no-catalog...", flush=True)
            no_catalog.append(call_mimo(args.model, vanilla_sys, p_text))
            print(f"  trial {trial+1}/{args.n} prompt {i+1}/{len(prompts)} with-catalog...", flush=True)
            with_catalog.append(call_mimo(args.model, catalog_sys, p_text))

    def summarize(rs):
        return {
            "input_total": sum(r["prompt_tokens"] for r in rs),
            "output_total": sum(r["completion_tokens"] for r in rs),
            "total": sum(r["prompt_tokens"] + r["completion_tokens"] for r in rs),
            "latency_total_ms": sum(r["latency_ms"] for r in rs),
            "input_mean": round(statistics.mean(r["prompt_tokens"] for r in rs), 1),
            "output_mean": round(statistics.mean(r["completion_tokens"] for r in rs), 1),
        }

    s_a = summarize(no_catalog)
    s_b = summarize(with_catalog)
    summary = {
        "transcript": str(transcript),
        "model": args.model,
        "n_prompts": len(prompts),
        "n_trials": args.n,
        "catalog_system_chars": len(catalog_sys),
        "no_catalog": s_a,
        "with_catalog": s_b,
        "delta_input_pct": round(100 * (s_b["input_total"] - s_a["input_total"]) / max(s_a["input_total"], 1), 2),
        "delta_output_pct": round(100 * (s_b["output_total"] - s_a["output_total"]) / max(s_a["output_total"], 1), 2),
        "delta_total_pct": round(100 * (s_b["total"] - s_a["total"]) / max(s_a["total"], 1), 2),
    }
    results = {
        "summary": summary,
        "prompts": prompts,
        "no_catalog": no_catalog,
        "with_catalog": with_catalog,
    }
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(results, indent=2))

    print()
    print(f"=== session replay ({len(prompts)} prompts × {args.n} trials, {args.model}) ===")
    print(f"  catalog system prompt: {summary['catalog_system_chars']} chars")
    print(f"  no catalog:   input={s_a['input_total']:6} output={s_a['output_total']:6} total={s_a['total']:6}")
    print(f"  with catalog: input={s_b['input_total']:6} output={s_b['output_total']:6} total={s_b['total']:6}")
    print(f"  Δinput:  {summary['delta_input_pct']:+.1f}%  (catalog adds context cost)")
    print(f"  Δoutput: {summary['delta_output_pct']:+.1f}%  (skill-style behavior)")
    print(f"  Δtotal:  {summary['delta_total_pct']:+.1f}%")
    print(f"  results: {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
