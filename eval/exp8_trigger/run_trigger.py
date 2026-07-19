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
  python3 run_trigger.py --validate-only                      # deterministic, no model
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

# Target prompts are exact-match cases: a companion cannot pass for the target.
TARGET_CASES = [
    ("/brainer use whichever optional Brainer skills or individual methods are relevant to this task", "brainer"),
    ("make your answers really terse and compact, drop the fluff", "caveman-ultra"),
    ("this plan has way too many steps — simplify it, cut the process", "lean-execution"),
    ("before we start this 6-file refactor, draft a phased plan first", "plan-first-execute"),
    ("/wayfinder map this multi-session effort whose destination is known but whose decision route is still foggy", "wayfinder"),
    ("I think the tests pass now — confirm the work is actually done", "verify-before-completion"),
    ("where is the function parse_config used across the whole codebase?", "index-first"),
    ("the wiki facts are stale after the big rename — reconcile them against the code", "wiki-refresh"),
    ("should this note be persisted to memory or is it too low-signal?", "write-gate"),
    ("record this architecture decision in our project memory for next time", "wiki-memory"),
    ("the terminal output is full of ANSI codes and progress bars — clean it up", "output-filter"),
    ("I'm re-reading a file I already opened; just show me what changed", "semantic-diff"),
    ("audit this project's prompt-cache hygiene before we ship the new hooks", "cache-lint"),
    ("classify this incoming prompt and route it to the cheapest capable model", "prompt-triage"),
    ("extract the key state from this transcript before it gets compacted", "context-keeper"),
    ("/think reason through this open-ended problem from first principles and challenge the assumptions before proposing any solution", "think"),
    ("/baton drop a verified handoff of this in-progress session so another agent can continue it", "baton"),
    ("audit this session for missed Brainer skill triggers and unverified completion claims", "brainer-audit"),
    ("watch this long session for filler creep, looping tool errors, and unverified done claims", "compliance-canary"),
    ("score this draft from zero to five against the written rubric and gate whether it ships", "eval-gate"),
    ("use the Fable method on this layered task because the first debugging theory may be wrong", "fable-mode"),
    ("map this code change to its callers and blast radius before I decide whether it is safe to ship", "impact-of-change"),
    ("turn this repeated local workflow into a reusable Brainer skill", "learn-skill"),
    ("design this generator-verifier retry loop with a concrete gate, stop condition, and budget cap", "loop-engineering"),
    ("/self-improvement-loops govern this loop that may rewrite its own prompt, evaluator harness, and optimizer", "self-improvement-loops"),
    ("sync these canonical Brainer skill changes to sibling repos without overwriting customizations", "propagate"),
    ("track every ask and conjunct in a visible ledger until the user explicitly closes each one", "requirements-ledger"),
    ("scan this patch for introduced secrets, dangerous sinks, risky auth logic, and untrusted dependencies", "security-oversight"),
    ("this task will repeat; run an after-the-fact retrospective and capture reusable project lessons", "task-retrospective"),
    ("lead this challenging task by delegating bounded builder lanes and reviewing their work", "team-lead"),
    ("break this migration into independent parallel lanes across every affected file and drive it end-to-end to done", "standing-orders"),
]

# Composition prompts accept any listed companion as an honest top-1 answer.
COMPOSITION_CASES = [
    ("Record this durable architecture decision in project memory, but first decide whether it is high-signal enough to persist.",
     ("write-gate", "wiki-memory")),
    ("Keep every request open during this drifting long session and watch for unverified completion claims.",
     ("requirements-ledger", "compliance-canary")),
    ("Plan this layered multi-file task and apply the Fable evidence-and-verification discipline while executing it.",
     ("plan-first-execute", "fable-mode")),
]

# Backward-compatible import for existing ad-hoc consumers.
SHOULD_FIRE = TARGET_CASES


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


def live_skill_names() -> set[str]:
    return {d.name for d in SKILLS_DIR.iterdir() if (d / "SKILL.md").is_file()}


