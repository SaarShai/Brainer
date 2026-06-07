#!/usr/bin/env python3
"""exp8_trigger — does a description trim still trigger the right skill?

The always-on tax is all description text. Trimming it is the real lever — but
descriptions are what makes the model pick the right skill, so over-trimming breaks
triggering. This measures top-1 trigger accuracy: given the live catalog of
(name: description) read from disk + a should-fire prompt, does the model select the
intended skill? Run it BEFORE trimming (baseline) and AFTER (compare) — keep a trim
only if accuracy holds.

Usage:
  python3 run_trigger.py --model qwen2.5:7b-instruct          # live descriptions from disk
  python3 run_trigger.py --stub
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[1]
SKILLS_DIR = REPO_ROOT / "skills"
sys.path.insert(0, str(REPO_ROOT / "eval" / "exp1_compounding"))
from run_compounding import call_ollama  # noqa: E402

RESULTS_DIR = HERE / "results"

# should-fire prompts: each must select its intended skill over the rest of the catalog.
SHOULD_FIRE = [
    ("make your answers really terse and compact, drop the fluff", "caveman-ultra"),
    ("this plan has way too many steps — simplify it, cut the process", "lean-execution"),
    ("before we start this 6-file refactor, draft a phased plan first", "plan-first-execute"),
    ("I think the tests pass now — confirm the work is actually done", "verify-before-completion"),
    ("where is the function parse_config used across the whole codebase?", "index-first"),
    ("have we tried to fix this caching bug in some earlier session?", "session-recall"),
    ("the wiki facts are stale after the big rename — reconcile them against the code", "wiki-refresh"),
    ("these wiki pages are old; apply time-based confidence decay to them", "memory-decay"),
    ("should this note be persisted to memory or is it too low-signal?", "write-gate"),
    ("record this architecture decision in our project memory for next time", "wiki-memory"),
    ("the terminal output is full of ANSI codes and progress bars — clean it up", "output-filter"),
    ("I'm re-reading a file I already opened; just show me what changed", "semantic-diff"),
    ("audit this project's prompt-cache hygiene before we ship the new hooks", "cache-lint"),
    ("write a handoff doc so a fresh session can pick up where I left off", "handoff"),
    ("this prompt is over 2K tokens — compress it before sending", "compress-context"),
    ("classify this incoming prompt and route it to the cheapest capable model", "prompt-triage"),
    ("extract the key state from this transcript before it gets compacted", "context-keeper"),
    ("the agent keeps making the same failing tool call over and over", "loop-breaker"),
    ("pull the transcript from my other stuck session and write a doc here", "handoff-from"),
]


def load_catalog() -> list[tuple[str, str]]:
    cat = []
    for d in sorted(SKILLS_DIR.iterdir()):
        sk = d / "SKILL.md"
        if not sk.is_file():
            continue
        txt = sk.read_text(encoding="utf-8")
        m = re.search(r"^description:\s*(.+)$", txt, re.M)
        if m:
            cat.append((d.name, m.group(1).strip()))
    return cat


def pick(backend: str, model: str, catalog: list[tuple[str, str]], prompt: str) -> str:
    listing = "\n".join(f"- {n}: {desc}" for n, desc in catalog)
    sys_p = ("You are a skill router. Given the catalog and a user message, name the ONE "
             "skill whose description best matches. Reply with ONLY the skill name, nothing else.")
    body = f"CATALOG:\n{listing}\n\nUSER MESSAGE: {prompt}\n\nBest-fit skill name:"
    if backend == "stub":
        # stub: pick the skill whose name-stem appears most in the prompt (plumbing only)
        toks = set(re.findall(r"[a-z]+", prompt.lower()))
        best, score = catalog[0][0], -1
        for n, _ in catalog:
            s = sum(1 for t in n.split("-") if t in toks)
            if s > score:
                best, score = n, s
        return best
    out = call_ollama(model, sys_p, body)["output"].strip().lower()
    # match the returned text against known skill names (longest match wins)
    names = [n for n, _ in catalog]
    hits = sorted([n for n in names if n in out], key=len, reverse=True)
    return hits[0] if hits else out[:40]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="qwen2.5:7b-instruct")
    ap.add_argument("--stub", action="store_true")
    ap.add_argument("--out", default=str(RESULTS_DIR / "summary.json"))
    ap.add_argument("--label", default="live", help="tag for this run (e.g. baseline / trimmed)")
    args = ap.parse_args()
    backend = "stub" if args.stub else "ollama"
    catalog = load_catalog()
    desc_tokens = sum(max(1, len(d) // 4) for _, d in catalog)  # rough
    print(f"exp8_trigger: backend={backend} model={args.model} catalog={len(catalog)} "
          f"~{desc_tokens} desc-tokens label={args.label}", flush=True)

    records, correct = [], 0
    for prompt, expected in SHOULD_FIRE:
        got = pick(backend, args.model, catalog, prompt)
        ok = (got == expected)
        correct += ok
        records.append({"prompt": prompt, "expected": expected, "got": got, "correct": ok})
        print(f"  {'OK ' if ok else 'XX '} expected={expected:<24} got={got}", flush=True)

    acc = round(correct / len(SHOULD_FIRE), 3)
    summary = {
        "experiment": "exp8_trigger", "backend": backend, "model": args.model,
        "label": args.label, "n_prompts": len(SHOULD_FIRE),
        "catalog_size": len(catalog), "approx_desc_tokens": desc_tokens,
        "top1_accuracy": acc, "correct": correct, "records": records,
    }
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(summary, indent=2))
    print(f"\n=== top-1 trigger accuracy ({args.label}): {acc} ({correct}/{len(SHOULD_FIRE)}) "
          f"| ~{desc_tokens} desc-tokens ===", flush=True)
    print(f"results: {out_path}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
