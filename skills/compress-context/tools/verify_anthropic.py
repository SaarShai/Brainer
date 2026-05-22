"""Anthropic-API-backed verify, drop-in replacement for verify.py's Ollama calls.

Same interface as verify.verify() and verify.escalate_gen() — just swap the model.

Usage:
    import os
    os.environ["ANTHROPIC_API_KEY"] = "sk-ant-..."
    from verify_anthropic import verify, escalate_gen_anthropic

    ans, meta = escalate_gen_anthropic(question, context, my_gen_fn,
                                        rates=(0.5, 0.7, None),
                                        verify_model="claude-haiku-4-6")
"""
from __future__ import annotations
import json
import os


VERIFY_PROMPT = """Check if ANSWER is grounded in CONTEXT and fully addresses QUESTION.

Return ONLY JSON on one line:
{"grounded": true|false, "reason": "<short>"}

Rules:
- grounded=false if ANSWER contradicts CONTEXT (fact swap)
- grounded=false if ANSWER misses the key fact needed to answer QUESTION
- grounded=true if ANSWER is consistent with CONTEXT and addresses QUESTION

QUESTION: {q}
CONTEXT: {ctx}
ANSWER: {ans}

JSON:"""


def verify(question: str, answer: str, context: str,
           model: str = "claude-haiku-4-6",
           max_ctx_chars: int = 6000,
           api_key: str | None = None) -> dict:
    """Self-verify an answer using Anthropic Claude. Matches verify.py interface.

    Returns {grounded: bool, reason: str, tokens: int}.
    Defaults to Haiku (cheap). `api_key=None` → uses ANTHROPIC_API_KEY env var.
    """
    try:
        import anthropic
    except ImportError:
        return {"grounded": True, "reason": "anthropic_sdk_missing", "tokens": 0}

    client = anthropic.Anthropic(api_key=api_key or os.environ.get("ANTHROPIC_API_KEY"))
    ctx = context[:max_ctx_chars]
    prompt = VERIFY_PROMPT.format(q=question, ctx=ctx, ans=answer)

    try:
        msg = client.messages.create(
            model=model,
            max_tokens=100,
            temperature=0.0,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = "".join(b.text for b in msg.content if hasattr(b, "text"))
        tokens = (msg.usage.input_tokens if msg.usage else 0) + \
                 (msg.usage.output_tokens if msg.usage else 0)
    except Exception as e:
        return {"grounded": True, "reason": f"verify_error:{e}", "tokens": 0}

    start = raw.find("{"); end = raw.rfind("}") + 1
    if start >= 0 and end > start:
        try:
            obj = json.loads(raw[start:end])
            return {"grounded": bool(obj.get("grounded", False)),
                    "reason": str(obj.get("reason", ""))[:200],
                    "tokens": tokens}
        except json.JSONDecodeError:
            pass
    return {"grounded": True, "reason": "parse_fail", "tokens": tokens}


def escalate_gen_anthropic(question: str, context: str,
                            gen_fn,
                            rates=(0.5, 0.7, None),
                            verify_model: str = "claude-haiku-4-6",
                            api_key: str | None = None) -> tuple[str, dict]:
    """Compress → gen → verify → escalate. Anthropic-backed verify."""
    from pipeline_v2 import compress
    attempts = []
    total_verify_tok = 0
    ans = ""

    for rate in rates:
        if rate is None:
            ctx = context
            stats = {"savings": 0.0, "final": None}
        else:
            ctx, stats = compress(context, question=question, rate=rate)
        ans = gen_fn(ctx)
        v = verify(question, ans, context, model=verify_model, api_key=api_key)
        total_verify_tok += v.get("tokens", 0)
        attempts.append({
            "rate": rate, "stats": stats,
            "grounded": v["grounded"], "reason": v["reason"],
            "answer": ans[:200],
        })
        if v["grounded"]:
            return ans, {
                "rate_used": rate, "attempts": attempts,
                "total_verify_tokens": total_verify_tok,
                "grounded": True,
            }

    return ans, {
        "rate_used": None, "attempts": attempts,
        "total_verify_tokens": total_verify_tok,
        "grounded": False,
    }
