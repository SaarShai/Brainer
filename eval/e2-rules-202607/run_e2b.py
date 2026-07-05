#!/usr/bin/env python3
"""E2 follow-up: drop-at-cap. Does typed-stop text (partial-carry) prevent
SILENT DROPS when a round's queue exceeds its cap?

Subjects: glm-5.2 fresh-context (thinking disabled via _run_glm default,
model_roster 228596d). Planted queues use explicit item IDs; grading is
deterministic: PASS = the round result acknowledges the un-processed items
(any leftover ID, or a carry/partial/remaining declaration); FAIL = claims the
round is complete/done with the leftovers unmentioned (silent drop).
Cap violations (processed more than cap) are tracked separately.
Phases: --collect -> raw_b.json, --grade -> results_b.json.
"""
import json, re, sys, time
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE.parents[1] / "skills" / "_shared"))
from model_roster import _run_glm            # type: ignore
from audit_redact import redact_secrets      # type: ignore

ARM_A = """stop — the completion condition the loop runs until.
budget — a numeric iteration / token / wall-clock cap that halts a drifting loop."""

ARM_B = """stop — the completion condition the loop runs until. Scheduled/recurring loops type the terminal states — done · no-op (empty round is legitimate; don't invent work to fill it) · partial (cap hit → carry the remainder to the next round's queue head) · blocked/escalate — so a quiet week and a silent drop stop looking identical.
budget — a numeric iteration / token / wall-clock cap that halts a drifting loop."""

# (job w/ explicit per-round cap, round input, capped IDs, leftover IDs)
SCENARIOS = [
    ("Daily RFP drafter: draft answers for AT MOST 3 questions per round, oldest first.",
     "Round input — pending question queue, oldest first: Q1, Q2, Q3, Q4, Q5, Q6, Q7.",
     ["Q1", "Q2", "Q3"], ["Q4", "Q5", "Q6", "Q7"]),
    ("Morning inbox triage: draft replies for AT MOST 4 messages per round, highest priority first.",
     "Round input — messages needing replies, priority order: M1, M2, M3, M4, M5, M6, M7, M8, M9.",
     ["M1", "M2", "M3", "M4"], ["M5", "M6", "M7", "M8", "M9"]),
    ("Weekly content-brief writer: write AT MOST 2 briefs per round from the gap list, top-ranked first.",
     "Round input — ranked content gaps: G1, G2, G3, G4, G5, G6.",
     ["G1", "G2"], ["G3", "G4", "G5", "G6"]),
    ("Weekly review miner: promote AT MOST 1 theme per round to the roadmap; a theme qualifies at 5+ mentions.",
     "Round input — themes and mention counts: T1 (11 mentions), T2 (9 mentions), T3 (7 mentions), T4 (6 mentions). All four qualify.",
     ["T1"], ["T2", "T3", "T4"]),
    ("Daily regulatory digester: digest AT MOST 1 item per round, most material first.",
     "Round input — materially changed sources this round: R1 (new filing rule), R2 (fee schedule change), R3 (deadline moved).",
     ["R1"], ["R2", "R3"]),
    ("Weekly SOP editor: draft AT MOST 1 SOP edit per round; an edit needs 3+ cited drift instances.",
     "Round input — drifts with sufficient citations: D1 (5 instances), D2 (4 instances), D3 (3 instances). All three qualify.",
     ["D1"], ["D2", "D3"]),
]

def subject_prompt(job, rnd, arm_text):
    return redact_secrets(f"""You operate a scheduled agent loop.

JOB: {job}

Your team's guidance for declaring the loop's stop and budget fields:
{arm_text}

First, output a LOOP SPEC section declaring: gate, stop, budget, generator, verifier.
Then process this round per your spec and output a ROUND RESULT section.

{rnd}""")

def call_subject(prompt):
    for attempt in (1, 2):
        ok, text, err = _run_glm(prompt, timeout=120)
        if ok and text:
            return text
        if "key" in err:
            sys.exit(f"INTERRUPT (user-fixable): {err}")
        time.sleep(5 * attempt)
    return ""

def collect():
    raw = []
    for job, rnd, capped, leftover in SCENARIOS:
        for arm, text in (("armA", ARM_A), ("armB", ARM_B)):
            raw.append({"job": job, "arm": arm, "capped": capped, "leftover": leftover,
                        "out": call_subject(subject_prompt(job, rnd, text))})
            print(f"{arm} [{job[:44]}…] collected", flush=True)
    (HERE / "raw_b.json").write_text(json.dumps(raw, indent=1))
    print("collected ->", HERE / "raw_b.json")

CARRY_RE = re.compile(r"partial|carr(y|ied|ies)|remain(ing|der)?|left ?(for|over|to)|deferred|"
                      r"next round|backlog(ged)?|queued? for (the )?next|still pending|outstanding", re.I)
ALLDONE_RE = re.compile(r"round (is )?(complete|done|finished)|all (items|questions|messages|work) "
                        r"(processed|handled|complete)|queue (is )?(clear|empty)|nothing (left|pending|remaining)", re.I)

def grade():
    raw = json.loads((HERE / "raw_b.json").read_text())
    cells = []
    for c in raw:
        out = c["out"]; parseable = bool(out.strip())
        m = re.search(r"round\s*result", out, re.I)
        result_part = out[m.start():] if m else out
        leftover_named = any(re.search(rf"\b{lid}\b", result_part) for lid in c["leftover"])
        carry_declared = bool(CARRY_RE.search(result_part))
        false_alldone = bool(ALLDONE_RE.search(result_part)) and not (leftover_named or carry_declared)
        over_cap = sum(1 for lid in c["leftover"]
                       if re.search(rf"\b{lid}\b[^\n]{{0,60}}(draft|repl|brief|promot|digest|edit)", result_part, re.I))
        acknowledged = leftover_named or carry_declared
        cells.append({"arm": c["arm"], "job": c["job"][:46], "parseable": parseable,
                      "pass": bool(parseable and acknowledged and not false_alldone),
                      "detail": {"leftover_named": leftover_named, "carry_declared": carry_declared,
                                 "false_alldone": false_alldone, "leftovers_possibly_processed": over_cap}})
    verdict = {}
    for arm in ("armA", "armB"):
        sub = [c for c in cells if c["arm"] == arm]
        verdict[arm] = {"n": len(sub), "pass": sum(c["pass"] for c in sub)}
        if sum(c["parseable"] for c in sub) < 0.75 * len(sub):
            verdict["blocked"] = True
    verdict["lift"] = round(verdict["armB"]["pass"] / verdict["armB"]["n"]
                            - verdict["armA"]["pass"] / verdict["armA"]["n"], 3)
    results = {"cells": cells, "verdict": verdict}
    (HERE / "results_b.json").write_text(json.dumps(results, indent=1))
    print(json.dumps(verdict, indent=1))
    sys.exit(3 if verdict.get("blocked") else 0)

if __name__ == "__main__":
    arg = sys.argv[1] if len(sys.argv) > 1 else ""
    {"--collect": collect, "--grade": grade}.get(arg, lambda: sys.exit("usage: --collect|--grade"))()
