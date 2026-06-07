#!/usr/bin/env python3
"""exp9_drift — do the anti-drift hooks (skill-pulse, compliance-canary) earn their
tokens? Measure instruction-adherence drift vs token cost, separately and combined.

These two skills pass correctness/latency tests but have NO in-repo proof they HELP.
This supplies it: efficiency = adherence-restored ÷ tokens injected.

Drift signal (LIFBench-style, model-agnostic — cf. the skills' own arXiv 2411.07037
citation): a single arbitrary instruction is stated ONCE at turn 0 — "end EVERY reply
with the exact line `[ack: HELIOS-7]`". The system prompt is NEUTRAL and the context
window is bounded, so as the conversation grows the rule scrolls out / loses salience
and adherence DECAYS (the model stops emitting the ack). Compliance per turn = ack
present. This is the clean, checkable instance of "a rule the agent should keep
following" — chosen because qwen2.5:7b is terse by default, so a verbosity signal floors.

(Earlier harness put the rule in the persistent system slot, which ollama re-sends at
full salience every turn → it never decayed → false floor. Fixed: rule lives once in the
growing transcript.)

Arms (same conversation, same model, temp 0):
  control — rule stated once, never repeated.
  pulse   — re-inject the rule every N=4 turns (skill-pulse: unconditional/periodic).
  canary  — if the previous reply DROPPED the ack, inject a targeted corrective before
            the next turn (compliance-canary: reactive).
  both    — pulse cadence + canary reactive.

Per turn we record adherence AND tokens injected. Then:
  uplift     = arm_adherence − control_adherence  (over the decay region)
  efficiency = uplift ÷ injected-tokens           (reactive should win)
  combination: does `both` beat the better single arm, or just double the cost?

Phase-1 gate: control adherence must DECAY (high early, lower late). If it stays ~100%
(no decay) or ~0% (model can't follow at all) → floor; honest finding, not a fake win.

Usage:
  python3 run_drift.py --model qwen2.5:7b-instruct
  python3 run_drift.py --stub
  python3 run_drift.py --arms control      # Phase-1 gate only
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[1]
sys.path.insert(0, str(REPO_ROOT / "eval" / "exp1_compounding"))
from run_compounding import call_ollama  # noqa: E402

RESULTS_DIR = HERE / "results"
ARMS = ("control", "pulse", "canary", "both")
PULSE_EVERY = 4
ACK = "[ack: HELIOS-7]"
RULE = f"IMPORTANT — for our ENTIRE session, end EVERY reply with this exact line on its own: {ACK}"
SYSTEM = "You are a concise coding assistant."
HISTORY_CAP = 2500  # bounded window — the seeded rule scrolls out as the transcript grows

# Verbose-tempting questions; the answers don't matter, only whether the ack survives.
TURNS = [
    "What does a hash map do?",
    "Walk me through how binary search works.",
    "Difference between a process and a thread?",
    "What are REST APIs?",
    "How does garbage collection work?",
    "What is a database index and why does it help?",
    "TCP vs UDP?",
    "What does a load balancer do?",
    "Walk me through the OSI model.",
    "How does HTTPS secure traffic?",
    "What is a deadlock and how do you avoid one?",
    "Explain the actor model.",
    "What is eventual consistency?",
    "How does a bloom filter work?",
    "Explain the CAP theorem.",
    "What does a reverse proxy do?",
    "How does DNS resolution work?",
    "Authentication vs authorization?",
    "B-tree vs binary tree?",
    "Name some rate-limiting strategies.",
    "What is a race condition?",
    "Explain memoization.",
    "Describe the pub/sub pattern.",
    "How does copy-on-write work?",
    "What is backpressure?",
    "Explain idempotency in APIs.",
]


def complied(out: str) -> bool:
    return ACK.lower() in out.lower()


def injection_for(arm: str, turn_idx: int, last_complied: bool | None) -> str:
    pulse_fires = arm in ("pulse", "both") and turn_idx > 0 and turn_idx % PULSE_EVERY == 0
    canary_fires = arm in ("canary", "both") and last_complied is False
    if pulse_fires:
        return "[system-reminder] " + RULE
    if canary_fires:
        return f"[system-reminder] DRIFT: your last reply dropped the required `{ACK}` line. Resume it on EVERY reply."
    return ""


def render_history(history: list[tuple[str, str]]) -> str:
    txt = "\n".join(f"{role}: {msg}" for role, msg in history)
    return txt[-HISTORY_CAP:]


def generate(backend: str, model: str, prompt: str, rule_in_window: bool, injected: bool) -> str:
    if backend == "stub":
        # stub: complies iff the rule is visible (in-window) OR re-injected this turn. Padded
        # to ~180 chars so the seeded rule scrolls out of HISTORY_CAP mid-run (exercises decay).
        pad = "This is a representative answer with enough length to grow the transcript window. "
        return (pad + ACK) if (rule_in_window or injected) else pad
    return call_ollama(model, SYSTEM, prompt)["output"]


def run_arm(arm: str, backend: str, model: str) -> list[dict[str, Any]]:
    # Seed the rule into the transcript (NOT the system slot) so it persists in-window and
    # scrolls out GRADUALLY as the conversation grows — that scroll-out is the drift mechanism.
    history: list[tuple[str, str]] = [("[session rule]", RULE)]
    last_complied: bool | None = None
    recs: list[dict[str, Any]] = []
    for i, turn in enumerate(TURNS):
        inj = injection_for(arm, i, last_complied)
        inj_tokens = max(0, len(inj) // 4) if inj else 0
        convo = render_history(history)
        rule_in_window = (RULE in convo) or bool(inj)
        prompt = convo + "\n\n"
        if inj:
            prompt += inj + "\n\n"
        prompt += f"User: {turn}\nAssistant:"
        out = generate(backend, model, prompt, rule_in_window, bool(inj)).strip()
        ok = complied(out)
        history.append(("User", turn))
        history.append(("Assistant", out))
        last_complied = ok
        recs.append({"turn": i, "complied": ok, "injected": bool(inj),
                     "injected_tokens": inj_tokens, "rule_in_window": rule_in_window,
                     "preview": out[-50:]})
    return recs


def summarize(all_recs: dict[str, list[dict]], backend: str, model: str) -> dict:
    per_arm: dict[str, Any] = {}
    for arm, recs in all_recs.items():
        scored = recs[1:]  # turn 0 introduces the rule; measure adherence from turn 1
        n = len(scored)
        per_arm[arm] = {
            "adherence": round(sum(r["complied"] for r in scored) / n, 3) if n else None,
            "compliance_curve": [int(r["complied"]) for r in recs],
            "injected_tokens_total": sum(r["injected_tokens"] for r in recs),
            "n_injections": sum(1 for r in recs if r["injected"]),
            "records": recs,
        }
    verdict: dict[str, Any] = {}
    if "control" in per_arm:
        cur = per_arm["control"]["compliance_curve"]
        # decay can be FAST (rule scrolls out after a few turns), so the "early" window is
        # the first scored turns, not the early third (which would dilute a fast drop).
        early = cur[1:5]
        late = cur[-max(1, len(cur) // 3):]
        e = round(statistics.mean(early), 2) if early else 0
        l = round(statistics.mean(late), 2) if late else 0
        verdict.update(control_adherence_early=e, control_adherence_late=l,
                       control_decays=(e >= 0.5 and l < e - 0.2))
    base = per_arm.get("control", {}).get("adherence")
    for arm in ("pulse", "canary", "both"):
        if arm in per_arm and base is not None and per_arm[arm]["adherence"] is not None:
            uplift = round(per_arm[arm]["adherence"] - base, 3)
            cost = per_arm[arm]["injected_tokens_total"]
            per_arm[arm]["uplift"] = uplift
            per_arm[arm]["efficiency_uplift_per_1k_tok"] = round(uplift / cost * 1000, 3) if cost else None
    for k in ("pulse", "canary", "both"):
        if k in per_arm:
            verdict[f"{k}_adherence"] = per_arm[k]["adherence"]
            verdict[f"{k}_uplift"] = per_arm[k].get("uplift")
            verdict[f"{k}_cost_tok"] = per_arm[k]["injected_tokens_total"]
            verdict[f"{k}_efficiency"] = per_arm[k].get("efficiency_uplift_per_1k_tok")
    if {"pulse", "canary", "both"} <= per_arm.keys():
        best_single = max(per_arm["pulse"].get("uplift") or 0, per_arm["canary"].get("uplift") or 0)
        verdict["both_beats_best_single"] = (per_arm["both"].get("uplift") or 0) > best_single + 1e-9
    return {"experiment": "exp9_drift", "backend": backend, "model": model,
            "n_turns": len(TURNS), "pulse_every": PULSE_EVERY, "history_cap": HISTORY_CAP,
            "ack": ACK, "arms": list(all_recs.keys()), "per_arm": per_arm, "verdict": verdict}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="qwen2.5:7b-instruct")
    ap.add_argument("--stub", action="store_true")
    ap.add_argument("--arms", default=",".join(ARMS))
    ap.add_argument("--out", default=str(RESULTS_DIR / "summary.json"))
    args = ap.parse_args()
    backend = "stub" if args.stub else "ollama"
    arms = [a.strip() for a in args.arms.split(",") if a.strip()]
    print(f"exp9_drift: backend={backend} model={args.model} arms={arms} turns={len(TURNS)}", flush=True)
    all_recs = {}
    for arm in arms:
        print(f"\n=== arm: {arm} ===", flush=True)
        recs = run_arm(arm, backend, args.model)
        all_recs[arm] = recs
        for r in recs:
            print(f"  t{r['turn']:>2} ack={'Y' if r['complied'] else '.'} "
                  f"{'<inj>' if r['injected'] else '     '} {r['preview']!r}", flush=True)
    summary = summarize(all_recs, backend, args.model)
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(summary, indent=2))
    v = summary["verdict"]
    print("\n=== verdict ===", flush=True)
    if "control_decays" in v:
        print(f"PHASE-1 GATE: control adherence early={v['control_adherence_early']} late={v['control_adherence_late']} "
              f"→ {'DECAYS (proceed)' if v['control_decays'] else 'NO DECAY (floor — not measurable here)'}", flush=True)
    for k in ("pulse_adherence", "pulse_uplift", "pulse_efficiency", "canary_adherence",
              "canary_uplift", "canary_efficiency", "both_uplift", "both_beats_best_single"):
        if k in v:
            print(f"  {k}: {v[k]}", flush=True)
    print(f"results: {args.out}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
