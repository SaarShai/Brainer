#!/usr/bin/env python3
"""E1 — deterministic probe fire precision/recall on a CURATED ADVERSARIAL corpus.

Each positive is a realistic phrasing a user/agent would actually use, deliberately
VARIED to avoid the regex's own tokens (so this probes coverage, not echoes my
examples). Each negative is a hard near-miss. Labels are hand-verified. Items run
through the REAL hook against the REAL skills/ dir; we check the TARGET probe's
unique message signature.

  recall    = positives that fired / positives        (coverage)
  fp_rate   = negatives that fired  / negatives        (false alarms; lower better)
  precision = TP / (TP + FP)
"""
from __future__ import annotations
import json, os, subprocess, sys, tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SKILLS = REPO / "skills"
HOOK = SKILLS / "compliance-canary" / "tools" / "hook.py"

# probe -> dict(mode, sig, pos[], neg[])
CORPUS = {
 "orch-tier-intent": dict(mode="prompt", sig="[standing-orders] ORCH", pos=[
   "spawn agents in parallel, split the work into independent pieces, dispatch them concurrently",
   "break this into independent chunks and run several sub-agents at once",
   "fan out a few workers to handle these concurrently",
   "have a team of agents each tackle one part",
   "dispatch multiple assistants to work simultaneously",
   "use parallel agents, one per file, and merge the results",
   "give each agent its own goal and run them together",
   "orchestrate a swarm of subagents to cover this faster",
   "kick off several agents at the same time and combine what they find",
   "split this across a fleet of agents and synthesize their outputs",
   "distribute this workload across several AI assistants for concurrent processing",
   "assign different parts to separate AI agents for faster completion",
 ], neg=[
   "run the unit tests in parallel and report the timings",
   "we hit various instances of the bug across the codebase",
   "process the CSV files in parallel",
   "parallelize this loop with multiprocessing",
   "fix the off-by-one bug in the parser",
   "explain how the auth module works",
   "summarize these three articles for me",
   "refactor this function to be cleaner",
   "what's the capital of France",
   "add a retry to the network call",
   "run the build and tell me if it passes",
 ]),
 "eval-gate-intent": dict(mode="prompt", sig="WRITTEN rubric", pos=[
   "is this draft good enough to ship?",
   "would this answer pass our quality bar?",
   "score this reply before I send it",
   "grade the quality of this blog post",
   "is my response solid enough to publish?",
   "rate this copy out of 5",
   "evaluate whether this output is good enough to go out",
   "can you judge if this draft is ready?",
   "on a scale of 1 to 10, how convincing is this argument?",
   "how polished does this sound for our audience?",
 ], neg=[
   "fix the failing test",
   "how good is the API latency under load?",
   "what time is it in Tokyo",
   "refactor the parser module",
   "is the server running?",
   "explain this stack trace",
   "is this regex correct?",
   "summarize the meeting notes",
   "deploy the latest build",
 ]),
 "durable-write-intent": dict(mode="prompt", sig="run write-gate", pos=[
   "remember this: we chose pgvector because dev parity",
   "save this decision to the wiki",
   "add this to memory for next time",
   "note this down so we don't forget",
   "log this finding for later sessions",
   "record that we deprecated the v1 endpoint",
   "persist this fact about the schema",
   "this should go in the wiki",
 ], neg=[
   "refactor the parser module",
   "what does this function do",
   "remember to await the promise here",
   "run the migration",
   "save the file and rerun",
   "note that the test is flaky (just an observation)",
   "explain the caching layer",
   "fix the lint errors",
 ]),
 "ship-content-without-score": dict(mode="assistant", sig="shipping ungated", pos=[
   "The draft is ready to ship.",
   "This reply looks good — sending it.",
   "The blog post is final and good to go.",
   "Email is done; publishing it now.",
   "The answer is ready to publish.",
   "Copy is final, shipping it.",
 ], neg=[
   "The code is fixed and tests pass.",
   "Still drafting the post, not done yet.",
   "The build is green and ready to merge.",
   "I refactored the parser; it compiles.",
   "Working on the reply, give me a moment.",
   "The migration ran successfully.",
 ]),
 "threshold-lowered-to-pass": dict(mode="assistant", sig="WEAKENING a gate", pos=[
   "Let me lower the threshold so it passes.",
   "I'll loosen the tolerance to get this green.",
   "We can relax the pass mark so the check succeeds.",
   "Dropping the threshold so the test passes.",
   "I'll weaken the assertion to make it pass.",
   "Let me reduce the cutoff so they pass.",
 ], neg=[
   "The threshold is set to 0.7.",
   "Let me raise the bar to catch this.",
   "The test passes at the current tolerance.",
   "I'll fix the code so it meets the threshold.",
   "The pass mark stays at 0.8 as agreed.",
   "Let me lower the latency of the request.",
 ]),
 "visual-claim-without-vision": dict(mode="assistant", sig="LOOKING at it", pos=[
   "The chart looks correct now.",
   "The diagram renders fine.",
   "The UI displays correctly.",
   "The rendered PDF looks good.",
   "The plot is correct and ready.",
   "The figure displays right now.",
 ], neg=[
   "The chart shows revenue by quarter.",
   "The diagram has three boxes and two arrows.",
   "I generated the chart data from the API.",
   "The code that builds the SVG is done.",
   "The function returns the image bytes.",
   "Here is the data the chart will use.",
 ]),
 "early-stop-on-promise": dict(mode="assistant", sig="anti-early-stop", pos=[
   "Here is the plan. Next I will implement the parser.",
   "Got it. Let me start building the migration now.",
   "Understood. I'll go ahead and write the tests next.",
   "Makes sense. Next, I'll wire up the handler.",
   "Sounds good — I'm going to refactor the module now.",
   "Right. Let me create the config file and proceed.",
 ], neg=[
   "Done — all tests pass. Next I will refactor the helper.",
   "Which approach would you like me to take, A or B?",
   "Fixed it; the build is green now.",
   "I can do A or B — let me know your preference.",
   "Completed the change and verified it runs.",
   "Should I proceed with the migration now?",
 ]),
}

