#!/usr/bin/env python3
"""exp4_contradiction — when a remembered fact CHANGES, does the memory system serve
the CURRENT fact or a STALE wrong one?

Exp1 only ever ADDS facts. The hardest form of "learn from feedback" is corrective
feedback that CONTRADICTS a prior lesson (a command renamed, a constant lowered after
an incident, a config key deprecated). This harness tests whether the wiki-refresh
"Replace" decision (implemented here via the `wiki overlap` dedup-at-write primitive)
actually fixes stale answers — and whether naive append-only memory is better or worse
than no update at all.

Sequence (fixed order): 3 introducers establish v1 facts, 3 change-events deliver the
contradicting v2 facts, then 3 post-change dependent questions ask for the CURRENT fact.

Arms (each from a fresh `wiki.py init`):
  cold       — no memory. Floor: model has no Helios facts, guesses.
  stale      — writes the v1 introducer lessons; IGNORES the change-events (an agent
               that never updates memory). At dep-time retrieves v1 -> serves OLD answer.
  append     — writes v1 AND v2 as SEPARATE pages (naive add). Dep-time retrieval may
               surface BOTH -> contradiction in context.
  reconcile  — writes v1; on each change-event runs `wiki overlap`, and if it points at
               an existing same-topic page, REPLACES that page's Lesson with v2 (the
               wiki-refresh Replace action). Dep-time retrieves only the CURRENT fact.

Metric: post-change dependent accuracy (gold = the NEW value) + stale-answer rate
(served the OLD value) per arm. Hypothesis: reconcile > append > stale; stale may be
WORSE than cold (confidently serves a wrong-but-remembered fact).

Usage:
  python3 run_contradiction.py --model qwen2.5:7b-instruct
  python3 run_contradiction.py --stub          # offline wiring smoke
"""
from __future__ import annotations

import argparse
import json
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[1]
sys.path.insert(0, str(REPO_ROOT / "eval" / "exp1_compounding"))
# Reuse the tested Exp1 primitives verbatim.
from run_compounding import (  # noqa: E402
    SYSTEM, call_ollama, gate_pass, persist_lesson, retrieve, score_output, wiki,
)

RESULTS_DIR = HERE / "results"
ARMS = ("cold", "stale", "append", "reconcile")

