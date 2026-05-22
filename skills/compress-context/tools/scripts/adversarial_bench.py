#!/usr/bin/env python3
"""Adversarial regression bench for ComCom.

Runs the adversarial QA set through full-ctx vs compressed, judges via Ollama,
reports mean-score delta with bootstrap 95% CI, exits non-zero on regression.

Suitable for CI: exit 1 if Δscore < regression_threshold.

Usage:
  python3 adversarial_bench.py [--threshold -0.3] [--target phi4:14b] [--judge qwen3:8b]
"""
from __future__ import annotations
import argparse, json, random, statistics, sys, time, urllib.request, warnings
from pathlib import Path
warnings.filterwarnings("ignore")

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT))

from pipeline_v2 import compress

OLLAMA = "http://127.0.0.1:11434/api/generate"
DATA = ROOT.parent.parent / "bench/data/adversarial_qa_10.json"


def ollama(model, prompt, num_predict=200):
    if "qwen3" in model: prompt += " /no_think"
    data = json.dumps({"model": model, "prompt": prompt, "stream": False, "think": False,
                        "options": {"num_predict": num_predict, "temperature": 0.0, "seed": 42}}).encode()
    req = urllib.request.Request(OLLAMA, data=data,
                                  headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=180) as r:
            return json.loads(r.read()).get("response", "").strip()
    except Exception as e:
        return f"[gen_error: {e}]"


def judge(q, gt, ans, model):
    p = (f'Score ANSWER 0-3 vs GROUND_TRUTH for QUESTION. '
         f'3=correct+complete, 2=correct core, 1=partial, 0=wrong.\n'
         f'Reply ONLY JSON: {{"score":<0-3>}}\nQUESTION: {q}\nGROUND_TRUTH: {gt}\nMODEL_ANSWER: {ans}\nJSON:')
    r = ollama(model, p, num_predict=30)
    try:
        s = r.find("{"); e = r.rfind("}") + 1
        return int(json.loads(r[s:e]).get("score", 0))
    except Exception:
        return 0


def bootstrap_ci(vals, n_boot=2000, ci=0.95):
    if not vals: return (0, 0, 0)
    rng = random.Random(0)
    bs = sorted(sum(rng.choice(vals) for _ in vals)/len(vals) for _ in range(n_boot))
    return (statistics.mean(vals), bs[int((1-ci)/2*n_boot)], bs[int((1+ci)/2*n_boot)])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--threshold", type=float, default=-0.3)
    ap.add_argument("--target", default="phi4:14b")
    ap.add_argument("--judge", default="qwen3:8b")
    ap.add_argument("--rate", type=float, default=0.5)
    ap.add_argument("--data", default=str(DATA))
    args = ap.parse_args()

    items = json.loads(Path(args.data).read_text())
    print(f"# Adversarial Regression Bench (N={len(items)}, target={args.target})")
    print()
    print(f"| id | question | full_score | comp_score | Δ |")
    print(f"|---|---|---:|---:|---:|")

    deltas = []
    full_scores, comp_scores = [], []
    for item in items:
        ctx = item["context"]; q = item["question"]; gt = item["answer"]
        full_prompt = f"CONTEXT:\n{ctx}\n\nQUESTION: {q}\nANSWER (terse):"
        full_ans = ollama(args.target, full_prompt)
        full_s = judge(q, gt, full_ans, args.judge)

        comp_ctx, _ = compress(ctx, question=q, rate=args.rate)
        comp_prompt = f"CONTEXT:\n{comp_ctx}\n\nQUESTION: {q}\nANSWER (terse):"
        comp_ans = ollama(args.target, comp_prompt)
        comp_s = judge(q, gt, comp_ans, args.judge)

        d = comp_s - full_s
        deltas.append(d); full_scores.append(full_s); comp_scores.append(comp_s)
        q_short = q[:40].replace("|", "\\|")
        print(f"| {item.get('id','?')} | {q_short} | {full_s} | {comp_s} | {d:+d} |")

    mean_full = statistics.mean(full_scores)
    mean_comp = statistics.mean(comp_scores)
    mean_d, lo, hi = bootstrap_ci(deltas)
    print()
    print(f"**mean full** = {mean_full:.2f}, **mean compressed** = {mean_comp:.2f}")
    print(f"**Δ score** = {mean_d:+.2f}  95% CI = [{lo:+.2f}, {hi:+.2f}]")
    print(f"**threshold** = {args.threshold}")

    if mean_d < args.threshold:
        print(f"\nREGRESSION: mean Δ {mean_d:+.2f} < threshold {args.threshold}", file=sys.stderr)
        sys.exit(1)
    print("\nOK: no regression")
    sys.exit(0)


if __name__ == "__main__":
    main()