def validate_cases(
    target_cases: list[tuple[str, str]] | None = None,
    composition_cases: list[tuple[str, tuple[str, ...]]] | None = None,
) -> list[str]:
    targets = TARGET_CASES if target_cases is None else target_cases
    compositions = COMPOSITION_CASES if composition_cases is None else composition_cases
    live = live_skill_names()
    errors: list[str] = []
    names = []
    for index, case in enumerate(targets):
        if not isinstance(case, tuple) or len(case) != 2:
            errors.append(f"target {index} must be a (prompt, skill) pair")
            continue
        prompt, target = case
        if not isinstance(prompt, str) or not prompt.strip() or not isinstance(target, str) or not target:
            errors.append(f"target {index} must have a non-empty prompt and skill")
            continue
        names.append(target)
    duplicates = sorted({name for name in names if names.count(name) > 1})
    if duplicates:
        errors.append(f"duplicate target cases: {duplicates}")
    if set(names) != live or len(names) != len(live):
        errors.append(f"target coverage mismatch: targets={len(names)} live={len(live)} "
                      f"missing={sorted(live - set(names))} extra={sorted(set(names) - live)}")
    for index, case in enumerate(compositions):
        if not isinstance(case, tuple) or len(case) != 2:
            errors.append(f"composition {index} must be a (prompt, accepted-skills) pair")
            continue
        prompt, accepted = case
        if not isinstance(prompt, str) or not prompt.strip() or not isinstance(accepted, tuple) or len(accepted) < 2:
            errors.append(f"composition {index} must have a prompt and at least two accepted skills")
            continue
        if any(not isinstance(name, str) or not name.strip() for name in accepted):
            errors.append(f"composition {index} accepted skills must be non-empty strings")
            continue
        accepted_set = set(accepted)
        if len(accepted_set) != len(accepted):
            errors.append(f"composition {index} has duplicate accepted skills")
        unknown = sorted(accepted_set - live)
        if unknown:
            errors.append(f"composition {index} has unknown accepted skills: {unknown}")
    return errors


def case_matches(got: str, accepted: tuple[str, ...]) -> bool:
    return got in accepted


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
    ap.add_argument("--validate-only", action="store_true")
    ap.add_argument("--out", default=str(RESULTS_DIR / "summary.json"))
    ap.add_argument("--label", default="live", help="tag for this run (e.g. baseline / trimmed)")
    args = ap.parse_args()
    backend = "stub" if args.stub else "ollama"
    catalog = load_catalog()
    errors = validate_cases()
    if errors:
        print("case validation: FAIL\n  " + "\n  ".join(errors), file=sys.stderr)
        return 2
    if args.validate_only:
        print(f"case validation: PASS targets={len(TARGET_CASES)} "
              f"compositions={len(COMPOSITION_CASES)} live={len(live_skill_names())}")
        return 0
    desc_tokens = sum(max(1, len(d) // 4) for _, d in catalog)  # rough
    print(f"exp8_trigger: backend={backend} model={args.model} catalog={len(catalog)} "
          f"~{desc_tokens} desc-tokens label={args.label}", flush=True)

    cases = ([('target', prompt, (expected,)) for prompt, expected in TARGET_CASES] +
             [('composition', prompt, accepted) for prompt, accepted in COMPOSITION_CASES])
    records, correct = [], 0
    for case_type, prompt, accepted in cases:
        got = pick(backend, args.model, catalog, prompt)
        ok = case_matches(got, accepted)
        correct += ok
        records.append({"prompt": prompt, "expected": accepted[0], "accepted": list(accepted),
                        "case_type": case_type, "got": got, "correct": ok})
        expected_label = "|".join(accepted)
        print(f"  {'OK ' if ok else 'XX '} expected={expected_label:<39} got={got}", flush=True)

    acc = round(correct / len(cases), 3)
    summary = {
        "experiment": "exp8_trigger", "backend": backend, "model": args.model,
        "label": args.label, "n_prompts": len(cases),
        "n_target_prompts": len(TARGET_CASES),
        "n_composition_prompts": len(COMPOSITION_CASES),
        "catalog_size": len(catalog), "approx_desc_tokens": desc_tokens,
        "top1_accuracy": acc, "correct": correct, "records": records,
    }
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(summary, indent=2))
    print(f"\n=== top-1 trigger accuracy ({args.label}): {acc} ({correct}/{len(cases)}) "
          f"| ~{desc_tokens} desc-tokens ===", flush=True)
    print(f"results: {out_path}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
