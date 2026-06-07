#!/usr/bin/env python3
"""exp7_wiring — does the SKILL.md PROSE, loaded into a model's context, actually INDUCE
the harvest behavior? (Exp1/4 test the python; this tests the trigger prose.)

The self-improvement loop only works if, when an agent hits a failure / gets corrected /
succeeds with a reusable fact, the verify-before-completion + wiki-memory SKILL bodies
actually make it HARVEST the lesson (run it through the gate, write it to the wiki). Exp1/4
exercise write_gate.py + wiki.py directly — they never check that the prose causes the
behavior. This does.

Method: for each scenario, ask a local model "what do you do next?" with the real SKILL.md
bodies in the system prompt (TREATMENT) vs a bare system prompt (CONTROL). Detect whether
the response FIRES the harvest (proposes gating/persisting the lesson to memory). A working
skill: high fire on should-fire scenarios under treatment, low under control, low false-fire
on should-not scenarios.

Metric: harvest-fire rate (treatment vs control) on should-fire; false-fire on should-not;
the treatment−control delta is the prose→behavior signal.

Usage:
  python3 run_wiring.py --model qwen2.5:7b-instruct
  python3 run_wiring.py --stub
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[1]
sys.path.insert(0, str(REPO_ROOT / "eval" / "exp1_compounding"))
from run_compounding import call_ollama  # noqa: E402

RESULTS_DIR = HERE / "results"
SKILL_PATHS = {
    "verify-before-completion": REPO_ROOT / "skills/verify-before-completion/SKILL.md",
    "wiki-memory": REPO_ROOT / "skills/wiki-memory/SKILL.md",
}

# Explicit decision marker. The model MUST end with `HARVEST: yes|no`; we parse THAT, not
# harvest vocabulary. A keyword detector mis-fires badly (cross-model finding): a model
# DECLINING to harvest still says "wiki"/"write-gate" because it's discussing the loaded
# skills — so vocabulary-presence ≠ a harvest decision. Asking for an explicit decision and
# parsing the last marker measures the harvest JUDGEMENT cleanly.
DECISION_SUFFIX = (
    "\n\nFINAL LINE REQUIRED: after your reply, output exactly one line — "
    "`HARVEST: yes` if this task produced a durable, project-specific lesson worth saving "
    "to long-term project memory, or `HARVEST: no` otherwise."
)
_HARVEST_RE = re.compile(r"harvest:\s*(yes|no)\b", re.IGNORECASE)


def parse_harvest_decision(output: str):
    """True (yes) / False (no) / None (no marker) from the LAST `HARVEST:` line."""
    matches = _HARVEST_RE.findall(output or "")
    if not matches:
        return None
    return matches[-1].lower() == "yes"

SCENARIOS = [
    # should-fire: durable, project-specific lessons (the three learning sources + a decision)
    {"id": "failure", "should_fire": True,
     "text": "I just ran `helios deploy` and it failed: 'unknown subcommand: deploy'. "
             "After digging in, the real command is `helios ship --wave N`. I fixed my script. "
             "What do you do next?"},
    {"id": "feedback", "should_fire": True,
     "text": "Code review rejected my PR: I named the env var `db_url`, but the project "
             "convention is `HELIOS_DB_URL` (the `HELIOS_` prefix). I corrected it. "
             "What do you do next?"},
    {"id": "success", "should_fire": True,
     "text": "Finally got the deploy working end-to-end — the trick was `helios ship --wave 3` "
             "with `max_retries=5`. Shipped successfully to prod. What do you do next?"},
    {"id": "failure2", "should_fire": True,
     "text": "The Helios build kept OOM-ing during webpack until I set "
             "`NODE_OPTIONS=--max-old-space-size=4096`; now it builds clean. What do you do next?"},
    {"id": "decision", "should_fire": True,
     "text": "We decided to back the Helios ledger with Postgres instead of Mongo because we "
             "need real ACID transactions across accounts. Locked in. What do you do next?"},
    # should-not-fire: nothing durable / project-specific to learn
    {"id": "trivial", "should_fire": False,
     "text": "Thanks, that's everything for now. What do you do next?"},
    {"id": "ephemeral", "should_fire": False,
     "text": "Quick sanity check: what is 2 + 2? What do you do next?"},
    {"id": "greeting", "should_fire": False,
     "text": "Hey, are you there? What do you do next?"},
    {"id": "general_knowledge", "should_fire": False,
     "text": "Out of curiosity, what is the capital of France? What do you do next?"},
    {"id": "ephemeral2", "should_fire": False,
     "text": "What's today's date? What do you do next?"},
]


def load_skill_bodies() -> str:
    blocks = []
    for name, p in SKILL_PATHS.items():
        if p.exists():
            blocks.append(f"# SKILL: {name}\n\n{p.read_text(encoding='utf-8')}")
    return "\n\n---\n\n".join(blocks)


SYSTEM_BARE = "You are a helpful coding assistant. Answer concisely with your next action."


def generate(backend: str, model: str, system: str, prompt: str, treated: bool, should_fire: bool) -> dict[str, Any]:
    if backend == "stub":
        # deterministic: treatment decides correctly (skill guidance present); control,
        # with only the bare one-line definition, decides conservatively "no".
        if treated:
            out = ("Considered. " + ("HARVEST: yes" if should_fire else "HARVEST: no"))
        else:
            out = "Noted.\nHARVEST: no"
        return {"output": out, "latency_ms": 1, "prompt_eval_count": 1, "eval_count": 1}
    return call_ollama(model, system, prompt)


def run(backend: str, model: str) -> dict[str, Any]:
    skill_body = load_skill_bodies()
    # both arms must emit the decision marker; treatment additionally carries the skill's
    # WHEN-to-harvest guidance, control gets only the bare one-line definition in the suffix.
    system_treated = (SYSTEM_BARE + "\n\n# Active skills (follow their guidance):\n\n"
                      + skill_body + DECISION_SUFFIX)
    system_control = SYSTEM_BARE + DECISION_SUFFIX
    records: list[dict[str, Any]] = []
    for sc in SCENARIOS:
        for treated in (False, True):
            system = system_treated if treated else system_control
            gen = generate(backend, model, system, sc["text"], treated, sc["should_fire"])
            decision = parse_harvest_decision(gen["output"])
            fired = decision is True
            correct = (fired == sc["should_fire"])
            records.append({
                "scenario": sc["id"], "should_fire": sc["should_fire"],
                "arm": "treatment" if treated else "control",
                "decision": decision, "fired": fired, "correct": correct,
                "output_preview": gen["output"][:200],
            })
            flag = "FIRE" if fired else ("----" if decision is False else "????")
            print(f"  [{'TRT' if treated else 'CTL'}] {sc['id']:<16} should_fire={int(sc['should_fire'])} "
                  f"{flag} {'OK' if correct else 'XX'}  {gen['output'][:50]!r}", flush=True)
    return {"records": records}


def build_summary(data: dict, backend: str, model: str, wall_s: float) -> dict:
    recs = data["records"]
    def rate(arm: str, should_fire: bool) -> float:
        sub = [r for r in recs if r["arm"] == arm and r["should_fire"] == should_fire]
        return round(sum(r["fired"] for r in sub) / max(len(sub), 1), 3)
    def acc(arm: str) -> float:
        sub = [r for r in recs if r["arm"] == arm]
        return round(sum(r["correct"] for r in sub) / max(len(sub), 1), 3)
    def abstain(arm: str) -> float:
        sub = [r for r in recs if r["arm"] == arm]
        return round(sum(r["decision"] is None for r in sub) / max(len(sub), 1), 3)
    trt_fire = rate("treatment", True)     # should-fire → decided yes (want high)
    ctl_fire = rate("control", True)
    trt_false = rate("treatment", False)   # should-not → decided yes = false-fire (want low)
    ctl_false = rate("control", False)
    trt_acc, ctl_acc = acc("treatment"), acc("control")
    verdict = {
        "decision_accuracy": {"treatment": trt_acc, "control": ctl_acc,
                              "treatment_minus_control": round(trt_acc - ctl_acc, 3)},
        "harvest_fire_should_fire": {"treatment": trt_fire, "control": ctl_fire,
                                     "treatment_minus_control": round(trt_fire - ctl_fire, 3)},
        "false_fire_should_not": {"treatment": trt_false, "control": ctl_false},
        "abstain_rate": {"treatment": abstain("treatment"), "control": abstain("control")},
        "headline": (f"harvest DECISION accuracy (explicit HARVEST: yes/no marker): "
                     f"treatment={trt_acc} vs control={ctl_acc} (delta {round(trt_acc-ctl_acc,3):+}); "
                     f"should-fire fire-rate treatment={trt_fire}; "
                     f"false-fire on should-not treatment={trt_false}"),
    }
    return {
        "experiment": "exp7_wiring",
        "protocol": "load real SKILL.md bodies; model emits explicit HARVEST: yes/no; measure decision accuracy vs control (bare definition)",
        "backend": backend, "model": model,
        "n_scenarios": len(SCENARIOS), "n_should_fire": sum(s["should_fire"] for s in SCENARIOS),
        "records": recs,
        "verdict": verdict, "wall_seconds": round(wall_s, 1),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="qwen2.5:7b-instruct")
    ap.add_argument("--stub", action="store_true")
    ap.add_argument("--out", default=str(RESULTS_DIR / "summary.json"))
    args = ap.parse_args()
    backend = "stub" if args.stub else "ollama"
    print(f"exp7_wiring: backend={backend} model={args.model} scenarios={len(SCENARIOS)}", flush=True)
    t0 = time.time()
    data = run(backend, args.model)
    summary = build_summary(data, backend, args.model, time.time() - t0)
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(summary, indent=2))
    print("\n=== verdict ===", flush=True)
    print(summary["verdict"]["headline"], flush=True)
    print(f"results: {out_path}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
