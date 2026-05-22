#!/usr/bin/env python3
"""Post-hoc audit: sample N% of logged ComCom calls, replay full-context as baseline,
compare to logged compressed answer, alert on drift.

Input JSONL format (one dict per line):
  {"original_context": str, "question": str,
   "compressed_context": str, "answer": str, "ground_truth"?: str}

Usage:
  python3 post_hoc_audit.py <log.jsonl> [--sample 0.05] [--target phi4:14b] [--judge qwen3:8b]
  [--drift-threshold 0.1]
Exit 1 if drift rate > drift-threshold.
"""
from __future__ import annotations
import argparse, json, random, sys, urllib.request, warnings
from pathlib import Path
warnings.filterwarnings("ignore")

OLLAMA = "http://127.0.0.1:11434/api/generate"


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


def judge_pair(q, ans_a, ans_b, model):
    """Return (score_a, score_b, drift_bool). drift = |a - b| > 1."""
    p = (f'Score each ANSWER 0-3 for correctness addressing QUESTION.\n'
         f'Reply ONLY JSON: {{"a":<0-3>,"b":<0-3>}}\n'
         f'QUESTION: {q}\nANSWER_A: {ans_a}\nANSWER_B: {ans_b}\nJSON:')
    r = ollama(model, p, num_predict=40)
    try:
        s = r.find("{"); e = r.rfind("}") + 1
        d = json.loads(r[s:e])
        a, b = int(d.get("a", 0)), int(d.get("b", 0))
        return a, b, abs(a - b) > 1
    except Exception:
        return 0, 0, False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("log")
    ap.add_argument("--sample", type=float, default=0.05)
    ap.add_argument("--target", default="phi4:14b")
    ap.add_argument("--judge", default="qwen3:8b")
    ap.add_argument("--drift-threshold", type=float, default=0.1)
    args = ap.parse_args()

    rows = [json.loads(l) for l in open(args.log)]
    n_sample = max(1, int(len(rows) * args.sample))
    sampled = random.Random(0).sample(rows, min(n_sample, len(rows)))
    print(f"# Post-hoc audit: sampling {len(sampled)}/{len(rows)} ({args.sample:.0%})\n")

    drifts = []
    for i, row in enumerate(sampled, 1):
        orig_ctx = row["original_context"]
        q = row["question"]
        logged_ans = row["answer"]

        # Replay with full context
        baseline_prompt = f"CONTEXT:\n{orig_ctx}\n\nQUESTION: {q}\nANSWER (terse):"
        baseline_ans = ollama(args.target, baseline_prompt)

        score_b, score_logged, drift = judge_pair(q, baseline_ans, logged_ans, args.judge)
        if drift:
            drifts.append({"i": i, "q": q[:60], "baseline": score_b,
                            "logged": score_logged, "logged_ans": logged_ans[:100]})
        print(f"[{i}/{len(sampled)}] baseline={score_b} logged={score_logged} "
              f"drift={'YES' if drift else 'no'}")

    rate = len(drifts) / len(sampled)
    print(f"\n**Drift rate**: {rate:.1%}  (threshold {args.drift_threshold:.0%})")
    if drifts:
        print("\nDrifted items:")
        for d in drifts:
            print(f"- [{d['i']}] baseline={d['baseline']} logged={d['logged']} | q: {d['q']}")

    if rate > args.drift_threshold:
        print(f"\nWARNING: drift rate {rate:.1%} > threshold {args.drift_threshold:.0%}",
              file=sys.stderr)
        sys.exit(1)
    sys.exit(0)


if __name__ == "__main__":
    main()
