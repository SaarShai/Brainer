#!/usr/bin/env python3
"""Quality eval: compressed vs original context, task answers via Ollama.

For each task: run pipeline, send both versions + question to model, compare answers
and token counts. Scores via exact-match or containment on expected-answer keywords.
"""
import argparse, json, time, urllib.request, warnings
warnings.filterwarnings("ignore")
import tiktoken
from pipeline import run_pipeline, count_tokens

OLLAMA = "http://127.0.0.1:11434/api/generate"

TASKS = [
    {
        "name": "auth-bug-extraction",
        "context_file": "samples/verbose_prose.txt",
        "question": "What file and line has the bug, and what exactly should be changed?",
        "expected_keywords": ["42", "middleware", "<=", "<"],
    },
    {
        "name": "react-rerender",
        "context_file": "samples/mixed_technical.txt",
        "question": "Why does the component re-render unnecessarily, and what single React technique fixes it?",
        "expected_keywords": ["object", "reference", "useMemo"],
    },
    {
        "name": "perf-target",
        "context_file": "samples/mixed_technical.txt",
        "question": "Current render time vs target, in ms?",
        "expected_keywords": ["250", "50"],
    },
    # LONG-INPUT TASKS (caveman README ~3K tokens)
    {
        "name": "long-levels",
        "context_file": "samples/long_readme.txt",
        "question": "What are all the intensity/mode levels caveman supports? List them.",
        "expected_keywords": ["lite", "full", "ultra"],
    },
    {
        "name": "long-savings",
        "context_file": "samples/long_readme.txt",
        "question": "What measured output-token savings does caveman claim, give the average percent.",
        "expected_keywords": ["65", "%"],
    },
    {
        "name": "long-rules",
        "context_file": "samples/long_readme.txt",
        "question": "Name three categories of words caveman drops.",
        "expected_keywords": ["article", "filler", "pleasant"],
    },
    # CODE-GEN TASK
    {
        "name": "codegen-test",
        "context_file": "samples/verbose_prose.txt",
        "question": "Write a one-line test assertion (jest/expect style) that verifies a token exactly at expiry is rejected.",
        "expected_keywords": ["expect", "false", "validateToken"],
    },
]

def ask_ollama(model, prompt, num_predict=400):
    # qwen3: /no_think disables thinking tokens. Safe for other models (ignored).
    if "qwen3" in model:
        prompt = prompt + " /no_think"
    data = json.dumps({
        "model": model,
        "prompt": prompt,
        "stream": False,
        "think": False,
        "options": {"num_predict": num_predict, "temperature": 0.1},
    }).encode()
    req = urllib.request.Request(OLLAMA, data=data, headers={"Content-Type": "application/json"})
    t0 = time.time()
    with urllib.request.urlopen(req, timeout=180) as resp:
        out = json.loads(resp.read())
    return out.get("response", ""), time.time() - t0

def score(answer, keywords):
    hits = sum(1 for k in keywords if k.lower() in answer.lower())
    return hits, len(keywords)

def run_task(task, model, rate):
    ctx = open(task["context_file"]).read()
    stages = run_pipeline(ctx, rate=rate, use_llmlingua=True)
    compressed = stages[2][1]  # +llmlingua
    orig_tok = stages[0][2]
    comp_tok = stages[2][2]

    # structured-output stage: brevity hint shortens model output, no accuracy loss expected
    prompt_template = "CONTEXT:\n{ctx}\n\nQUESTION: {q}\nANSWER (terse, factual, no preamble, no disclaimers):"
    p_orig = prompt_template.format(ctx=ctx, q=task["question"])
    p_comp = prompt_template.format(ctx=compressed, q=task["question"])

    ans_o, t_o = ask_ollama(model, p_orig)
    ans_c, t_c = ask_ollama(model, p_comp)

    so, total = score(ans_o, task["expected_keywords"])
    sc, _ = score(ans_c, task["expected_keywords"])

    return {
        "task": task["name"],
        "orig_tok": orig_tok, "comp_tok": comp_tok,
        "savings": 1 - comp_tok/orig_tok,
        "orig_score": so, "comp_score": sc, "total": total,
        "orig_ans": ans_o.strip()[:200], "comp_ans": ans_c.strip()[:200],
        "orig_lat": t_o, "comp_lat": t_c,
    }

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="qwen3:8b")
    ap.add_argument("--rate", type=float, default=0.7)
    args = ap.parse_args()

    print(f"model={args.model}  llmlingua_rate={args.rate}\n")
    results = []
    for t in TASKS:
        print(f"→ {t['name']}")
        r = run_task(t, args.model, args.rate)
        results.append(r)
        print(f"  tokens: orig={r['orig_tok']} comp={r['comp_tok']} savings={r['savings']:.1%}")
        print(f"  score:  orig={r['orig_score']}/{r['total']} comp={r['comp_score']}/{r['total']}")
        print(f"  latency: orig={r['orig_lat']:.1f}s comp={r['comp_lat']:.1f}s")
        print(f"  orig ans: {r['orig_ans']}")
        print(f"  comp ans: {r['comp_ans']}")
        print()

    tot_orig = sum(r["orig_score"] for r in results)
    tot_comp = sum(r["comp_score"] for r in results)
    tot_max  = sum(r["total"] for r in results)
    tot_ot   = sum(r["orig_tok"] for r in results)
    tot_ct   = sum(r["comp_tok"] for r in results)
    print(f"\nAGGREGATE: orig={tot_orig}/{tot_max}  comp={tot_comp}/{tot_max}  "
          f"token-savings={1-tot_ct/tot_ot:.1%}  quality-retention={tot_comp/max(tot_orig,1):.1%}")

if __name__ == "__main__":
    main()
