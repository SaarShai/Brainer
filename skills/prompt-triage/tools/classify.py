#!/usr/bin/env python3
"""Fast task classifier for agents-triage hook.

Two-tier classifier:
  1. Regex fast-path (<5ms): pattern-match common simple tasks.
  2. Ollama fallback (<1500ms): local qwen3:8b one-shot classifier on uncertain.

Output (stdout, JSON one-line):
  {"tier": "simple|medium|hard|unknown",
   "agent": "wiki-note|quick-fix|research-lite|local-ollama|triage|none",
   "model": "haiku|sonnet|opus|local:<model>",
   "confidence": 0.0-1.0,
   "reason": "<short>",
   "lean_context": ["paths or globs to load"]}

Called by UserPromptSubmit hook; stdout is injected into CC context.
"""
from __future__ import annotations
import json, os, re, sys, urllib.request

# Regex fast-path rules. Order matters — first match wins.
# Each rule: (pattern, tier, agent, model, confidence, reason, context_globs)
RULES = [
    # Wiki admin: add/append/note to wiki
    (r"\b(?:add|append|write|note|log|record)\b.{0,40}\b(?:wiki|markdown|kb|knowledge base)\b",
     "simple", "wiki-note", "haiku", 0.9, "wiki add/edit pattern",
     ["**/*.md", "index.md"]),
    # One-line fix / quick edit / typo
    (r"\b(?:fix|correct|patch)\b\s+(?:this|the)?\s*(?:typo|import|syntax|linter?|one(?:-|\s)liner?)\b",
     "simple", "quick-fix", "haiku", 0.85, "one-liner fix",
     []),
    # Short factual question (no filesystem)
    (r"^\s*(?:what is|who is|when (?:was|is|did)|where (?:is|was)|define|meaning of)\b",
     "simple", "research-lite", "haiku", 0.85, "factual lookup", []),
    # Summarize this file / path / log / etc.
    (r"\b(?:summari[sz]e|tldr|abstract|condense|rewrite)\b",
     "simple", "local-ollama", "local:gemma4:26b", 0.8, "summarization -- local model fine",
     []),
    # Research: find repos, survey literature
    (r"\b(?:research|survey|find repos?|investigate|literature)\b",
     "medium", "research-lite", "sonnet", 0.8, "research-lite task", []),
    # Install / setup / configure
    (r"\b(?:install|setup|configure|add\s+hook|register\s+mcp)\b",
     "simple", "quick-fix", "haiku", 0.75, "setup task", []),
    # Complex signals — multi-file refactor, architecture, design
    (r"\b(?:refactor|architect|design|redesign|implement.{0,20}system|multi[-\s]?file|across)\b",
     "hard", "none", "opus", 0.9, "complex task -- opus appropriate", []),
    # Commit/push — mechanical
    (r"^\s*(?:commit|push|git (?:add|commit|push|stash))\b",
     "simple", "quick-fix", "haiku", 0.9, "git mechanical", []),
    # Explicit local/free/cheap hint
    (r"\b(?:cheap|local|free|no api|ollama)\b",
     "simple", "local-ollama", "local:qwen3:8b", 0.8, "explicit local hint", []),
    # Long-context local (TurboQuant KV compression candidate)
    (r"\b(?:long[-\s]?context|turboquant|kv[-\s]?cache|35b|70b|128k)\b",
     "medium", "turboquant-local", "local:turboquant", 0.8,
     "long-ctx local inference -- turboquant kv compression",
     []),
]


def regex_classify(prompt: str) -> dict | None:
    for pat, tier, agent, model, conf, reason, ctx in RULES:
        if re.search(pat, prompt, re.IGNORECASE):
            return {
                "tier": tier, "agent": agent, "model": model,
                "confidence": conf, "reason": reason,
                "lean_context": ctx,
            }
    return None


OLLAMA_URL = "http://127.0.0.1:11434/api/generate"

LLM_PROMPT = """Classify this user task for an LLM agent. Output ONLY one-line JSON:
{"tier":"simple|medium|hard","agent":"wiki-note|quick-fix|research-lite|local-ollama|turboquant-local|triage|none","model":"haiku|sonnet|opus|local:qwen3:8b|local:turboquant","confidence":0-1,"reason":"<15 words"}

Rules:
- simple = single file edit, add note, one-line fix, factual question, summarize
- medium = multi-step but bounded (research a topic, refactor one file, write one script)
- hard = multi-file, architecture, design, novel reasoning
- agent="none" means fall through to main model (opus)
- Prefer lowest capable tier. Haiku ~$0.25/M-tok input; sonnet ~$3; opus ~$15.
- If task mentions "simple", "quick", "tiny" — bias simple.
- If task starts with imperative verb (add/fix/summarize/commit) — usually simple.

TASK: {task}
JSON:"""


def ollama_classify(prompt: str, model: str = "qwen3:8b", timeout: int = 2) -> dict | None:
    full = LLM_PROMPT.format(task=prompt[:800])
    if "qwen3" in model:
        full += " /no_think"
    data = json.dumps({
        "model": model, "prompt": full, "stream": False, "think": False,
        "options": {"num_predict": 80, "temperature": 0.0, "seed": 42},
    }).encode()
    req = urllib.request.Request(OLLAMA_URL, data=data,
                                  headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            resp = json.loads(r.read()).get("response", "")
    except Exception:
        return None
    s = resp.find("{"); e = resp.rfind("}") + 1
    if s < 0 or e <= s: return None
    try:
        obj = json.loads(resp[s:e])
        obj.setdefault("lean_context", [])
        return obj
    except Exception:
        return None


def classify(prompt: str, use_ollama_fallback: bool = True) -> dict:
    fast = regex_classify(prompt)
    if fast and fast["confidence"] >= 0.8:
        fast["source"] = "regex"
        return fast
    if use_ollama_fallback:
        llm = ollama_classify(prompt)
        if llm:
            llm["source"] = "ollama"
            llm.setdefault("lean_context", [])
            return llm
    if fast:
        fast["source"] = "regex-low-conf"
        return fast
    # Default: unknown → let opus handle
    return {"tier": "unknown", "agent": "none", "model": "opus",
            "confidence": 0.0, "reason": "no classifier signal",
            "lean_context": [], "source": "default"}


def main():
    if len(sys.argv) > 1:
        prompt = " ".join(sys.argv[1:])
    else:
        data = json.loads(sys.stdin.read())
        prompt = data.get("prompt") or data.get("user_prompt") or ""
    no_ollama = os.environ.get("AGENTS_TRIAGE_NO_OLLAMA") == "1"
    out = classify(prompt, use_ollama_fallback=not no_ollama)
    print(json.dumps(out))


if __name__ == "__main__":
    main()
