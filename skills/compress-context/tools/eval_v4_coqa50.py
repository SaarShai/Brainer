"""Eval-v4: N=50 CoQA items, 3 conditions, bootstrap 95% CI.

Target: phi4:14b. Judge: qwen3:8b. Both via Ollama.
Conditions:
  A_full      — full context baseline
  B_v1        — compress v1 rate=0.5 (no question awareness)
  C_v2_safe   — compress v2 rate=0.7 (gentle + question-aware + crit-zone)

Note: skipping C_v2 rate=0.5 (known-broken in v3) and D_adaptive (costs too much
  wall time at N=50 with escalation chains). C_v2_safe at 0.7 is what's actually
  recommended for personal use.
"""
import argparse, json, random, statistics, time, urllib.request, warnings
from pathlib import Path
warnings.filterwarnings("ignore")

from pipeline import run_pipeline as run_v1
from pipeline_v2 import compress as compress_v2

OLLAMA = "http://127.0.0.1:11434/api/generate"
TARGET = "phi4:14b"
JUDGE = "qwen3:8b"

TARGET_PROMPT = "CONTEXT:\n{ctx}\n\nQUESTION: {q}\nANSWER (terse, factual, 1-2 sentences, no preamble):"

JUDGE_PROMPT = """Score MODEL_ANSWER 0-3 vs GROUND_TRUTH for QUESTION.
3=correct+complete, 2=correct core, 1=partial, 0=wrong.
Mode: NONE=3, MISSING, SWAP, NOISE, REFUSE.
ONLY JSON: {{"score":<0-3>,"mode":"<MODE>"}}

QUESTION: {q}
GROUND_TRUTH: {gt}
MODEL_ANSWER: {ans}"""


def ollama(model, prompt, num_predict=200):
    if "qwen3" in model: prompt += " /no_think"
    data = json.dumps({"model": model, "prompt": prompt, "stream": False,
                       "think": False,
                       "options": {"num_predict": num_predict, "temperature": 0.0, "seed": 42}}).encode()
    req = urllib.request.Request(OLLAMA, data=data, headers={"Content-Type": "application/json"})
    t0 = time.time()
    with urllib.request.urlopen(req, timeout=300) as r:
        out = json.loads(r.read())
    return {"text": out.get("response", "").strip(),
            "prompt_tokens": out.get("prompt_eval_count", 0),
            "latency": time.time() - t0}


def judge(q, gt, ans):
    p = JUDGE_PROMPT.format(q=q, gt=gt, ans=ans)
    o = ollama(JUDGE, p, num_predict=60)
    raw = o["text"]
    try:
        s = raw.find("{"); e = raw.rfind("}") + 1
        obj = json.loads(raw[s:e])
        return int(obj.get("score", 0)), obj.get("mode", "NOISE")
    except:
        return 0, "PARSE_FAIL"


def bootstrap_ci(vals, n_boot=2000, ci=0.95):
    if not vals: return (0, 0, 0)
    rng = random.Random(0)
    boots = sorted(sum(rng.choice(vals) for _ in vals)/len(vals) for _ in range(n_boot))
    return (statistics.mean(vals), boots[int((1-ci)/2*n_boot)], boots[int((1+ci)/2*n_boot)])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--items", default="/tmp/tokecon-coqa-50/coqa_50.jsonl")
    ap.add_argument("--n", type=int, default=50)
    ap.add_argument("--log", default="eval_v4_log.jsonl")
    args = ap.parse_args()

    items = [json.loads(l) for l in open(args.items)][:args.n]
    print(f"N={len(items)} target={TARGET} judge={JUDGE}")

    results = []
    log_fh = open(args.log, "w")
    for i, item in enumerate(items):
        ctx = item["context"]; q = item["question"]; gt = item["answer"]

        # A: full
        a_prompt = TARGET_PROMPT.format(ctx=ctx, q=q)
        a = ollama(TARGET, a_prompt)
        a_score, a_mode = judge(q, gt, a["text"])

        # B: v1 rate=0.5
        stages = run_v1(ctx, rate=0.5, use_llmlingua=True)
        b_ctx = stages[2][1]
        b_prompt = TARGET_PROMPT.format(ctx=b_ctx, q=q)
        b = ollama(TARGET, b_prompt)
        b_score, b_mode = judge(q, gt, b["text"])

        # C: v2 rate=0.7 (safe, recommended)
        c_ctx, c_stats = compress_v2(ctx, question=q, rate=0.7)
        c_prompt = TARGET_PROMPT.format(ctx=c_ctx, q=q)
        c = ollama(TARGET, c_prompt)
        c_score, c_mode = judge(q, gt, c["text"])

        rec = {"i": i, "id": item["id"], "turn": item["meta"]["turn"],
               "a_tok": a["prompt_tokens"], "a_score": a_score, "a_mode": a_mode,
               "b_tok": b["prompt_tokens"], "b_score": b_score, "b_mode": b_mode,
               "c_tok": c["prompt_tokens"], "c_score": c_score, "c_mode": c_mode,
               "a_ans": a["text"][:120], "b_ans": b["text"][:120], "c_ans": c["text"][:120]}
        results.append(rec)
        log_fh.write(json.dumps(rec) + "\n"); log_fh.flush()
        elapsed = (time.time() - T0) / 60
        print(f"[{i+1}/{len(items)}] a={a['prompt_tokens']}t/{a_score} "
              f"b={b['prompt_tokens']}t/{b_score} c={c['prompt_tokens']}t/{c_score} "
              f"[{elapsed:.1f}min]")

    log_fh.close()

    print("\n" + "="*60)
    print(f"{'cond':<6} {'mean_tok':>10} {'score (CI)':>24} {'savings vs A':>14}")
    print("-"*60)
    for cond, a_tok, a_sc in [("A_full", "a_tok", "a_score"),
                               ("B_v1", "b_tok", "b_score"),
                               ("C_v2_safe", "c_tok", "c_score")]:
        toks = [r[a_tok] for r in results]
        scores = [r[a_sc] for r in results]
        savings = [1 - r[a_tok]/r["a_tok"] for r in results]
        sci = bootstrap_ci(scores); sav = bootstrap_ci(savings)
        print(f"{cond:<6} {statistics.mean(toks):>10.1f} "
              f"{sci[0]:>7.2f} [{sci[1]:.2f},{sci[2]:.2f}]   {sav[0]*100:>10.1f}%")

    print("\nΔscore vs A_full (paired):")
    for cond, sc in [("B_v1", "b_score"), ("C_v2_safe", "c_score")]:
        deltas = [r[sc] - r["a_score"] for r in results]
        d = bootstrap_ci(deltas)
        print(f"  {cond:<12} Δ={d[0]:+.2f}  95%CI=[{d[1]:+.2f},{d[2]:+.2f}]")

    print("\nFailure modes:")
    for cond, m in [("A_full", "a_mode"), ("B_v1", "b_mode"), ("C_v2_safe", "c_mode")]:
        from collections import Counter
        print(f"  {cond:<12} {dict(Counter(r[m] for r in results))}")


if __name__ == "__main__":
    T0 = time.time()
    main()
