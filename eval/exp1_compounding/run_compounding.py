#!/usr/bin/env python3
"""exp1_compounding — does persisting lessons in wiki-memory make an agent improve
over a SEQUENCE of related tasks vs a cold-start agent?

Protocol (borrowed from StreamBench, not its code):
  * Tasks run in a FIXED order (eval/exp1_compounding/tasks.yaml).
  * Some tasks INTRODUCE a durable lesson; later tasks DEPEND on a lesson learnable
    from an earlier task. Facts live in a fictional "Project Helios" toolkit, so they
    are not in the model's pretraining — the lesson is the only reliable path to gold.
  * Per-task feedback/update: after each task an agent may persist its lesson; before
    each task it may retrieve prior lessons. We track longitudinal success over task
    index per arm.

Three arms (each starts from a FRESH `wiki.py init` temp dir):
  cold     — no memory. Each task standalone.
  memory   — BEFORE each task: retrieve from the per-arm wiki via `wiki.py search`,
             prepend the top hits' bodies to the prompt. AFTER each task: write the
             task's lesson_text through the gate (`write_gate.py gate`); ONLY on PASS
             do we persist via `wiki.py new` + append the lesson body + `wiki.py index`.
  poisoned — like memory, but lessons are written UNGATED (gate skipped) and the wiki
             is SEEDED with low-signal noise pages. Tests whether the gate earns its slot.

Generation backend:
  * Real:  POST to a local Ollama /api/generate (same contract as eval/runner.py).
  * Stub:  --stub uses a deterministic canned generator (no Ollama needed) so the
           wiki.py + write_gate.py wiring can be smoke-tested offline.

Output: results/summary.json — per-(arm, task_index) records + per-arm success curve
over task index + a headline verdict.

Usage:
  # offline smoke (no ollama), 1 task:
  python3 run_compounding.py --stub --limit 1
  # real run against local ollama:
  python3 run_compounding.py --model qwen2.5:7b-instruct
  # subset of arms / tasks:
  python3 run_compounding.py --stub --arms memory --limit 2
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError:  # pragma: no cover - resolved on Kaggle via pip install PyYAML
    yaml = None

HERE = Path(__file__).resolve().parent
# repo root: eval/exp1_compounding/ -> eval/ -> <root>
REPO_ROOT = HERE.parents[1]
WIKI_PY = REPO_ROOT / "skills" / "wiki-memory" / "tools" / "wiki.py"
GATE_PY = REPO_ROOT / "skills" / "write-gate" / "tools" / "write_gate.py"
TASKS_YAML = HERE / "tasks.yaml"
RESULTS_DIR = HERE / "results"

OLLAMA_URL = "http://127.0.0.1:11434/api/generate"

ARMS = ("cold", "memory", "poisoned")

# Low-signal noise the `poisoned` arm seeds before the sequence starts. These are
# vague/speculative and reference an unrelated fictional project, so a healthy gate
# would reject them — they exist to dilute retrieval and contradict nothing useful.
NOISE_PAGES = [
    ("misc-thoughts-one",
     "Maybe the system could probably be faster. I think we might want to look into "
     "things at some point. Anyway, nothing concrete yet."),
    ("misc-thoughts-two",
     "Project Zephyr notes: it seems like the dashboard could maybe use a refresh. "
     "Possibly. To recap, no decisions were made."),
    ("misc-thoughts-three",
     "Random reminder: the queue and the cache and the config all exist. We have a "
     "database. There are timestamps somewhere. Logs happen."),
]


# --------------------------------------------------------------------------- #
# Generation backends
# --------------------------------------------------------------------------- #
def call_ollama(model: str, system: str, prompt: str) -> dict[str, Any]:
    body = json.dumps({
        "model": model,
        "system": system,
        "prompt": prompt,
        "stream": False,
        "options": {"temperature": 0.0},
    }).encode()
    req = urllib.request.Request(OLLAMA_URL, data=body, headers={"Content-Type": "application/json"})
    t0 = time.time()
    try:
        with urllib.request.urlopen(req, timeout=300) as resp:
            data = json.loads(resp.read())
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, OSError) as e:
        # One flaky generation must not abort the whole longitudinal sequence —
        # record an empty (scored-as-wrong) output and keep going.
        detail = getattr(e, "reason", None) or str(e)
        return {"output": "", "latency_ms": int((time.time() - t0) * 1000),
                "prompt_eval_count": 0, "eval_count": 0, "error": str(detail)}
    return {
        "output": data.get("response", ""),
        "latency_ms": int((time.time() - t0) * 1000),
        "prompt_eval_count": data.get("prompt_eval_count", 0),
        "eval_count": data.get("eval_count", 0),
    }


def _stub_quoted_setting(prompt: str) -> str | None:
    """Pull the quoted raw setting name from a prompt, e.g. 'cache ttl' -> CACHE_TTL."""
    m = re.findall(r'"([a-z][a-z ]+)"', prompt.lower())
    for q in m:
        q = q.strip()
        # skip non-setting quotes like the deploy command examples
        if " " in q or q in {"db url", "cache ttl", "queue name", "event ts"}:
            return q.upper().replace(" ", "_")
    return None


def call_stub(model: str, system: str, prompt: str) -> dict[str, Any]:
    """Deterministic offline rule-applier for wiring smoke tests.

    Models the intended mechanism: a competent agent that, GIVEN the relevant
    convention in context (either spelled out in an introducer prompt or retrieved
    from a prior lesson), can APPLY that rule to produce the specific answer; and that
    WITHOUT the convention in context falls back to a wrong guess. This lets the
    offline smoke reproduce the compounding signal (memory > cold on dependents)
    without a real model — the rule lives in earlier lessons, so retrieval is what
    unlocks the dependent answers.
    """
    ctx = f"{system}\n{prompt}"
    ctx_l = ctx.lower()
    prompt_l = prompt.lower()

    def out(answer: str) -> dict[str, Any]:
        return {"output": answer, "latency_ms": 1,
                "prompt_eval_count": max(1, len(ctx) // 4),
                "eval_count": max(1, len(answer) // 4)}

    def pword(*words: str) -> bool:
        """Whole-word presence in the prompt (so 'format' != 'formatted')."""
        return any(re.search(rf"\b{re.escape(w)}\b", prompt_l) for w in words)

    has_prefix_rule = "helios_" in ctx_l and ("upper_snake_case" in ctx_l or "prefix" in ctx_l)
    has_ship_rule = "helios ship --wave" in ctx_l
    has_retry_rule = "max_retries=5" in ctx_l or ("max_retries" in ctx_l and "5" in ctx_l)
    has_log_rule = "/var/helios/run.log" in ctx_l
    has_tz_rule = "utc" in ctx_l and "z" in ctx_l and ("trailing" in ctx_l or "suffix" in ctx_l)

    # 0) Concrete value already spelled out verbatim in context (a lesson body, or an
    #    introducer prompt that states the exact token) AND topically relevant to the
    #    current prompt. The relevance guard stops a retrieved lesson for one topic
    #    from leaking its literal as the answer to an unrelated task.
    literal_rules = [
        ("helios ship --wave 3", ("deploy", "ship", "wave")),
        ("helios_db_url", ("db",)),
        ("/var/helios/run.log", ("log", "logs", "error", "errors", "look")),
        ("2026-01-01t00:00:00z", ("midnight", "render", "january")),
    ]
    for needle, prompt_cues in literal_rules:
        if needle in ctx_l and pword(*prompt_cues):
            idx = ctx_l.find(needle)
            return out(ctx[idx:idx + len(needle)])
    # the retry constant is stated as name + value, not glued; compose it.
    if "max_retries" in ctx_l and "value is 5" in ctx_l and pword("retry", "retries"):
        return out("max_retries=5")

    # 1) Config-key convention application (prefix rule).
    setting = _stub_quoted_setting(prompt)
    if setting and has_prefix_rule:
        key = f"HELIOS_{setting}"
        if pword("timestamp", "suffix", "timezone") and has_tz_rule:
            # composite task: key + timestamp suffix
            return out(f"{key} — value in UTC ISO-8601 with a trailing Z suffix")
        return out(key)

    # 2) Deploy command application.
    if has_ship_rule and pword("deploy", "ship", "wave"):
        if "wave 3" in prompt_l or "wave number 3" in prompt_l:
            return out("helios ship --wave 3")
        return out("helios ship --wave")

    # 3) Retry-policy application -> total attempts = 1 + retries.
    if has_retry_rule and pword("attempt", "attempts"):
        return out("6")

    # 4) Log path -> where to read errors / what is the log file.
    if has_log_rule and pword("error", "errors", "log", "logs", "look"):
        return out("/var/helios/run.log")

    # 5) Timestamp rule -> describe or format.
    if has_tz_rule:
        if pword("midnight", "format", "render"):
            return out("2026-01-01T00:00:00Z")
        return out("Timestamps are stored in UTC and rendered ISO-8601 with a trailing Z suffix.")

    # 6) cold/no-context fallback: a wrong guess (no convention available).
    return out("UNKNOWN_GUESS")


def generate(backend: str, model: str, system: str, prompt: str) -> dict[str, Any]:
    if backend == "stub":
        return call_stub(model, system, prompt)
    return call_ollama(model, system, prompt)


# --------------------------------------------------------------------------- #
# Scoring
# --------------------------------------------------------------------------- #
def score_output(output: str, gold: Any, scoring: str) -> bool:
    out = output.lower()
    if scoring == "keywords":
        kws = gold if isinstance(gold, list) else [gold]
        return all(str(k).lower() in out for k in kws)
    # exact-substring (case-insensitive). gold may be a list (any) or a string.
    golds = gold if isinstance(gold, list) else [gold]
    return any(str(g).lower() in out for g in golds)


# --------------------------------------------------------------------------- #
# wiki.py / write_gate.py shells
# --------------------------------------------------------------------------- #
def wiki(root: Path, *cli_args: str) -> dict[str, Any] | list[Any]:
    """Run `wiki.py --root <root> <args...>` and parse its JSON stdout."""
    cmd = [sys.executable, str(WIKI_PY), "--root", str(root), *cli_args]
    out = subprocess.run(cmd, text=True, capture_output=True)
    if out.returncode != 0:
        raise RuntimeError(f"wiki.py {' '.join(cli_args)} failed (rc={out.returncode}): {out.stderr[-500:]}")
    text = out.stdout.strip()
    return json.loads(text) if text else {}


def gate_pass(text: str, kind: str = "fact") -> tuple[bool, dict[str, Any]]:
    """Run `write_gate.py gate --json` — exit 0 PASS, 1 reject. Returns (passed, detail)."""
    cmd = [sys.executable, str(GATE_PY), "gate", "--kind", kind, "--json", "--text", text]
    out = subprocess.run(cmd, text=True, capture_output=True)
    detail: dict[str, Any] = {}
    if out.stdout.strip():
        try:
            detail = json.loads(out.stdout)
        except json.JSONDecodeError:
            pass
    # exit 0 == pass per the gate CLI contract
    return out.returncode == 0, detail


def persist_lesson(root: Path, task_id: str, lesson_text: str) -> str:
    """Create a wiki page via `wiki.py new`, append the lesson body, re-index.

    Honors the spec: persistence goes through `wiki.py new`. The page template only
    fills {{title}}/{{domain}}/{{date}}, so we append the durable lesson_text into the
    created file's body (under its Summary) and re-index so search/fetch see it.
    Returns the created page id (path stem) for retrieval bookkeeping.
    """
    res = wiki(root, "new", "--template", "page", "--title", task_id, "--domain", "experiments", "--slug", task_id)
    created_rel = res["created"] if isinstance(res, dict) else res[0]["created"]  # "concepts/<slug>.md"
    page_path = root / created_rel
    body = page_path.read_text(encoding="utf-8")
    # Append the lesson under a dedicated section so the indexed body carries the fact.
    body = body.rstrip() + "\n\n## Lesson\n\n" + lesson_text.strip() + "\n"
    page_path.write_text(body, encoding="utf-8")
    wiki(root, "index")
    return created_rel[:-3] if created_rel.endswith(".md") else created_rel  # id == path w/o .md


def retrieve(root: Path, query: str, k: int = 3) -> tuple[str, list[str]]:
    """Search the per-arm wiki, fetch top-k hit bodies, return (prepend_block, ids)."""
    hits = wiki(root, "search", query, "-k", str(k))
    if not isinstance(hits, list):
        return "", []
    blocks: list[str] = []
    ids: list[str] = []
    for h in hits[:k]:
        pid = h.get("id")
        if not pid:
            continue
        try:
            page = wiki(root, "fetch", pid)
        except RuntimeError:
            continue
        content = page.get("content", "") if isinstance(page, dict) else ""
        if content.strip():
            blocks.append(content.strip())
            ids.append(pid)
    if not blocks:
        return "", []
    block = "RELEVANT PROJECT MEMORY (retrieved from prior tasks):\n\n" + "\n\n---\n\n".join(blocks)
    return block, ids


def query_for(task: dict[str, Any]) -> str:
    """Build a retrieval query from the task prompt — keep it focused on Helios nouns."""
    prompt = task["prompt"]
    # pull the distinctive tokens (Helios + the quoted setting + key nouns)
    toks = re.findall(r"[A-Za-z_][A-Za-z0-9_]{2,}", prompt)
    keep = [t for t in toks if t.lower() in {
        "helios", "config", "key", "deploy", "command", "wave", "retry", "retries",
        "log", "logs", "error", "errors", "timestamp", "timezone", "utc", "cache",
        "queue", "ttl", "attempts", "event", "convention", "ship", "format",
    }]
    # include quoted raw setting names like "cache ttl"
    quoted = re.findall(r'"([^"]+)"', prompt)
    q = " ".join(quoted + keep[:12]) or "helios"
    return q


# --------------------------------------------------------------------------- #
# Arm runner
# --------------------------------------------------------------------------- #
SYSTEM = ("You are a precise assistant working inside the Project Helios toolkit. "
          "Use any provided project memory as ground truth. Answer exactly as instructed.")


def run_arm(arm: str, tasks: list[dict[str, Any]], backend: str, model: str) -> list[dict[str, Any]]:
    tmp = Path(tempfile.mkdtemp(prefix=f"exp1-{arm}-"))
    wiki_root = tmp / "wiki"
    wiki(wiki_root, "init")

    if arm == "poisoned":
        # Seed low-signal noise pages UNGATED, directly on disk + index.
        for slug, text in NOISE_PAGES:
            res = wiki(wiki_root, "new", "--template", "page", "--title", slug, "--domain", "experiments", "--slug", slug)
            created_rel = res["created"] if isinstance(res, dict) else res[0]["created"]
            p = wiki_root / created_rel
            p.write_text(p.read_text(encoding="utf-8").rstrip() + "\n\n## Note\n\n" + text + "\n", encoding="utf-8")
        wiki(wiki_root, "index")

    records: list[dict[str, Any]] = []
    for idx, task in enumerate(tasks):
        retrieved_ids: list[str] = []
        prompt = task["prompt"]
        system = SYSTEM
        if arm in ("memory", "poisoned"):
            block, retrieved_ids = retrieve(wiki_root, query_for(task), k=3)
            if block:
                system = SYSTEM + "\n\n" + block

        gen = generate(backend, model, system, prompt)
        correct = score_output(gen["output"], task["gold"], task.get("scoring", "exact"))

        # --- per-task feedback/update: persist the lesson for this task ---
        wrote = False
        gate_detail: dict[str, Any] = {}
        if arm == "memory":
            passed, gate_detail = gate_pass(task["lesson_text"], kind="fact")
            if passed:
                persist_lesson(wiki_root, task["id"], task["lesson_text"])
                wrote = True
        elif arm == "poisoned":
            # ungated: always persist (skip the gate entirely)
            persist_lesson(wiki_root, task["id"], task["lesson_text"])
            wrote = True
            gate_detail = {"skipped": True}

        records.append({
            "arm": arm,
            "task_index": idx,
            "task_id": task["id"],
            "source": task.get("source", "unspecified"),
            "depends_on_lesson": bool(task.get("depends_on_lesson")),
            "success": True,  # the task ran without error
            "correct": bool(correct),
            "tokens": int(gen.get("prompt_eval_count", 0)) + int(gen.get("eval_count", 0)),
            "prompt_eval_count": int(gen.get("prompt_eval_count", 0)),
            "eval_count": int(gen.get("eval_count", 0)),
            "latency_ms": int(gen.get("latency_ms", 0)),
            "retrieved_ids": retrieved_ids,
            "wrote_lesson": wrote,
            "gate_score": gate_detail.get("score"),
            "gate_passed": gate_detail.get("passed"),
            "output_preview": gen["output"][:160],
        })
    return records


# --------------------------------------------------------------------------- #
# Summary + verdict
# --------------------------------------------------------------------------- #
def build_summary(all_records: dict[str, list[dict[str, Any]]], tasks: list[dict[str, Any]],
                  backend: str, model: str, wall_s: float) -> dict[str, Any]:
    per_arm: dict[str, Any] = {}
    for arm, recs in all_records.items():
        success_curve = [int(r["correct"]) for r in sorted(recs, key=lambda r: r["task_index"])]
        dep = [r for r in recs if r["depends_on_lesson"]]
        intro = [r for r in recs if not r["depends_on_lesson"]]
        per_arm[arm] = {
            "n_tasks": len(recs),
            "correct_total": sum(r["correct"] for r in recs),
            "accuracy_total": round(sum(r["correct"] for r in recs) / max(len(recs), 1), 3),
            "accuracy_dependent": round(sum(r["correct"] for r in dep) / max(len(dep), 1), 3),
            "accuracy_introducer": round(sum(r["correct"] for r in intro) / max(len(intro), 1), 3),
            "tokens_total": sum(r["tokens"] for r in recs),
            "success_curve": success_curve,
            "records": sorted(recs, key=lambda r: r["task_index"]),
        }

    def dep_acc(arm: str) -> float | None:
        return per_arm[arm]["accuracy_dependent"] if arm in per_arm else None

    verdict: dict[str, Any] = {}
    if "memory" in per_arm and "cold" in per_arm:
        m, c = dep_acc("memory"), dep_acc("cold")
        verdict["memory_beats_cold_on_dependent"] = m > c
        verdict["memory_dependent_acc"] = m
        verdict["cold_dependent_acc"] = c
        verdict["dependent_acc_lift"] = round((m or 0) - (c or 0), 3)
    if "poisoned" in per_arm and "memory" in per_arm:
        p, m = dep_acc("poisoned"), dep_acc("memory")
        verdict["poisoned_degrades_vs_memory"] = p < m
        verdict["poisoned_dependent_acc"] = p
        verdict["poisoned_vs_memory_delta"] = round((p or 0) - (m or 0), 3)

    # --- per-source breakdown: the memory−cold lift on DEPENDENT tasks, split by
    #     the lesson's ORIGIN (failure / feedback / success). This is what shows the
    #     system learns from each of the three sources, not just "memory in general".
    sources = sorted({t.get("source", "unspecified") for t in tasks if t.get("depends_on_lesson")})
    per_source: dict[str, Any] = {}
    for src in sources:
        entry: dict[str, Any] = {}
        for arm, recs in all_records.items():
            dep = [r for r in recs if r["depends_on_lesson"] and r.get("source") == src]
            entry[arm] = {
                "n_dependent": len(dep),
                "accuracy_dependent": round(sum(r["correct"] for r in dep) / max(len(dep), 1), 3),
            }
        if "memory" in entry and "cold" in entry:
            entry["memory_minus_cold_lift"] = round(
                entry["memory"]["accuracy_dependent"] - entry["cold"]["accuracy_dependent"], 3)
        per_source[src] = entry
    if per_source:
        verdict["per_source_lift"] = {
            s: per_source[s].get("memory_minus_cold_lift") for s in per_source
        }

    headline_parts = []
    if "memory_beats_cold_on_dependent" in verdict:
        headline_parts.append(
            f"memory {'BEATS' if verdict['memory_beats_cold_on_dependent'] else 'does NOT beat'} "
            f"cold on lesson-dependent tasks "
            f"({verdict['cold_dependent_acc']}→{verdict['memory_dependent_acc']}, "
            f"lift {verdict['dependent_acc_lift']:+})"
        )
    if "poisoned_degrades_vs_memory" in verdict:
        headline_parts.append(
            f"poisoned {'DEGRADES' if verdict['poisoned_degrades_vs_memory'] else 'does NOT degrade'} "
            f"vs gated memory (Δ {verdict['poisoned_vs_memory_delta']:+})"
        )
    src_bits = [f"{s} {e['memory_minus_cold_lift']:+}"
                for s, e in per_source.items() if "memory_minus_cold_lift" in e]
    if src_bits:
        headline_parts.append("per-source memory−cold lift on dependents: " + ", ".join(src_bits))
    verdict["headline"] = "; ".join(headline_parts) if headline_parts else "single-arm run — no comparison"

    return {
        "experiment": "exp1_compounding",
        "protocol": "sequential tasks; per-task retrieve-before + gated-write-after; longitudinal success curve",
        "backend": backend,
        "model": model,
        "n_tasks": len(tasks),
        "n_dependent": sum(1 for t in tasks if t.get("depends_on_lesson")),
        "n_introducer": sum(1 for t in tasks if not t.get("depends_on_lesson")),
        "arms": list(all_records.keys()),
        "per_arm": per_arm,
        "per_source": per_source,
        "verdict": verdict,
        "wall_seconds": round(wall_s, 1),
    }


def load_tasks(path: Path, limit: int | None) -> list[dict[str, Any]]:
    if yaml is None:
        raise RuntimeError("PyYAML required: pip install PyYAML")
    data = yaml.safe_load(path.read_text())
    tasks = data["tasks"]
    if limit is not None:
        tasks = tasks[:limit]
    return tasks


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="qwen2.5:7b-instruct")
    ap.add_argument("--backend", default="ollama", choices=["ollama", "stub"])
    ap.add_argument("--stub", action="store_true", help="shortcut for --backend stub (offline wiring smoke)")
    ap.add_argument("--arms", default="cold,memory,poisoned",
                    help="comma-separated subset of arms to run")
    ap.add_argument("--limit", type=int, default=None, help="run only the first N tasks")
    ap.add_argument("--out", default=str(RESULTS_DIR / "summary.json"))
    ap.add_argument("--tasks", default=str(TASKS_YAML))
    args = ap.parse_args()

    backend = "stub" if args.stub else args.backend
    arms = [a.strip() for a in args.arms.split(",") if a.strip()]
    for a in arms:
        if a not in ARMS:
            ap.error(f"unknown arm: {a} (choices: {ARMS})")

    tasks = load_tasks(Path(args.tasks), args.limit)
    print(f"exp1_compounding: backend={backend} model={args.model} arms={arms} "
          f"tasks={len(tasks)}", flush=True)

    t0 = time.time()
    all_records: dict[str, list[dict[str, Any]]] = {}
    for arm in arms:
        print(f"\n=== arm: {arm} ===", flush=True)
        recs = run_arm(arm, tasks, backend, args.model)
        all_records[arm] = recs
        for r in recs:
            flag = "OK " if r["correct"] else "XX "
            mem = f" mem={r['retrieved_ids']}" if r["retrieved_ids"] else ""
            print(f"  {flag}[{r['task_index']:>2}] {r['task_id']:<24} "
                  f"dep={int(r['depends_on_lesson'])} wrote={int(r['wrote_lesson'])}{mem}", flush=True)

    summary = build_summary(all_records, tasks, backend, args.model, time.time() - t0)
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(summary, indent=2))

    print("\n=== verdict ===", flush=True)
    print(summary["verdict"]["headline"], flush=True)
    print(f"results: {out_path}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
