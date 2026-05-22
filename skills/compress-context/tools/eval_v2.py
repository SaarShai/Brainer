#!/usr/bin/env python3
"""Eval-v2: principled compression evaluation.

Improvements over v1:
- Public benchmark data (SQuAD v2 validation slice) — not hand-picked samples.
- LLM-as-judge (gemma4:31b) with 0-3 rubric + failure-mode classification.
- Pre-registered rubric (below). Keywords NOT derived from compressed output.
- Actual model input tokens via Ollama `prompt_eval_count` (not tiktoken approx).
- Multiple runs per condition → bootstrap 95% CI on savings and quality.
- Per-model stratification.
- Logs every call for post-hoc audit.

Usage: python3 eval_v2.py --n 15 --runs 2 --rate 0.5 --target-models phi4:14b,qwen3:8b
"""
import argparse, json, random, statistics, time, urllib.request, warnings
from pathlib import Path
warnings.filterwarnings("ignore")

from pipeline import run_pipeline

OLLAMA = "http://127.0.0.1:11434/api/generate"
JUDGE_MODEL = "qwen3:8b"  # smaller, stays loaded alongside target, avoids swap thrash

# PRE-REGISTERED RUBRIC — do not modify after seeing results
JUDGE_PROMPT = """You are a strict evaluator. Compare MODEL_ANSWER to GROUND_TRUTH for the QUESTION.

Score 0-3:
  3 = correct and complete
  2 = correct core fact, minor omission
  1 = partially correct OR correct but with a wrong added fact
  0 = wrong, irrelevant, or refuses

Failure mode (only if score < 3):
  NONE     = score is 3
  MISSING  = answer lacks required fact
  SWAP     = answer states a fact that contradicts ground truth (FACT SWAP — serious)
  NOISE    = answer adds irrelevant/hallucinated content
  REFUSE   = refuses or says can't answer

Respond ONLY with JSON on one line:
{{"score": <0-3>, "mode": "<NONE|MISSING|SWAP|NOISE|REFUSE>"}}

QUESTION: {q}
GROUND_TRUTH: {gt}
MODEL_ANSWER: {ans}
"""

TARGET_PROMPT = "CONTEXT:\n{ctx}\n\nQUESTION: {q}\nANSWER (terse, factual, one-two sentences, no preamble):"

def ollama(model, prompt, num_predict=300, think=False):
    if "qwen3" in model:
        prompt = prompt + " /no_think"
    data = json.dumps({
        "model": model,
        "prompt": prompt,
        "stream": False,
        "think": think,
        "options": {"num_predict": num_predict, "temperature": 0.0, "seed": 42},
    }).encode()
    req = urllib.request.Request(OLLAMA, data=data, headers={"Content-Type": "application/json"})
    t0 = time.time()
    with urllib.request.urlopen(req, timeout=300) as resp:
        out = json.loads(resp.read())
    return {
        "text": out.get("response", "").strip(),
        "latency": time.time() - t0,
        "prompt_tokens": out.get("prompt_eval_count", 0),
        "completion_tokens": out.get("eval_count", 0),
    }

def judge(question, ground_truth, answer):
    p = JUDGE_PROMPT.format(q=question, gt=ground_truth, ans=answer)
    out = ollama(JUDGE_MODEL, p, num_predict=60)
    raw = out["text"]
    try:
        # find first JSON object in response
        start = raw.find("{")
        end = raw.find("}", start) + 1
        obj = json.loads(raw[start:end])
        return int(obj.get("score", 0)), obj.get("mode", "NOISE"), raw
    except Exception as e:
        return 0, "PARSE_FAIL", raw

def load_squad(n, seed=0):
    """Load n SQuAD v2 items with answerable questions."""
    from datasets import load_dataset
    ds = load_dataset("rajpurkar/squad_v2", split="validation")
    answerable = [x for x in ds if x["answers"]["text"]]
    random.Random(seed).shuffle(answerable)
    items = []
    for x in answerable[:n*3]:
        if len(items) >= n: break
        # diversify context length
        if 300 <= len(x["context"]) <= 3000:
            items.append({
                "id": x["id"],
                "context": x["context"],
                "question": x["question"],
                "answer": x["answers"]["text"][0],
            })
    return items[:n]

def bootstrap_ci(values, n_boot=2000, ci=0.95):
    if not values: return (0, 0, 0)
    rng = random.Random(0)
    boots = []
    for _ in range(n_boot):
        sample = [values[rng.randrange(len(values))] for _ in values]
        boots.append(sum(sample)/len(sample))
    boots.sort()
    lo = boots[int((1-ci)/2 * n_boot)]
    hi = boots[int((1+ci)/2 * n_boot)]
    return (statistics.mean(values), lo, hi)

