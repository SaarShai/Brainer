---
name: compress-context
description: Compound prompt compression with self-verify escalation. Use opt-in for long-context tasks where the prompt is ≥2K tokens. Compresses input via LLMLingua-2 + structural protection of code/paths/numbers, then runs a quick judge to verify the answer is still grounded; on low confidence, re-runs at a higher rate or falls back to original. Measured 44.9% token savings, Δscore −0.12 (95% CI touches 0) on SQuAD v2 (n=8). Opt-in until N≥50 verified.
effort: medium
tools: [Bash, Read]
auto-install: false
---

# compress-context (ComCom)

## What it does

Three-stage pipeline that compresses long prompts while preserving answer quality:

1. **Caveman pass** — drop filler words, normalize whitespace.
2. **LLMLingua-2 pass** — neural token-level compression at a target rate (default 0.5 = keep 50% tokens). Code, paths, numbers, math placeholders protected.
3. **Self-verify** — quick judge call (cheap model) asks "is the answer grounded in the compressed context?". On low confidence, escalates: re-compress at higher rate (0.7) → fall back to original.

## Measured

Eval-v3 on SQuAD v2, n=8, judge=qwen3:8b, model under test=phi4:14b:
- Adaptive escalation (`rates=(0.5, 0.7, None)`): **44.9% input-token savings, Δscore −0.12 [−0.38, 0.00]**. Quality effectively preserved (CI touches 0). Zero REFUSE failures.

Sample size is small. Promote to default after N≥50 on Kaggle T4.

## Usage (Python)

The skill directory name has a hyphen, so it isn't importable as a Python
package. Add `tools/` to `sys.path` and import the modules directly:

```python
import sys
sys.path.insert(0, "skills/compress-context/tools")
from pipeline_v2 import compress
from verify import escalate_gen

def my_gen(ctx):
    return call_model(prompt=build_prompt(ctx, question))

answer, meta = escalate_gen(question, context, my_gen, rates=(0.5, 0.7, None))
# meta: {rate_used, attempts, total_verify_tokens, grounded}
```

## MCP

`tools/comcom_mcp/` exposes four MCP tools — `comcom_compress`, `comcom_verify`,
`comcom_skip_check`, `comcom_estimate_cost` — for use from any MCP-aware host.

## Install

```bash
bash skills/compress-context/tools/install.sh
```

Adds the MCP server to your host config. Optional.

## Files

```
tools/
├── pipeline_v2.py     # 3-stage compression
├── verify.py          # judge + escalation
├── eval_v3.py         # eval harness used to measure
├── comcom_mcp/        # MCP server
├── samples/
└── INSTALL.md
```

## Lineage

LLMLingua-2 (microsoft/LLMLingua, MIT) for neural compression. Self-verify escalation pattern is original to this project. RESULTS.md carries the eval methodology + raw numbers.
