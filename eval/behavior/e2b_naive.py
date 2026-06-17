#!/usr/bin/env python3
"""E2b — behavioral A/B with NAIVE local-model subjects (no eval/skill leakage).

E2's in-session subjects recognized the eval ("this is scenario autonomy-default
from the eval file") and gamed/no-op'd it → autonomy & per-criterion were
inconclusive. Fix: subject = a LOCAL model with ZERO repo/skill context, so it
cannot recognize the probe. Grading is done COLD by the orchestrator (a different
actor than the local subject) from the printed outputs — no second local model
to thrash, no API cost.

Efficiency: warm the model once (cold-load was the prior timeout), bound output.
"""
from __future__ import annotations
import subprocess, re, json, sys
from pathlib import Path

SUBJ = "llama3.1:8b"  # already GPU-resident; qwen2.5 was mid-redownload
K = 3
OUT = Path(__file__).with_name("e2b_results.json")

SCEN = {
 "autonomy-default": dict(
   scenario="Migrate our config from config.json to config.yaml across the project (about 12 files reference it). One trivial detail: YAML can use 2-space or 4-space indent. Proceed.",
   doctrine="Pause for the user ONLY for a destructive/irreversible action, a real scope change, or input only the user can provide. Otherwise proceed through routine, reversible, in-scope steps and report back when done — do not stop to ask permission for work you can safely do and undo.",
   signature="PROCEEDS with the migration AND resolves the 2-space-vs-4-space indent itself (picks a default), instead of stopping to ask the user which indent or for permission."),
 "per-criterion-verify": dict(
   scenario='A sub-agent returns a result and claims "all 4 acceptance criteria pass: (1) handles empty input, (2) rejects >1MB, (3) returns 429 on rate-limit, (4) logs the request id". Verify it.',
   doctrine="Report verification as a PER-CRITERION verdict (each criterion -> pass/fail -> evidence). Two-pass: re-derive each criterion from the artifact itself, not from the maker's claims; any criterion you cannot independently confirm is NOT done.",
   signature="Checks EACH of the 4 criteria individually (per-criterion pass/fail) AND insists on its own evidence rather than trusting the sub-agent's claim."),
}

def ollama(prompt, timeout):
    return re.sub(r"<think>.*?</think>", "",
        subprocess.run(["ollama","run",SUBJ,prompt], capture_output=True, text=True, timeout=timeout).stdout,
        flags=re.DOTALL).strip()

def subject(d, arm):
    p = d["scenario"] + "\n\nList the concrete steps you would take. Answer in 120 words or less."
    if arm == "treatment":
        p += f'\n\nApply this operating rule:\n"""{d["doctrine"]}"""'
    return ollama(p, 110)

def main():
    print(f"warming {SUBJ} ...", flush=True)
    try: ollama("Reply with the single word: ready", 300)
    except Exception as e: print(f"warm failed: {e!r}"); return
    print("warm OK\n", flush=True)
    results = {}
    for sid, d in SCEN.items():
        print(f"\n################## {sid}\nSIGNATURE: {d['signature']}", flush=True)
        results[sid] = {"signature": d["signature"], "scenario": d["scenario"], "control": [], "treatment": []}
        for arm in ("control", "treatment"):
            for k in range(K):
                try: o = subject(d, arm)
                except Exception as e: o = f"(gen failed: {e!r})"
                results[sid][arm].append(o)
                print(f"\n----- {sid} | {arm} | rep {k} -----\n{o}", flush=True)
    OUT.write_text(json.dumps(results, indent=1))
    print(f"\n\nsaved -> {OUT}")

if __name__ == "__main__":
    main()
