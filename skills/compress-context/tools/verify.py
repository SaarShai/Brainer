"""Self-verify: cheap grounding check on a generated answer.

Flow:
  gen_answer(question, compressed_ctx) → answer
  verify(question, answer, full_ctx) → {grounded: bool, missing: str|None}

If not grounded: caller escalates (higher rate or full ctx).
"""
import json, urllib.request

OLLAMA = "http://127.0.0.1:11434/api/generate"

VERIFY_PROMPT = """Check if ANSWER is grounded in CONTEXT and fully addresses QUESTION.

Return ONLY JSON on one line:
{{"grounded": true|false, "reason": "<short>"}}

Rules:
- grounded=false if ANSWER contradicts CONTEXT (fact swap)
- grounded=false if ANSWER misses the key fact needed to answer QUESTION
- grounded=true if ANSWER is consistent with CONTEXT and addresses QUESTION

QUESTION: {q}
CONTEXT: {ctx}
ANSWER: {ans}

JSON:"""


def verify(question: str, answer: str, context: str, model: str = "qwen3:8b",
           max_ctx_chars: int = 6000) -> dict:
    ctx = context[:max_ctx_chars]
    prompt = VERIFY_PROMPT.format(q=question, ctx=ctx, ans=answer)
    if "qwen3" in model:
        prompt += " /no_think"
    data = json.dumps({
        "model": model, "prompt": prompt, "stream": False,
        "think": False,
        "options": {"num_predict": 100, "temperature": 0.0},
    }).encode()
    req = urllib.request.Request(OLLAMA, data=data,
                                  headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            out = json.loads(r.read())
        raw = out.get("response", "")
        start = raw.find("{"); end = raw.rfind("}") + 1
        if start >= 0 and end > start:
            obj = json.loads(raw[start:end])
            return {"grounded": bool(obj.get("grounded", False)),
                    "reason": obj.get("reason", "")[:200],
                    "tokens": out.get("prompt_eval_count", 0) + out.get("eval_count", 0)}
    except Exception as e:
        return {"grounded": True, "reason": f"verify_error:{e}", "tokens": 0}
    return {"grounded": True, "reason": "parse_fail", "tokens": 0}


def escalate_gen(question, context, gen_fn, verify_fn=None,
                 rates=(0.5, 0.7, None), verify_model="qwen3:8b"):
    """Run gen at compressed rates, verify, escalate until grounded.

    Args:
      gen_fn(ctx) -> answer  — calls target model
      verify_fn defaults to self-verify with compressed context + original

    Returns (answer, meta) with meta = {rate_used, attempts, total_verify_tokens, grounded}
    """
    from pipeline_v2 import compress
    attempts = []
    total_verify_tok = 0

    for rate in rates:
        if rate is None:
            ctx = context
            stats = {"savings": 0.0, "final": None}
        else:
            ctx, stats = compress(context, question=question, rate=rate)
        ans = gen_fn(ctx)
        v = verify(question, ans, context, model=verify_model) if (verify_fn is None) else verify_fn(question, ans, context)
        total_verify_tok += v.get("tokens", 0)
        attempts.append({"rate": rate, "stats": stats, "grounded": v["grounded"],
                         "reason": v["reason"], "answer": ans[:200]})
        if v["grounded"]:
            return ans, {"rate_used": rate, "attempts": attempts,
                         "total_verify_tokens": total_verify_tok, "grounded": True}

    return ans, {"rate_used": None, "attempts": attempts,
                 "total_verify_tokens": total_verify_tok, "grounded": False}
