#!/usr/bin/env python3
"""Eval-v3: CC upgrade — question-aware + critical-zone + self-verify escalation.

Compares 4 conditions per item:
  A. full context (baseline)
  B. compressed v1 (rate=0.5, no question awareness)
  C. compressed v2 (rate=0.5, question + critical-zone protection)
  D. adaptive (v2 rate=0.5 → verify → if fail rate=0.7 → if fail full)

Each × 2 runs. LLM-as-judge (qwen3:8b). Report savings, quality, Δscore with CIs.
"""
import argparse, json, random, statistics, time, urllib.request, warnings
from pathlib import Path
warnings.filterwarnings("ignore")

from pipeline import run_pipeline as run_v1
from pipeline_v2 import compress as compress_v2
from verify import escalate_gen, verify as verify_fn

OLLAMA = "http://127.0.0.1:11434/api/generate"
JUDGE_MODEL = "qwen3:8b"
TARGET_MODEL = "phi4:14b"

JUDGE_PROMPT = """You are a strict evaluator. Score MODEL_ANSWER 0-3 vs GROUND_TRUTH for QUESTION.
3=correct+complete, 2=correct core, 1=partial/wrong-add, 0=wrong/refuse.
Mode: NONE(=3) | MISSING | SWAP | NOISE | REFUSE.
Respond ONLY one-line JSON:
{{"score":<0-3>,"mode":"<MODE>"}}

QUESTION: {q}
GROUND_TRUTH: {gt}
MODEL_ANSWER: {ans}"""

TARGET_PROMPT = "CONTEXT:\n{ctx}\n\nQUESTION: {q}\nANSWER (terse, factual, one-two sentences, no preamble):"


def ollama(model, prompt, num_predict=300):
    if "qwen3" in model:
        prompt += " /no_think"
    data = json.dumps({
        "model": model, "prompt": prompt, "stream": False, "think": False,
        "options": {"num_predict": num_predict, "temperature": 0.0, "seed": 42},
    }).encode()
    req = urllib.request.Request(OLLAMA, data=data,
                                  headers={"Content-Type": "application/json"})
    t0 = time.time()
    with urllib.request.urlopen(req, timeout=300) as r:
        out = json.loads(r.read())
    return {"text": out.get("response", "").strip(),
            "prompt_tokens": out.get("prompt_eval_count", 0),
            "completion_tokens": out.get("eval_count", 0),
            "latency": time.time() - t0}


def judge(q, gt, ans):
    p = JUDGE_PROMPT.format(q=q, gt=gt, ans=ans)
    out = ollama(JUDGE_MODEL, p, num_predict=60)
    raw = out["text"]
    try:
        s = raw.find("{"); e = raw.rfind("}") + 1
        o = json.loads(raw[s:e])
        return int(o.get("score", 0)), o.get("mode", "NOISE")
    except Exception:
        return 0, "PARSE_FAIL"


def load_squad(n, seed=0):
    from datasets import load_dataset
    ds = load_dataset("rajpurkar/squad_v2", split="validation")
    answerable = [x for x in ds if x["answers"]["text"]]
    random.Random(seed).shuffle(answerable)
    items = []
    for x in answerable[:n*3]:
        if len(items) >= n: break
        if 300 <= len(x["context"]) <= 3000:
            items.append({"id": x["id"], "context": x["context"],
                          "question": x["question"],
                          "answer": x["answers"]["text"][0]})
    return items[:n]


def bootstrap_ci(values, n_boot=2000, ci=0.95):
    if not values: return (0, 0, 0)
    rng = random.Random(0)
    boots = [sum(rng.choice(values) for _ in values)/len(values) for _ in range(n_boot)]
    boots.sort()
    lo = boots[int((1-ci)/2 * n_boot)]
    hi = boots[int((1+ci)/2 * n_boot)]
    return (statistics.mean(values), lo, hi)


def make_gen_fn(question):
    """Returns gen_fn(ctx) -> answer, capturing target-model call tokens."""
    call_log = []
    def fn(ctx):
        prompt = TARGET_PROMPT.format(ctx=ctx, q=question)
        o = ollama(TARGET_MODEL, prompt)
        call_log.append(o)
        return o["text"]
    return fn, call_log


