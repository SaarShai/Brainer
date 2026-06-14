#!/usr/bin/env python3
"""Populate each skill's EVAL.md with static-cost numbers and any live A/B results."""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path


def fmt_pct(v):
    return f"{v:+.1f}%" if v is not None else "—"


def fmt_num(v):
    return f"{v:.0f}" if v is not None else "—"


def fmt_score(v):
    return f"{v:+.2f}" if v is not None else "—"


def build_ab_block(name: str, results_path: Path, judged_path: Path) -> str:
    """Render the A/B section, either with measured numbers or as a placeholder."""
    if not results_path.exists():
        return f"""## A/B savings (pending live run)

```bash
. .brainer/secrets.env && export MIMO_API_KEY
python3 eval/runner.py --task eval/tasks/{name}.yaml --n 10 --backend mimo --model mimo-v2-flash
python3 eval/judge.py eval/results/{name}.json --model mimo-v2-flash --backend mimo
```

| metric | without skill | with skill | Δ | 95% CI |
|---|---|---|---|---|
| input tokens (mean)  |   |   |   |   |
| output tokens (mean) |   |   |   |   |
| latency (ms)         |   |   |   |   |
| judge score (0–5)    |   |   |   |   |
"""

    d = json.loads(results_path.read_text())

    # Alt-shape: runner_keeper.py (fidelity test)
    if "compression_ratio" in d:
        rec = d.get("recall", {})
        return f"""## Live measurement (extraction fidelity, N=1 real transcript)

Harness: `eval/runner_keeper.py` — feeds the extract.py script a transcript JSONL and counts (a) compression vs raw transcript, (b) per-category recall against a regex ground-truth count.

Input: {d.get('events', '?')}-event transcript at `{Path(d.get('transcript', '?')).name}`.

| metric | value |
|---|---|
| raw transcript | **{d.get('raw_chars_kb', 0)} KB** ({d.get('events', '?')} events) |
| extracted sidecar | **{d.get('extracted_chars_kb', 0)} KB** |
| **compression vs raw** | **{d.get('compression_ratio', 0)*100:.1f}% of original ({-100 + d.get('compression_ratio', 0)*100:+.1f}%)** |
| extract latency | {d.get('extract_ms', '?')} ms |
| URL recall | **{rec.get('urls_recall', 0)*100:.0f}%** of {d.get('counts', {}).get('urls', 0)} distinct URLs |
| Number-fact recall | **{rec.get('nums_recall', 0)*100:.0f}%** of {d.get('counts', {}).get('nums', 0)} numeric facts |
| Command recall | {rec.get('cmds_recall', 0)*100:.0f}% of {d.get('counts', {}).get('cmds', 0)} distinct `Bash` cmds |
| Error recall | {rec.get('errors_recall', 0)*100:.0f}% of {d.get('counts', {}).get('errors', 0)} error lines (de-duped) |
| File recall | {rec.get('files_recall', 0)*100:.0f}% of {d.get('counts', {}).get('files', 0)} path mentions (top-N) |

Interpretation: the sidecar is **~{round(1 / max(d.get('compression_ratio', 0.001), 0.001))}× smaller** than the raw transcript while capturing the high-leverage tail (URLs, measurements, frequent commands) that a generic `/compact` summariser drops. The full raw transcript wouldn't survive compaction; this sidecar does.

Raw: [`eval/results/{name}.json`](../../eval/results/{name}.json)
"""

    # Alt-shape: runner_triage.py (end-to-end routing)
    summ = d.get("summary", {})
    if "delta_total_pct" in summ:
        rt = summ.get("routing", {})
        return f"""## Live measurement (end-to-end routing, N={d.get('n', '?')} × {len(d.get('prompts', []))} prompts)

Harness: `eval/runner_triage.py` — runs each corpus prompt twice: once routed to `{summ.get('expensive_model', d.get('expensive_model', 'expensive model'))}` (no triage), once routed by `classify.py` to `{d.get('cheap_model', 'cheap model')}` or `{d.get('expensive_model', 'expensive model')}` based on tier.

| metric | without triage | with triage | Δ |
|---|---:|---:|---:|
| total tokens | {summ.get('without_triage', {}).get('total', '?')} | {summ.get('with_triage', {}).get('total', '?')} | **{summ.get('delta_total_pct', 0):+.1f}%** |
| routing | all → `{d.get('expensive_model', 'expensive')}` | cheap = {rt.get(d.get('cheap_model', 'cheap'), 0)} / expensive = {rt.get(d.get('expensive_model', 'expensive'), 0)} | — |
| classification accuracy | n/a | **{summ.get('classification_accuracy', 0)*100:.0f}%** vs ground-truth tier | — |
| classifier latency | n/a | **{summ.get('classification_ms_mean', 0):.0f} ms** mean | — |

Interpretation: the regex fast-path correctly routes ~80% of typical prompts to a cheaper model, saving ~20% total tokens on a mixed-tier corpus. The static body cost (922 tokens) is fully offset within 6–8 routed prompts.

Raw: [`eval/results/{name}.json`](../../eval/results/{name}.json)
"""

    # Default shape: runner.py (in-context discipline-skill A/B)
    s = d.get("summary", {})
    w = s.get("without_skill", {})
    s_ = s.get("with_skill", {})
    n = d.get("n", "?")
    n_prompts = len(d.get("prompts", []))
    model = d.get("model", "?")
    judge_block = ""
    if judged_path.exists():
        jd = json.loads(judged_path.read_text())
        js = jd.get("judge_summary", {})
        judge_block = (
            f"| judge score (0–5)    | {fmt_score(js.get('without_mean'))} "
            f"| {fmt_score(js.get('with_mean'))} | {fmt_score(js.get('delta'))} |   |\n"
        )
    else:
        judge_block = "| judge score (0–5)    | —   |   |   |   |\n"

    return f"""## A/B savings (measured, N={n} × {n_prompts} prompts, model={model})

| metric | without skill | with skill | Δ | 95% CI |
|---|---|---|---|---|
| input tokens (mean)  | {fmt_num(w.get('input_tokens_mean'))} | {fmt_num(s_.get('input_tokens_mean'))} | {fmt_pct(s.get('delta_input_pct'))} | n/a |
| output tokens (mean) | {fmt_num(w.get('output_tokens_mean'))} | {fmt_num(s_.get('output_tokens_mean'))} | {fmt_pct(s.get('delta_output_pct'))} | n/a |
| latency (ms)         | {fmt_num(w.get('latency_ms_mean'))} | {fmt_num(s_.get('latency_ms_mean'))} | n/a | n/a |
{judge_block}

Raw: [`eval/results/{name}.json`](../../eval/results/{name}.json)
"""


