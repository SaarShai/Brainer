"""ComCom MCP server.

Run: python -m comcom_mcp.server
Or:  python path/to/server.py

Tools exposed:
  - comcom_compress(context, question=None, rate=0.5) → compressed text + stats
  - comcom_verify(question, answer, context, model='auto') → {grounded, reason}
  - comcom_skip_check(context) → should_compress? + why
  - comcom_estimate_cost(...) → $ projection

Agent orchestration pattern:
  1. comcom_skip_check(context) — if skip, use full.
  2. comcom_compress(context, question, rate=0.5) → compressed
  3. call target model with compressed context
  4. comcom_verify(question, answer, context) → if not grounded, retry
  5. retry with comcom_compress(rate=0.7) or fall back to full
"""
from __future__ import annotations
import json, os, sys, urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from mcp.server.fastmcp import FastMCP
from pipeline_v2 import compress as _compress
from skip_detector import should_compress as _should_compress

mcp = FastMCP("comcom")


@mcp.tool()
def comcom_compress(context: str, question: str | None = None, rate: float = 0.5) -> str:
    """Compress a context while preserving code/URLs/paths and question-relevant sentences when provided.

    Use before sending long context to an expensive LLM. Expected savings: 40-55%
    at rate=0.5 with question-aware protection. Quality hit is small when paired
    with comcom_verify for escalation.

    Args:
      context: the long text to compress.
      question: if provided, sentences containing question keywords plus
        factual-pattern sentences (numbers/dates/versions/paths) are preserved
        verbatim. Strongly recommended for QA tasks.
      rate: LLMLingua-2 keep rate in (0, 1]. 0.5 = aggressive, 0.7 = gentle,
        1.0 = skip LLMLingua (caveman regex only).

    Returns:
      JSON string with fields: compressed (str), stats (dict with orig_tok,
      final, savings, critical_sentences, rate).
    """
    compressed, stats = _compress(context, question=question, rate=rate)
    return json.dumps({"compressed": compressed, "stats": stats})


@mcp.tool()
def comcom_skip_check(context: str) -> str:
    """Decide whether compression is worth attempting on this context.

    Heuristic pre-filter. Returns skip=True for content where compression is
    likely net-negative: dense numeric tables, short text, highly structured data.

    Args:
      context: the text to evaluate.

    Returns:
      JSON string {"skip": bool, "reason": str}.
    """
    out = _should_compress(context)
    return json.dumps(out)


@mcp.tool()
def comcom_verify(question: str, answer: str, context: str,
                  model: str = "auto") -> str:
    """Check if an answer is grounded in the context and addresses the question.

    Used after generating with compressed context: if not grounded, caller should
    escalate (higher rate or full context).

    Args:
      question: the original question posed to the model.
      answer: the model's answer using compressed context.
      context: the ORIGINAL (full) context for ground-truth check.
      model: "auto" = try Ollama qwen3:8b then Anthropic Haiku if ANTHROPIC_API_KEY set.
             "ollama:<name>" = specific Ollama model.
             "anthropic:<model>" = specific Claude model.

    Returns:
      JSON string {"grounded": bool, "reason": str, "tokens": int, "backend": str}.
    """
    # Prefer Ollama if available
    if model == "auto":
        try:
            urllib.request.urlopen("http://127.0.0.1:11434/api/tags", timeout=2)
            backend = "ollama"
            from verify import verify as _v
            out = _v(question, answer, context, model="qwen3:8b")
            out["backend"] = backend
            return json.dumps(out)
        except Exception:
            if os.environ.get("ANTHROPIC_API_KEY"):
                from verify_anthropic import verify as _va
                out = _va(question, answer, context, model="claude-haiku-4-6")
                out["backend"] = "anthropic"
                return json.dumps(out)
            return json.dumps({"grounded": True, "reason": "no_verify_backend",
                               "tokens": 0, "backend": "none"})
    elif model.startswith("ollama:"):
        from verify import verify as _v
        out = _v(question, answer, context, model=model.split(":", 1)[1])
        out["backend"] = "ollama"
        return json.dumps(out)
    elif model.startswith("anthropic:"):
        from verify_anthropic import verify as _va
        out = _va(question, answer, context, model=model.split(":", 1)[1])
        out["backend"] = "anthropic"
        return json.dumps(out)
    return json.dumps({"grounded": True, "reason": f"unknown_model:{model}",
                       "tokens": 0, "backend": "none"})


@mcp.tool()
def comcom_estimate_cost(n_calls: int, avg_input_tokens: int,
                         avg_output_tokens: int = 200,
                         model: str = "claude-sonnet-4",
                         savings_rate: float = 0.45,
                         verify_overhead_tokens: int = 50) -> str:
    """Estimate $ savings from using ComCom over N API calls.

    Args:
      n_calls: expected number of calls.
      avg_input_tokens: typical context size.
      avg_output_tokens: typical response size.
      model: target model name (claude-haiku-4, claude-sonnet-4, claude-opus-4, gpt-4.1).
      savings_rate: measured compression savings (default 0.45 from our eval).
      verify_overhead_tokens: per-call verify overhead (default 50).

    Returns:
      JSON string with baseline_cost, comcom_cost, saved_usd, percent_saved.
    """
    from scripts.cost_estimator import estimate
    out = estimate(n_calls, avg_input_tokens, avg_output_tokens, model,
                    savings_rate, verify_overhead_tokens)
    return json.dumps(out)


if __name__ == "__main__":
    mcp.run()