def run_condition(item, cond, log_fh, run_idx):
    ctx = item["context"]; q = item["question"]; gt = item["answer"]

    if cond == "A_full":
        prompt = TARGET_PROMPT.format(ctx=ctx, q=q)
        gen = ollama(TARGET_MODEL, prompt)
        tokens_in = gen["prompt_tokens"]; ans = gen["text"]
        meta = {"rate": 1.0, "attempts": 1, "verify_tok": 0}

    elif cond == "B_v1":
        stages = run_v1(ctx, rate=0.5, use_llmlingua=True)
        comp_ctx = stages[2][1]
        prompt = TARGET_PROMPT.format(ctx=comp_ctx, q=q)
        gen = ollama(TARGET_MODEL, prompt)
        tokens_in = gen["prompt_tokens"]; ans = gen["text"]
        meta = {"rate": 0.5, "attempts": 1, "verify_tok": 0}

    elif cond == "C_v2":
        comp_ctx, cstats = compress_v2(ctx, question=q, rate=0.5)
        prompt = TARGET_PROMPT.format(ctx=comp_ctx, q=q)
        gen = ollama(TARGET_MODEL, prompt)
        tokens_in = gen["prompt_tokens"]; ans = gen["text"]
        meta = {"rate": 0.5, "attempts": 1, "verify_tok": 0,
                "crit_sent": cstats["critical_sentences"]}

    elif cond == "D_adaptive":
        gen_fn, _ = make_gen_fn(q)
        ans, am = escalate_gen(q, ctx, gen_fn, rates=(0.5, 0.7, None))
        # Token accounting: sum target-model prompts for all attempts + verify calls
        total_in = 0
        for att in am["attempts"]:
            if att["stats"].get("final") is not None:
                total_in += att["stats"]["final"]
            else:
                # full-ctx fallback: count with tiktoken approx
                import tiktoken
                total_in += len(tiktoken.get_encoding("cl100k_base").encode(ctx))
        tokens_in = total_in
        meta = {"rate": am["rate_used"], "attempts": len(am["attempts"]),
                "verify_tok": am["total_verify_tokens"],
                "grounded": am["grounded"]}

    score, mode = judge(q, gt, ans)
    rec = {"item_id": item["id"], "cond": cond, "run": run_idx,
           "tokens_in": tokens_in, "score": score, "mode": mode,
           "answer": ans[:200], "meta": meta}
    log_fh.write(json.dumps(rec) + "\n"); log_fh.flush()
    print(f"  [{cond}] item {item['id'][:8]} run {run_idx}: "
          f"tok={tokens_in} score={score} mode={mode} "
          f"{'rate='+str(meta.get('rate'))}")
    return rec


def summarize(records):
    conds = ["A_full", "B_v1", "C_v2", "D_adaptive"]
    by_item = {}
    for r in records:
        by_item.setdefault((r["item_id"], r["cond"]), []).append(r)

    print("\n" + "="*70)
    print(f"{'cond':<12} {'tokens (mean)':>16} {'score (mean CI)':>22} {'savings vs A':>14}")
    print("-"*70)

    summary = {}
    # baseline
    a_toks = []
    a_scores = []
    for (iid, c), rs in by_item.items():
        if c == "A_full":
            a_toks.append(statistics.mean([r["tokens_in"] for r in rs]))
            a_scores.append(statistics.mean([r["score"] for r in rs]))

    for cond in conds:
        toks, scores, savings = [], [], []
        modes = {}
        items = sorted({iid for (iid, c) in by_item if c == cond})
        for iid in items:
            rs = by_item.get((iid, cond), [])
            if not rs: continue
            toks.append(statistics.mean([r["tokens_in"] for r in rs]))
            scores.append(statistics.mean([r["score"] for r in rs]))
            for r in rs: modes[r["mode"]] = modes.get(r["mode"], 0) + 1
            # savings vs A for same item
            ars = by_item.get((iid, "A_full"), [])
            if ars:
                at = statistics.mean([r["tokens_in"] for r in ars])
                savings.append(1 - toks[-1]/at)

        if not toks: continue
        m_tok = statistics.mean(toks)
        sci = bootstrap_ci(scores)
        sav = bootstrap_ci(savings) if savings else (0,0,0)
        print(f"{cond:<12} {m_tok:>16.1f} {sci[0]:>10.2f} [{sci[1]:.2f},{sci[2]:.2f}] {sav[0]*100:>12.1f}%")
        summary[cond] = {"tokens": m_tok, "score": sci, "savings": sav, "modes": modes}

    # Δscore vs A_full, per-item paired
    print("\nDelta vs A_full (paired per-item):")
    for cond in conds[1:]:
        deltas = []
        for iid in sorted({iid for (iid, c) in by_item if c == cond}):
            a = by_item.get((iid, "A_full"), [])
            x = by_item.get((iid, cond), [])
            if a and x:
                deltas.append(statistics.mean([r["score"] for r in x]) -
                              statistics.mean([r["score"] for r in a]))
        if deltas:
            d = bootstrap_ci(deltas)
            print(f"  {cond:<12} Δ={d[0]:+.2f}  95%CI=[{d[1]:+.2f}, {d[2]:+.2f}]")

    print("\nFailure modes:")
    for cond in conds:
        s = summary.get(cond, {})
        print(f"  {cond:<12} {s.get('modes', {})}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=8)
    ap.add_argument("--runs", type=int, default=2)
    ap.add_argument("--log", default="eval_v3_log.jsonl")
    args = ap.parse_args()

    items = load_squad(args.n)
    print(f"loaded {len(items)} items")
    conds = ["A_full", "B_v1", "C_v2", "D_adaptive"]
    all_recs = []
    with open(args.log, "w") as log_fh:
        for cond in conds:
            print(f"\n--- {cond} ---")
            for i, item in enumerate(items):
                for r in range(args.runs):
                    all_recs.append(run_condition(item, cond, log_fh, r))
    summarize(all_recs)


if __name__ == "__main__":
    main()
