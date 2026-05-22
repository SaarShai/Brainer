"""Logprob-based confidence escalation.

Cheap quality signal: if target model is unconfident on a compressed-context answer,
escalate before doing an LLM-based verify call. Works with Anthropic API
(supports `top_logprobs` on some models) and OpenAI (supports logprobs).

Usage:
    from verify_logprob import escalate_with_logprobs

    ans, meta = escalate_with_logprobs(question, context, gen_fn_with_logprobs,
                                         rates=(0.5, 0.7, None),
                                         min_avg_logprob=-1.5)

gen_fn_with_logprobs(ctx, q) must return dict:
    {"text": str, "avg_logprob": float | None}
"""
from __future__ import annotations


def escalate_with_logprobs(question: str, context: str, gen_fn,
                            rates=(0.5, 0.7, None),
                            min_avg_logprob: float = -1.5,
                            fallback_verify_fn=None) -> tuple[str, dict]:
    """Escalate compression on low confidence.

    Decision rule per attempt:
      - if avg_logprob >= threshold → accept.
      - if avg_logprob < threshold → escalate.
      - if avg_logprob is None (provider doesn't expose) → fall back to fallback_verify_fn
        if given, else accept.
    """
    from pipeline_v2 import compress
    attempts = []
    ans = ""

    for rate in rates:
        if rate is None:
            ctx = context
            stats = {"savings": 0.0, "final": None}
        else:
            ctx, stats = compress(context, question=question, rate=rate)

        out = gen_fn(ctx, question)
        ans = out["text"]
        lp = out.get("avg_logprob")

        if lp is None and fallback_verify_fn is not None:
            v = fallback_verify_fn(question, ans, context)
            confident = v.get("grounded", False)
            reason = f"fallback_verify: {v.get('reason','')}"
        elif lp is None:
            confident = True  # can't tell → accept
            reason = "logprob_unavailable"
        else:
            confident = lp >= min_avg_logprob
            reason = f"avg_logprob={lp:.2f} threshold={min_avg_logprob}"

        attempts.append({"rate": rate, "stats": stats,
                          "avg_logprob": lp, "confident": confident,
                          "reason": reason, "answer": ans[:200]})

        if confident:
            return ans, {"rate_used": rate, "attempts": attempts,
                         "escalated": len(attempts) > 1}

    return ans, {"rate_used": None, "attempts": attempts,
                 "escalated": True, "exhausted": True}


def make_anthropic_gen(model: str = "claude-haiku-4-6", api_key: str | None = None):
    """Build gen_fn for Anthropic. Returns logprobs when available (Haiku supports top_logprobs).

    Note: Anthropic's `top_logprobs` param returns top-K token logprobs per position;
    we average the top-1 (chosen token) logprob across positions.
    """
    import os
    try:
        import anthropic
    except ImportError:
        raise RuntimeError("pip install anthropic")

    client = anthropic.Anthropic(api_key=api_key or os.environ.get("ANTHROPIC_API_KEY"))

    def gen(ctx: str, question: str) -> dict:
        prompt = f"CONTEXT:\n{ctx}\n\nQUESTION: {question}\nANSWER (terse, factual):"
        try:
            msg = client.messages.create(
                model=model, max_tokens=200, temperature=0.0,
                messages=[{"role": "user", "content": prompt}],
                extra_body={"top_logprobs": 1},  # best-effort; may be ignored
            )
            text = "".join(b.text for b in msg.content if hasattr(b, "text"))
            # Extract avg logprob if provider returned it
            lp = None
            if hasattr(msg, "usage") and hasattr(msg.usage, "output_logprobs"):
                lps = msg.usage.output_logprobs
                if lps:
                    lp = sum(lps) / len(lps)
            return {"text": text.strip(), "avg_logprob": lp}
        except Exception as e:
            return {"text": f"[gen_error: {e}]", "avg_logprob": None}

    return gen


def make_openai_gen(model: str = "gpt-4o-mini", api_key: str | None = None):
    """Build gen_fn for OpenAI. Returns avg logprob (OpenAI reliably exposes logprobs)."""
    import os
    try:
        from openai import OpenAI
    except ImportError:
        raise RuntimeError("pip install openai")

    client = OpenAI(api_key=api_key or os.environ.get("OPENAI_API_KEY"))

    def gen(ctx: str, question: str) -> dict:
        prompt = f"CONTEXT:\n{ctx}\n\nQUESTION: {question}\nANSWER (terse, factual):"
        try:
            r = client.chat.completions.create(
                model=model, temperature=0.0, max_tokens=200,
                logprobs=True, top_logprobs=1,
                messages=[{"role": "user", "content": prompt}],
            )
            ch = r.choices[0]
            text = ch.message.content or ""
            lp = None
            if ch.logprobs and ch.logprobs.content:
                lps = [t.logprob for t in ch.logprobs.content if t.logprob is not None]
                if lps: lp = sum(lps) / len(lps)
            return {"text": text.strip(), "avg_logprob": lp}
        except Exception as e:
            return {"text": f"[gen_error: {e}]", "avg_logprob": None}

    return gen