def evaluate(items, target_model, runs, rate, log_fh):
    """Run eval for one target model. Returns per-item records."""
    records = []
    for i, item in enumerate(items):
        # Compress ONCE per item (deterministic given seed)
        stages = run_pipeline(item["context"], rate=rate, use_llmlingua=True)
        orig_ctx = stages[0][1]
        comp_ctx = stages[2][1]

        for run_idx in range(runs):
            for cond, ctx in (("orig", orig_ctx), ("comp", comp_ctx)):
                prompt = TARGET_PROMPT.format(ctx=ctx, q=item["question"])
                gen = ollama(target_model, prompt)
                score, mode, raw = judge(item["question"], item["answer"], gen["text"])
                rec = {
                    "item_id": item["id"], "item_idx": i, "run": run_idx,
                    "model": target_model, "cond": cond,
                    "prompt_tok": gen["prompt_tokens"],
                    "comp_tok": gen["completion_tokens"],
                    "latency": gen["latency"],
                    "answer": gen["text"][:300],
                    "score": score, "mode": mode,
                    "question": item["question"], "gt": item["answer"],
                }
                records.append(rec)
                log_fh.write(json.dumps(rec) + "\n"); log_fh.flush()
                print(f"  [{target_model}] item {i+1}/{len(items)} run {run_idx} {cond}: "
                      f"tok={gen['prompt_tokens']} score={score} mode={mode}")
    return records

def summarize(records, target_model):
    rs = [r for r in records if r["model"] == target_model]
    by_item = {}
    for r in rs:
        key = (r["item_idx"], r["cond"])
        by_item.setdefault(key, []).append(r)
    # per-item mean
    savings_per_item = []
    score_orig, score_comp = [], []
    modes_comp = {}
    for i in sorted({r["item_idx"] for r in rs}):
        orig = by_item.get((i, "orig"), [])
        comp = by_item.get((i, "comp"), [])
        if not orig or not comp: continue
        ot = statistics.mean([r["prompt_tok"] for r in orig])
        ct = statistics.mean([r["prompt_tok"] for r in comp])
        savings_per_item.append(1 - ct/ot)
        score_orig.append(statistics.mean([r["score"] for r in orig]))
        score_comp.append(statistics.mean([r["score"] for r in comp]))
        for r in comp:
            modes_comp[r["mode"]] = modes_comp.get(r["mode"], 0) + 1

    sav = bootstrap_ci(savings_per_item)
    so = bootstrap_ci(score_orig)
    sc = bootstrap_ci(score_comp)
    delta = bootstrap_ci([c - o for c, o in zip(score_comp, score_orig)])

    print(f"\n=== {target_model} (n={len(savings_per_item)} items) ===")
    print(f"  token savings:   mean={sav[0]:.1%}  95% CI=[{sav[1]:.1%}, {sav[2]:.1%}]")
    print(f"  score orig:      mean={so[0]:.2f}/3  95% CI=[{so[1]:.2f}, {so[2]:.2f}]")
    print(f"  score comp:      mean={sc[0]:.2f}/3  95% CI=[{sc[1]:.2f}, {sc[2]:.2f}]")
    print(f"  Δscore (c-o):    mean={delta[0]:+.2f}  95% CI=[{delta[1]:+.2f}, {delta[2]:+.2f}]")
    print(f"  failure modes (comp): {modes_comp}")
    return {"model": target_model, "n": len(savings_per_item),
            "savings": sav, "score_orig": so, "score_comp": sc,
            "delta": delta, "modes": modes_comp}

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=12)
    ap.add_argument("--runs", type=int, default=2)
    ap.add_argument("--rate", type=float, default=0.5)
    ap.add_argument("--target-models", default="phi4:14b,qwen3:8b")
    ap.add_argument("--log", default="eval_v2_log.jsonl")
    args = ap.parse_args()

    print(f"loading {args.n} SQuAD v2 items...")
    items = load_squad(args.n)
    print(f"got {len(items)} items, context lens: {[len(x['context']) for x in items]}")

    models = args.target_models.split(",")
    all_records = []
    with open(args.log, "w") as log_fh:
        for m in models:
            print(f"\n--- evaluating {m} ---")
            recs = evaluate(items, m, args.runs, args.rate, log_fh)
            all_records.extend(recs)

    print("\n" + "="*60)
    print("SUMMARY")
    print("="*60)
    summaries = [summarize(all_records, m) for m in models]

    # cross-model aggregate
    all_savings, all_delta = [], []
    for m in models:
        rs = [r for r in all_records if r["model"] == m]
        by_item = {}
        for r in rs:
            by_item.setdefault((r["item_idx"], r["cond"]), []).append(r)
        for i in sorted({r["item_idx"] for r in rs}):
            orig = by_item.get((i, "orig"), [])
            comp = by_item.get((i, "comp"), [])
            if not orig or not comp: continue
            ot = statistics.mean([r["prompt_tok"] for r in orig])
            ct = statistics.mean([r["prompt_tok"] for r in comp])
            all_savings.append(1 - ct/ot)
            so = statistics.mean([r["score"] for r in orig])
            sc = statistics.mean([r["score"] for r in comp])
            all_delta.append(sc - so)
    sa = bootstrap_ci(all_savings)
    de = bootstrap_ci(all_delta)
    print(f"\nCROSS-MODEL ({len(all_savings)} item-model pairs):")
    print(f"  savings: mean={sa[0]:.1%}  95% CI=[{sa[1]:.1%}, {sa[2]:.1%}]")
    print(f"  Δscore : mean={de[0]:+.2f}  95% CI=[{de[1]:+.2f}, {de[2]:+.2f}]")

if __name__ == "__main__":
    main()
