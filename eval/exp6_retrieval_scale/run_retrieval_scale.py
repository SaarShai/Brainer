#!/usr/bin/env python3
"""exp6_retrieval_scale — does top-k retrieval still surface the RIGHT lesson as the
wiki grows? Bridges Exp1 (does memory help) and Exp2 (is retrieval precise) at realistic
store sizes.

Exp1's wiki held a handful of pages, so retrieval was trivially precise. The real
question for a long-lived memory: as the store fills with hundreds of unrelated-but-
well-formed pages, does the needle (the one lesson that answers the task) stay in the
top-k, or does precision collapse under distractor pressure?

Setup: seed 5 needle lessons (each answers one dependent question), then grow the store
with D well-formed distractor pages (distinct Helios-ish subjects, none containing a
gold answer). At each D in a sweep, for every needle measure:
  * hit@3   — is the needle page in the top-3 search results for the task query?
  * correct — does the model answer the question correctly given the top-3 it retrieved?

Output: hit@3 and accuracy as a function of distractor count. Graceful decay = retrieval
scales; a cliff = the store needs better ranking / scoping before it grows.

Usage:
  python3 run_retrieval_scale.py --model qwen2.5:7b-instruct
  python3 run_retrieval_scale.py --stub
  python3 run_retrieval_scale.py --sweep 0,10,50,100,200
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
from run_compounding import (  # noqa: E402
    SYSTEM, call_ollama, persist_lesson, retrieve, score_output, wiki,
)

RESULTS_DIR = HERE / "results"
DEFAULT_SWEEP = [0, 10, 25, 50, 100, 200, 400]

NEEDLES = [
    {"slug": "n-deploy", "query": "helios deploy command wave ship", "match": "deploy wave 3",
     "lesson": "DECISION: The Project Helios deploy command is `helios ship --wave N`. "
               "Run `helios ship --wave 3` to deploy wave 3.",
     "dep_prompt": "What is the exact command to deploy wave 3 in Project Helios? "
                   "Answer with just the command.",
     "gold": "helios ship --wave 3"},
    {"slug": "n-dburl", "query": "helios config database url env var prefix", "match": "database url",
     "lesson": "DECISION: The Project Helios database URL is configured via the env var "
               "`HELIOS_DB_URL` (the `HELIOS_` UPPER_SNAKE_CASE prefix).",
     "dep_prompt": "What env var holds the Project Helios database URL? Answer with just the name.",
     "gold": "HELIOS_DB_URL"},
    {"slug": "n-retry", "query": "helios max_retries retry value attempts", "match": "max_retries",
     "lesson": "DECISION: Project Helios sets `max_retries=5` for outbound API calls.",
     "dep_prompt": "What is the value of `max_retries` in Project Helios? "
                   "Answer with just `max_retries=<n>`.",
     "gold": "max_retries=5"},
    {"slug": "n-log", "query": "helios runtime log file path error location", "match": "log file",
     "lesson": "DECISION: Project Helios writes its runtime log to `/var/helios/run.log`.",
     "dep_prompt": "What is the path to the Project Helios runtime log file? Answer with just the path.",
     "gold": "/var/helios/run.log"},
    {"slug": "n-cache", "query": "helios cache ttl config key", "match": "cache ttl",
     "lesson": "DECISION: The Project Helios cache time-to-live is set via `HELIOS_CACHE_TTL`.",
     "dep_prompt": "What config key sets the Project Helios cache TTL? Answer with just the key.",
     "gold": "HELIOS_CACHE_TTL"},
]

# Distractor subjects — well-formed Helios-ish pages on topics DISTINCT from the needles
# (and never containing a gold token). They are realistic retrieval competitors.
DISTRACTOR_SUBJECTS = [
    "metrics-exporter", "request-scheduler", "billing-reconciler", "auth-broker",
    "status-dashboard", "webhook-dispatcher", "feature-flagger", "blob-archiver",
    "schema-migrator", "trace-collector", "notification-fanout", "session-vault",
    "quota-manager", "image-thumbnailer", "search-reindexer", "audit-trailer",
    "graph-walker", "csv-importer", "locale-resolver", "sprite-packer",
]


def make_distractor(i: int) -> tuple[str, str]:
    subj = DISTRACTOR_SUBJECTS[i % len(DISTRACTOR_SUBJECTS)]
    n = i // len(DISTRACTOR_SUBJECTS)
    slug = f"d-{subj}-{i:04d}"
    body = (f"DECISION: The Project Helios {subj} module (variant {n}) processes batch "
            f"group {i} on a {3 + (i % 7)}-minute interval. It emits a `{subj}_done` signal "
            f"and persists state under the {subj} namespace. Owner: team-{i % 9}. "
            f"Tuned for throughput tier {i % 5}, it retries transient faults up to "
            f"{2 + (i % 4)} times before paging team-{i % 9}.")
    return slug, body


def generate(backend: str, model: str, system: str, prompt: str) -> dict[str, Any]:
    if backend == "stub":
        ctx = (system + "\n" + prompt).lower()
        for nd in NEEDLES:
            # answer correctly iff the needle gold is present in the retrieved context
            if nd["match"] in prompt.lower():
                if nd["gold"].lower() in ctx:
                    return {"output": nd["gold"], "latency_ms": 1,
                            "prompt_eval_count": len(ctx)//4, "eval_count": 4}
                return {"output": "UNKNOWN_GUESS", "latency_ms": 1,
                        "prompt_eval_count": len(ctx)//4, "eval_count": 2}
        return {"output": "UNKNOWN", "latency_ms": 1, "prompt_eval_count": len(ctx)//4, "eval_count": 2}
    return call_ollama(model, system, prompt)


def measure_point(root: Path, needle_ids: dict[str, str], backend: str, model: str,
                  k: int = 3) -> dict[str, Any]:
    recs = []
    for nd in NEEDLES:
        hits = wiki(root, "search", nd["query"], "-k", str(k))
        retrieved_ids = [h.get("id") for h in hits] if isinstance(hits, list) else []
        hit = needle_ids[nd["slug"]] in retrieved_ids
        block, used_ids = retrieve(root, nd["query"], k=k)
        system = SYSTEM + ("\n\n" + block if block else "")
        gen = generate(backend, model, system, nd["dep_prompt"])
        correct = score_output(gen["output"], nd["gold"], "exact")
        recs.append({"slug": nd["slug"], "hit_at_k": bool(hit), "correct": bool(correct),
                     "rank": (retrieved_ids.index(needle_ids[nd["slug"]]) + 1) if hit else None,
                     "retrieved_ids": retrieved_ids, "output_preview": gen["output"][:80]})
    n = len(recs)
    return {
        "hit_at_3": round(sum(r["hit_at_k"] for r in recs) / n, 3),
        "accuracy": round(sum(r["correct"] for r in recs) / n, 3),
        "records": recs,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="qwen2.5:7b-instruct")
    ap.add_argument("--stub", action="store_true")
    ap.add_argument("--sweep", default=",".join(str(x) for x in DEFAULT_SWEEP))
    ap.add_argument("--k", type=int, default=3)
    ap.add_argument("--out", default=str(RESULTS_DIR / "summary.json"))
    args = ap.parse_args()
    backend = "stub" if args.stub else "ollama"
    sweep = sorted({int(x) for x in args.sweep.split(",") if x.strip()})

    tmp = Path(tempfile.mkdtemp(prefix="exp6-"))
    root = tmp / "wiki"
    wiki(root, "init")
    # seed the 5 needles
    needle_ids: dict[str, str] = {}
    for nd in NEEDLES:
        needle_ids[nd["slug"]] = persist_lesson(root, nd["slug"], nd["lesson"])

    print(f"exp6_retrieval_scale: backend={backend} model={args.model} k={args.k} "
          f"needles={len(NEEDLES)} sweep={sweep}", flush=True)
    t0 = time.time()
    points: list[dict[str, Any]] = []
    added = 0
    for target in sweep:
        # grow the store incrementally to `target` distractors
        while added < target:
            slug, body = make_distractor(added)
            res = wiki(root, "new", "--template", "page", "--title", slug,
                       "--domain", "experiments", "--slug", slug)
            created = res["created"] if isinstance(res, dict) else res[0]["created"]
            p = root / created
            p.write_text(p.read_text(encoding="utf-8").rstrip() + "\n\n## Note\n\n" + body + "\n",
                         encoding="utf-8")
            added += 1
        wiki(root, "index")
        pt = measure_point(root, needle_ids, backend, args.model, k=args.k)
        pt["distractors"] = target
        pt["store_size"] = target + len(NEEDLES)
        points.append(pt)
        print(f"  D={target:>4} store={pt['store_size']:>4}  hit@{args.k}={pt['hit_at_3']}  "
              f"acc={pt['accuracy']}", flush=True)

    hit0 = points[0]["hit_at_3"] if points else None
    hitN = points[-1]["hit_at_3"] if points else None
    acc0 = points[0]["accuracy"] if points else None
    accN = points[-1]["accuracy"] if points else None
    summary = {
        "experiment": "exp6_retrieval_scale",
        "protocol": "5 needles + D distractors; hit@k and accuracy vs distractor count",
        "backend": backend, "model": args.model, "k": args.k,
        "n_needles": len(NEEDLES), "sweep": sweep,
        "points": points,
        "verdict": {
            "hit_at_k_start": hit0, "hit_at_k_end": hitN,
            "accuracy_start": acc0, "accuracy_end": accN,
            "hit_decay": round((hit0 or 0) - (hitN or 0), 3),
            "accuracy_decay": round((acc0 or 0) - (accN or 0), 3),
            "headline": (f"retrieval hit@{args.k} {hit0}→{hitN} and accuracy {acc0}→{accN} as the "
                         f"store grows from {len(NEEDLES)} to {(sweep[-1] if sweep else 0)+len(NEEDLES)} "
                         f"pages (decay: hit {round((hit0 or 0)-(hitN or 0),3):+}, "
                         f"acc {round((acc0 or 0)-(accN or 0),3):+})"),
        },
        "wall_seconds": round(time.time() - t0, 1),
    }
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(summary, indent=2))
    print("\n=== verdict ===", flush=True)
    print(summary["verdict"]["headline"], flush=True)
    print(f"results: {out_path}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