# Each topic: an introducer (v1 fact), a change-event (v2 fact that CONTRADICTS v1),
# and a post-change dependent question whose gold is the NEW value. `stale_marker` is
# the OLD value — if it shows up instead, the system served a stale answer.
# Lessons are written rich enough to clear the write-gate (decision: + because + ≥2
# inline `code` tokens => score ≥ 4.0), so the test isolates contradiction handling
# rather than gate scoring. `match` is a distinctive token in the dep_prompt used only
# by the offline stub to route topics.
TOPICS = [
    {
        "slug": "helios-deploy",
        "query": "helios deploy command wave ship launch",
        "match": "deploy wave 3",
        "v1_lesson": "DECISION: The Project Helios deploy command is `helios ship --wave N`, "
                     "chosen because `ship` reads as the release verb. Run `helios ship --wave 3` "
                     "to deploy wave 3 of Helios.",
        "v2_lesson": "DECISION: the Project Helios deploy command moved to `helios launch --wave N` "
                     "because `ship` collided with the package-publish tool. Run "
                     "`helios launch --wave 3` to deploy wave 3 of Helios.",
        "change_prompt": "Project Helios shipped v2. The `ship` subcommand is gone; deploys now "
                         "use `helios launch --wave N`. Acknowledge the new deploy command.",
        "dep_prompt": "On the CURRENT Project Helios (v2 or later), what is the EXACT command to "
                      "deploy wave 3? Answer with just the command.",
        "gold_new": "helios launch --wave 3",
        "gold_old": "helios ship --wave 3",
    },
    {
        "slug": "helios-config-prefix",
        "query": "helios config env var prefix database url HELIOS HLX",
        "match": "database url",
        "v1_lesson": "DECISION: Project Helios config env vars use the `HELIOS_` prefix because "
                     "UPPER_SNAKE keeps them greppable. The database URL var is `HELIOS_DB_URL` "
                     "in Helios.",
        "v2_lesson": "DECISION: Project Helios migrated to the `HLX_` config prefix because "
                     "`HELIOS_` was too long. The database URL var is now `HLX_DB_URL` in Helios; "
                     "the old prefix is deprecated.",
        "change_prompt": "Project Helios v3 renamed every config env var prefix from `HELIOS_` to "
                         "`HLX_`. The old prefix is deprecated. Acknowledge the new prefix.",
        "dep_prompt": "What is the CURRENT env var name for the Project Helios database URL? "
                      "Answer with just the variable name.",
        "gold_new": "HLX_DB_URL",
        "gold_old": "HELIOS_DB_URL",
    },
    {
        "slug": "helios-retry",
        "query": "helios max_retries retry value attempts constant",
        "match": "max_retries",
        "v1_lesson": "DECISION: Project Helios sets `max_retries=5` for outbound calls because "
                     "tuning `max_retries` to 5 balanced resilience and latency in Helios load tests.",
        "v2_lesson": "INCIDENT POSTMORTEM: DECISION: Helios lowered `max_retries` to 2 because a "
                     "retry storm took down the gateway. The fix moved Helios to `max_retries=2` "
                     "after the incident.",
        "change_prompt": "After an incident, Project Helios lowered `max_retries` from 5 to 2. "
                         "Acknowledge the new retry value.",
        "dep_prompt": "What is the CURRENT value of `max_retries` in Project Helios? "
                      "Answer with just `max_retries=<n>`.",
        "gold_new": "max_retries=2",
        "gold_old": "max_retries=5",
    },
]


def build_sequence() -> list[dict[str, Any]]:
    seq: list[dict[str, Any]] = []
    for t in TOPICS:
        seq.append({"role": "intro", "slug": t["slug"], "query": t["query"],
                    "prompt": f"Note this Project Helios convention: {t['v1_lesson']}",
                    "lesson_text": t["v1_lesson"]})
    for t in TOPICS:
        seq.append({"role": "change", "slug": t["slug"], "query": t["query"],
                    "prompt": t["change_prompt"], "lesson_text": t["v2_lesson"]})
    for t in TOPICS:
        seq.append({"role": "dep", "slug": t["slug"], "query": t["query"],
                    "prompt": t["dep_prompt"], "gold_new": t["gold_new"],
                    "gold_old": t["gold_old"]})
    return seq


def replace_lesson(root: Path, page_id: str, new_text: str) -> None:
    """Overwrite the `## Lesson` section of an existing page, then re-index.

    Implements the wiki-refresh "Replace" decision: the stale page is rewritten in place
    so retrieval can no longer surface the superseded fact.
    """
    rel = page_id if page_id.endswith(".md") else page_id + ".md"
    page_path = root / rel
    body = page_path.read_text(encoding="utf-8")
    marker = "\n## Lesson\n"
    head = body.split(marker, 1)[0].rstrip() if marker in body else body.rstrip()
    page_path.write_text(head + "\n\n## Lesson\n\n" + new_text.strip() + "\n", encoding="utf-8")
    wiki(root, "index")


def overlap_match(root: Path, title: str, body: str) -> str | None:
    """Return the id of the best same-topic existing page (the Replace target), or None."""
    res = wiki(root, "overlap", "--title", title, "--body", body)
    if not isinstance(res, dict):
        return None
    bm = res.get("best_match")
    if bm and bm.get("score", 0) >= 1:
        return bm.get("id")
    return None


