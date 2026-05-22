#!/usr/bin/env python3
"""Populate each skill's EVAL.md with static-cost numbers."""
from __future__ import annotations

import json
import sys
from pathlib import Path


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    static_json = root / "eval" / "results" / "static_cost.json"
    if not static_json.exists():
        print("run static_cost.py first", file=sys.stderr)
        return 2
    data = {r["name"]: r for r in json.loads(static_json.read_text())}
    skills_dir = root / "skills"
    updated = 0
    for skill in sorted(skills_dir.iterdir()):
        if not skill.is_dir() or skill.name.startswith("_"):
            continue
        m = data.get(skill.name)
        if not m:
            continue
        eval_md = skill / "EVAL.md"
        body = f"""# EVAL — `{m['name']}`

## Static cost (measured)

| field | tokens / size |
|---|---|
| description (always resident) | **{m['description_tokens']} tokens** ({m['description_chars']} chars) |
| body (loaded on trigger)      | **{m['body_tokens']} tokens** ({m['body_chars']} chars) |
| tools/ payload                 | {m['tools_kb']} KB |
| model pin                      | `{m['model_pin'] or 'any'}` |
| effort pin                     | `{m['effort_pin'] or 'unset'}` |

agentskills.io budget reference: description ≤ 1,536 chars (1% of a 200K context window).

## A/B savings (pending live run)

Run:

```bash
python3 eval/runner.py --task eval/tasks/{m['name']}.yaml --n 10 --backend ollama
python3 eval/judge.py eval/results/{m['name']}.json
```

Once Ollama (or Anthropic API) is wired, fill this table:

| metric | without skill | with skill | Δ | 95% CI |
|---|---|---|---|---|
| input tokens (mean)  |   |   |   |   |
| output tokens (mean) |   |   |   |   |
| latency (ms)         |   |   |   |   |
| judge score (0–5)    |   |   |   |   |

## Methodology

- Sample size: N=10 local smoke; N≥50 on Kaggle T4 for any >20% savings claim.
- Tasks: 3–5 representative prompts in `eval/tasks/{m['name']}.yaml`.
- Judge: Xiaomi MiMo-7B via HF inference (or local Gemma fallback).
- Rubric: per-task rubric embedded in the YAML.

## Failure modes

To be filled in after live runs.
"""
        eval_md.write_text(body)
        updated += 1
    print(f"updated {updated} EVAL.md files")
    return 0


if __name__ == "__main__":
    sys.exit(main())
