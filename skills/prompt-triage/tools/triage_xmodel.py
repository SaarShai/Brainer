#!/usr/bin/env python3
"""Cross-model triage check: run the LLM-fallback path on this machine's
ollama with a labeled mini-corpus. Pass criteria: (a) model answers within
timeout, (b) JSON parses, (c) no complex prompt classified 'simple'."""
import json, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from classify import ollama_classify

MODEL = os.environ.get("XMODEL", "gemma2:9b")
CORPUS = [
    # (prompt, must_not_be_simple)
    ("review this project and write a goal for optimizing token usage, context window, memory management and delegation. run tests, research repos, identify patterns from session logs.", True),
    ("redesign the auth flow across the api gateway and both services", True),
    ("investigate why the deploy pipeline fails intermittently and fix the root cause", True),
    ("configure the production kubernetes ingress with TLS and rate limits", True),
    ("audit this repo for prompt-cache hygiene violations", True),
    ("fix the typo in README.md", False),
    ("what is the capital of France?", False),
    ("summarize this paragraph: the quick brown fox jumps over the lazy dog repeatedly.", False),
    ("commit and push", False),
    ("add a note to the wiki that we chose sqlite", False),
]

results, fails = [], 0
for prompt, must_not_simple in CORPUS:
    r = ollama_classify(prompt, model=MODEL, timeout=60)
    if r is None:
        results.append({"prompt": prompt[:60], "result": None, "ok": False})
        fails += 1
        continue
    tier = r.get("tier", "?")
    ok = not (must_not_simple and tier == "simple")
    if not ok:
        fails += 1
    results.append({"prompt": prompt[:60], "tier": tier,
                    "agent": r.get("agent"), "conf": r.get("confidence"), "ok": ok})

print(json.dumps({"model": MODEL, "n": len(CORPUS), "violations": fails,
                  "results": results}, indent=1))
sys.exit(1 if fails else 0)