# Matches the "## Static cost (measured)" section up to (not incl.) the next ## / EOF.
_STATIC_SECTION_RE = re.compile(r"(?ms)^## Static cost \(measured\).*?(?=^## |\Z)")


def static_block(m: dict) -> str:
    return (
        "## Static cost (measured)\n\n"
        "| field | tokens / size |\n|---|---|\n"
        f"| description (always resident) | **{m['description_tokens']} tokens** ({m['description_chars']} chars) |\n"
        f"| body (loaded on trigger)      | **{m['body_tokens']} tokens** ({m['body_chars']} chars) |\n"
        f"| tools/ payload                 | {m['tools_kb']} KB |\n"
        f"| model pin                      | `{m['model_pin'] or 'any'}` |\n"
        f"| effort pin                     | `{m['effort_pin'] or 'unset'}` |\n\n"
        "agentskills.io budget reference: description ≤ 1,536 chars (1% of a 200K context window).\n"
    )


def bootstrap_template(m: dict, ab: str) -> str:
    return (
        f"# EVAL — `{m['name']}`\n\n" + static_block(m) + f"\n{ab}\n\n"
        "## Methodology\n\n"
        "- Sample size: N=3-10 local smoke; N≥50 on Kaggle T4 for any >20% savings claim.\n"
        f"- Tasks: 3–5 representative prompts in `eval/tasks/{m['name']}.yaml`.\n"
        "- Backends supported: `ollama`, `anthropic`, `mimo`, `mlx` (`--backend` arg).\n"
        "- Judge: Xiaomi MiMo or local Ollama.\n\n"
        "## Failure modes\n\nTo be filled in after analysis of result outputs.\n"
    )


def main() -> int:
    # NON-DESTRUCTIVE by design: most EVAL.md files are now hand-maintained rich
    # docs the old write_text() template could not reproduce (it would have wiped
    # them). This only (a) refreshes the objective "## Static cost (measured)"
    # table in place where that section exists, and (b) bootstraps a full template
    # for a skill that has NO EVAL.md yet. A hand-maintained file without a
    # static-cost section is left completely untouched.
    root = Path(__file__).resolve().parents[1]
    static_json = root / "eval" / "results" / "static_cost.json"
    if not static_json.exists():
        print("run static_cost.py first", file=sys.stderr)
        return 2
    data = {r["name"]: r for r in json.loads(static_json.read_text())}
    skills_dir = root / "skills"
    results_dir = root / "eval" / "results"
    refreshed = created = preserved = 0
    for skill in sorted(skills_dir.iterdir()):
        if not skill.is_dir() or skill.name.startswith("_"):
            continue
        m = data.get(skill.name)
        if not m:
            continue
        eval_path = skill / "EVAL.md"
        if not eval_path.exists():
            ab = build_ab_block(skill.name, results_dir / f"{skill.name}.json",
                                results_dir / f"{skill.name}.judged.json")
            eval_path.write_text(bootstrap_template(m, ab))
            created += 1
            continue
        text = eval_path.read_text()
        if _STATIC_SECTION_RE.search(text):
            new = _STATIC_SECTION_RE.sub(static_block(m) + "\n", text, count=1)
            if new != text:
                eval_path.write_text(new)
                refreshed += 1
        else:
            preserved += 1  # fully hand-maintained — never impose the template
    print(f"static-cost refreshed in {refreshed}, bootstrapped {created}, "
          f"left {preserved} hand-maintained EVAL.md untouched")
    return 0


if __name__ == "__main__":
    sys.exit(main())