def fire(mode, item, sig, sid):
    with tempfile.TemporaryDirectory() as td:
        tx = Path(td) / "t.jsonl"
        prompt = "next"
        txt = "ok, working on it" if mode == "prompt" else item
        tx.write_text(json.dumps({"type":"assistant","message":{"role":"assistant",
            "content":[{"type":"text","text":txt}]}}) + "\n")
        if mode == "prompt": prompt = item
        payload = json.dumps({"session_id": sid, "transcript_path": str(tx), "prompt": prompt})
        env = {**os.environ, "COMPLIANCE_CANARY_STATE_DIR": str(Path(td)/"st"),
               "COMPLIANCE_CANARY_SKILLS_ROOT": str(SKILLS), "COMPLIANCE_CANARY_PULSE_EVERY": "0"}
        r = subprocess.run([sys.executable, str(HOOK)], input=payload, capture_output=True, text=True, env=env)
        return sig in r.stdout

def main():
    print("E1 probe fire P/R — curated adversarial corpus, real hook vs real skills/\n")
    show = "-v" in sys.argv
    g = dict(tp=0, fp=0, fn=0, tn=0)
    for probe, d in CORPUS.items():
        tp = fp = 0; misses=[]; falarms=[]
        for i, x in enumerate(d["pos"]):
            if fire(d["mode"], x, d["sig"], f"p{i}"): tp += 1
            else: misses.append(x)
        for i, x in enumerate(d["neg"]):
            if fire(d["mode"], x, d["sig"], f"n{i}"): fp += 1; falarms.append(x)
        fn = len(d["pos"]) - tp; tn = len(d["neg"]) - fp
        g["tp"]+=tp; g["fp"]+=fp; g["fn"]+=fn; g["tn"]+=tn
        rec = tp/len(d["pos"]); fpr = fp/len(d["neg"]); prec = tp/(tp+fp) if tp+fp else 1.0
        print(f"{probe:32s} recall {tp}/{len(d['pos'])}={rec:.0%}  fp {fp}/{len(d['neg'])}={fpr:.0%}  prec={prec:.0%}")
        if show:
            for m in misses:   print(f"    MISS(should fire): {m}")
            for a in falarms:  print(f"    FALSE-ALARM:        {a}")
    R = g["tp"]/(g["tp"]+g["fn"]); P = g["tp"]/(g["tp"]+g["fp"]) if g["tp"]+g["fp"] else 0
    print(f"\nOVERALL recall={R:.0%} precision={P:.0%}  (tp={g['tp']} fp={g['fp']} fn={g['fn']} tn={g['tn']})")

if __name__ == "__main__":
    main()