def generate(backend: str, model: str, system: str, prompt: str) -> dict[str, Any]:
    if backend == "stub":
        # Deterministic: echo whatever CURRENT fact is in context; if both v1 and v2 are
        # present (append arm) the model is "confused" and emits the OLDER one (worst case
        # for naive append). If only v1 (stale) -> old. If only v2 (reconcile) -> new.
        ctx = (system + "\n" + prompt).lower()
        for t in TOPICS:
            if t["match"] in prompt.lower():
                has_new = t["gold_new"].lower() in ctx
                has_old = t["gold_old"].lower() in ctx
                if has_new and not has_old:
                    ans = t["gold_new"]
                elif has_old:
                    ans = t["gold_old"]  # append (both) or stale (old only) -> stale
                else:
                    ans = "UNKNOWN"
                return {"output": ans, "latency_ms": 1, "prompt_eval_count": len(ctx)//4, "eval_count": 4}
        return {"output": "UNKNOWN", "latency_ms": 1, "prompt_eval_count": len(ctx)//4, "eval_count": 2}
    return call_ollama(model, system, prompt)


def run_arm(arm: str, seq: list[dict[str, Any]], backend: str, model: str) -> list[dict[str, Any]]:
    tmp = Path(tempfile.mkdtemp(prefix=f"exp4-{arm}-"))
    root = tmp / "wiki"
    wiki(root, "init")
    # track the page id written per slug so reconcile knows what to replace
    page_for_slug: dict[str, str] = {}
    records: list[dict[str, Any]] = []

    for idx, task in enumerate(seq):
        role = task["role"]
        system = SYSTEM
        retrieved_ids: list[str] = []
        if arm != "cold":
            block, retrieved_ids = retrieve(root, task["query"], k=3)
            if block:
                system = SYSTEM + "\n\n" + block

        rec: dict[str, Any] = {"arm": arm, "task_index": idx, "role": role,
                               "slug": task["slug"], "retrieved_ids": retrieved_ids}

        if role == "dep":
            gen = generate(backend, model, system, task["prompt"])
            correct = score_output(gen["output"], task["gold_new"], "exact")
            stale = (not correct) and score_output(gen["output"], task["gold_old"], "exact")
            rec.update({
                "correct": bool(correct), "served_stale": bool(stale),
                "tokens": int(gen.get("prompt_eval_count", 0)) + int(gen.get("eval_count", 0)),
                "output_preview": gen["output"][:160],
                "gold_new": task["gold_new"], "gold_old": task["gold_old"],
            })
        else:
            # intro / change: write the lesson per the arm's policy
            wrote, action, gate_score = False, "skip", None
            if arm == "stale":
                if role == "intro":
                    pid = persist_lesson(root, task["slug"], task["lesson_text"])
                    page_for_slug[task["slug"]] = pid
                    wrote, action = True, "create"
                # stale arm: change-events are IGNORED (no write)
            elif arm == "append":
                passed, det = gate_pass(task["lesson_text"], kind="fact")
                gate_score = det.get("score")
                if passed:
                    title = task["slug"] if role == "intro" else f"{task['slug']}-v2"
                    persist_lesson(root, title, task["lesson_text"])
                    wrote, action = True, "create"
            elif arm == "reconcile":
                passed, det = gate_pass(task["lesson_text"], kind="fact")
                gate_score = det.get("score")
                if passed:
                    if role == "intro":
                        pid = persist_lesson(root, task["slug"], task["lesson_text"])
                        page_for_slug[task["slug"]] = pid
                        wrote, action = True, "create"
                    else:  # change: find same-topic page and REPLACE it
                        target = overlap_match(root, f"{task['slug']}-v2", task["lesson_text"]) \
                                 or page_for_slug.get(task["slug"])
                        if target:
                            replace_lesson(root, target, task["lesson_text"])
                            wrote, action = True, "replace"
                        else:
                            persist_lesson(root, f"{task['slug']}-v2", task["lesson_text"])
                            wrote, action = True, "create"
            rec.update({"correct": None, "served_stale": None, "wrote": wrote,
                        "action": action, "gate_score": gate_score})
        records.append(rec)
    return records


def build_summary(all_recs: dict[str, list[dict]], backend: str, model: str, wall_s: float) -> dict:
    per_arm: dict[str, Any] = {}
    for arm, recs in all_recs.items():
        deps = [r for r in recs if r["role"] == "dep"]
        n = len(deps)
        per_arm[arm] = {
            "n_dependent": n,
            "accuracy_current": round(sum(bool(r["correct"]) for r in deps) / max(n, 1), 3),
            "stale_answer_rate": round(sum(bool(r["served_stale"]) for r in deps) / max(n, 1), 3),
            "records": recs,
        }
    verdict: dict[str, Any] = {
        "accuracy_current": {a: per_arm[a]["accuracy_current"] for a in per_arm},
        "stale_answer_rate": {a: per_arm[a]["stale_answer_rate"] for a in per_arm},
    }
    if "reconcile" in per_arm and "stale" in per_arm:
        verdict["reconcile_minus_stale"] = round(
            per_arm["reconcile"]["accuracy_current"] - per_arm["stale"]["accuracy_current"], 3)
    if "reconcile" in per_arm and "append" in per_arm:
        verdict["reconcile_minus_append"] = round(
            per_arm["reconcile"]["accuracy_current"] - per_arm["append"]["accuracy_current"], 3)
    if "stale" in per_arm and "cold" in per_arm:
        verdict["stale_minus_cold"] = round(
            per_arm["stale"]["accuracy_current"] - per_arm["cold"]["accuracy_current"], 3)
    bits = [f"{a}={per_arm[a]['accuracy_current']}" for a in per_arm]
    verdict["headline"] = ("post-change CURRENT-fact accuracy — " + ", ".join(bits)
                           + f"; stale-answer rate stale={per_arm.get('stale',{}).get('stale_answer_rate')}"
                           + f" append={per_arm.get('append',{}).get('stale_answer_rate')}"
                           + f" reconcile={per_arm.get('reconcile',{}).get('stale_answer_rate')}")
    return {
        "experiment": "exp4_contradiction",
        "protocol": "intro(v1) -> change(v2 contradicts) -> post-change dependent question",
        "backend": backend, "model": model,
        "n_topics": len(TOPICS), "arms": list(all_recs.keys()),
        "per_arm": per_arm, "verdict": verdict, "wall_seconds": round(wall_s, 1),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="qwen2.5:7b-instruct")
    ap.add_argument("--stub", action="store_true")
    ap.add_argument("--arms", default=",".join(ARMS))
    ap.add_argument("--out", default=str(RESULTS_DIR / "summary.json"))
    args = ap.parse_args()
    backend = "stub" if args.stub else "ollama"
    arms = [a.strip() for a in args.arms.split(",") if a.strip()]
    for a in arms:
        if a not in ARMS:
            ap.error(f"unknown arm: {a}")

    seq = build_sequence()
    print(f"exp4_contradiction: backend={backend} model={args.model} arms={arms} "
          f"topics={len(TOPICS)} seq_len={len(seq)}", flush=True)
    t0 = time.time()
    all_recs: dict[str, list[dict]] = {}
    for arm in arms:
        print(f"\n=== arm: {arm} ===", flush=True)
        recs = run_arm(arm, seq, backend, args.model)
        all_recs[arm] = recs
        for r in recs:
            if r["role"] == "dep":
                flag = "OK " if r["correct"] else ("STALE" if r["served_stale"] else "XX ")
                print(f"  {flag:<5}[{r['task_index']:>2}] {r['slug']:<20} -> {r['output_preview'][:50]!r}",
                      flush=True)
            else:
                print(f"  ..   [{r['task_index']:>2}] {r['role']:<6} {r['slug']:<20} "
                      f"action={r.get('action')} wrote={int(bool(r.get('wrote')))}", flush=True)

    summary = build_summary(all_recs, backend, args.model, time.time() - t0)
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(summary, indent=2))
    print("\n=== verdict ===", flush=True)
    print(summary["verdict"]["headline"], flush=True)
    print(f"results: {out_path}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
