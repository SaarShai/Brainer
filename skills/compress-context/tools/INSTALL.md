# ComCom — Install

## MCP server (universal — Claude Code, Cursor, Cline, Zed, Windsurf)

Requires Python ≥ 3.10.

```bash
pip install mcp tiktoken llmlingua
# Additional verify backend: pip install anthropic  (for Anthropic verify backend)
git clone https://github.com/SaarShai/token-economy
```

### Claude Code
```bash
claude mcp add comcom --scope project \
  -- python /path/to/token-economy/projects/compound-compression-pipeline/comcom_mcp/server.py
```

### Cursor / Cline / Zed / Windsurf / Continue
Add to your client's MCP config:
```json
{
  "comcom": {
    "command": "python",
    "args": ["/path/to/comcom_mcp/server.py"]
  }
}
```

## Tools exposed

- `comcom_compress(context, question?, rate=0.5)` → compressed text + stats JSON
- `comcom_skip_check(context)` → should compress? + reason
- `comcom_verify(question, answer, context, model=auto)` → grounded check
- `comcom_estimate_cost(n_calls, avg_input_tokens, ...)` → $ projection

## Agent orchestration pattern

```
1. comcom_skip_check(ctx) → if skip, use full ctx
2. comcom_compress(ctx, question, rate=0.5) → compressed
3. [your model call with compressed ctx]
4. comcom_verify(q, answer, ctx) → if not grounded:
   5a. retry comcom_compress at rate=0.7 → gen → verify
   5b. if still not grounded, fall back to full ctx
```

## Verify backends

- **Ollama** (local, default): needs qwen3:8b pulled. Cheapest.
- **Anthropic**: set `ANTHROPIC_API_KEY` env var. Uses claude-haiku-4-6 (~$0.0002/verify).
- Auto: tries Ollama first, Anthropic fallback.

## Measured

SQuAD v2 n=8, 2 runs, bootstrap 95% CI:
- 44.9% token savings
- Δquality −0.12 [−0.38, 0.00] (CI touches 0 → quality effectively preserved)
- Zero REFUSE failures at rate=0.5 with adaptive escalation
