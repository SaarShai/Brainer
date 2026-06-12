#!/usr/bin/env python3
"""Fast task classifier for agents-triage hook.

Two-tier classifier:
  1. Regex fast-path (<5ms): pattern-match common simple tasks.
  2. Ollama fallback (<1500ms): local qwen3:8b one-shot classifier on uncertain.

Output (stdout, JSON one-line):
  {"tier": "simple|medium|hard|unknown",
   "agent": "wiki-note|quick-fix|research-lite|general-purpose|none",
   "model": "haiku|sonnet|opus",
   "confidence": 0.0-1.0,
   "reason": "<short>",
   "lean_context": ["paths or globs to load"]}

Called by UserPromptSubmit hook; stdout is injected into CC context.
"""
from __future__ import annotations
import json, os, re, sys, urllib.request


def _extract_json_obj(text: str) -> dict | None:
    """Robust JSON-object extraction from possibly-noisy LLM output.

    M5 fix: the previous slice `text[text.find("{"): text.rfind("}")+1]` was
    fooled by stray braces in explanations like `the result is {tier:simple}` —
    the slice grabbed prose around the JSON. Now:
      1. Try a strict parse of the whole response first (fast path).
      2. Otherwise scan for the OUTERMOST balanced `{...}` block by tracking
         brace depth, ignoring braces inside double-quoted strings.
    Returns the parsed dict or None.
    """
    if not text:
        return None
    text = text.strip()
    # Fast path: whole response is JSON
    if text.startswith("{") and text.endswith("}"):
        try:
            obj = json.loads(text)
            if isinstance(obj, dict):
                return obj
        except Exception:
            pass
    # Slow path: scan for outermost balanced object
    depth = 0
    start = -1
    in_str = False
    esc = False
    for i, ch in enumerate(text):
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
            continue
        if ch == "{":
            if depth == 0:
                start = i
            depth += 1
        elif ch == "}":
            if depth == 0:
                continue
            depth -= 1
            if depth == 0 and start >= 0:
                candidate = text[start:i + 1]
                try:
                    obj = json.loads(candidate)
                    if isinstance(obj, dict):
                        return obj
                except Exception:
                    start = -1  # keep scanning for a later balanced block
    return None

# Normalization before any regex: unicode dashes/spaces fold to ASCII so
# `multi‑file` (U+2011) can't slip past the complex-hint guard, and quoted /
# code-fenced text is stripped so 'explain why "fix the typo" works' doesn't
# hit the quick-fix rule on QUOTED words (codex review 2026-06-12).
_UNICODE_FOLD = str.maketrans({
    "‐": "-", "‑": "-", "‒": "-", "–": "-", "—": "-",
    " ": " ", "‘": "'", "’": "'", "“": '"', "”": '"',
})
_QUOTED_RE = re.compile(r'"[^"\n]{0,200}"|\'[^\'\n]{0,200}\'|```[\s\S]*?```|`[^`\n]+`')


def _match_text(prompt: str) -> str:
    """The text regex rules and complex-hints run against."""
    return _QUOTED_RE.sub(" ", prompt.translate(_UNICODE_FOLD))


# Regex fast-path rules. Order matters — first match wins.
# Each rule: (pattern, tier, agent, model, confidence, reason, context_globs)
RULES = [
    # Wiki admin: add/append/note to wiki — IMPERATIVE form at start of prompt only.
    # The previous looser regex matched "write me a comprehensive markdown audit",
    # routing serious work to haiku. Now requires imperative-at-start AND a short prompt
    # (real wiki notes are short — "add a note to wiki that X").
    (r"^\s*(?:add|append|note|log|record)\b.{0,60}\b(?:wiki|markdown|kb|knowledge base)\b",
     "simple", "wiki-note", "haiku", 0.75, "imperative wiki add/edit pattern",
     ["**/*.md", "index.md"]),
    # One-line fix / quick edit / typo
    (r"\b(?:fix|correct|patch)\b\s+(?:this|the)?\s*(?:typo|import|syntax|linter?|one(?:-|\s)liner?)\b",
     "simple", "quick-fix", "haiku", 0.85, "one-liner fix",
     []),
    # Short factual question (no filesystem)
    (r"^\s*(?:what is|who is|when (?:was|is|did)|where (?:is|was)|define|meaning of)\b",
     "simple", "research-lite", "haiku", 0.85, "factual lookup", []),
    # Research BEFORE summarize (first-match-wins): "summarize and research
    # the literature" must route research-lite/medium, not local-ollama/simple
    # (codex review 2026-06-12 — the summarize rule was shadowing this one).
    (r"\b(?:research|survey|find repos?|investigate|literature)\b",
     "medium", "research-lite", "sonnet", 0.8, "research-lite task", []),
    # Summarize this file / path / log / etc. Routes to haiku (2026-06-12
    # policy: triage only routes to smaller IN-PLATFORM models — haiku/sonnet
    # in Claude Code — never out-of-platform local models; those are for
    # explicit manual dispatch only).
    (r"\b(?:summari[sz]e|tldr|abstract|condense|rewrite)\b",
     "simple", "general-purpose", "haiku", 0.8, "summarization -- haiku fine",
     []),
    # Install / setup / configure. Conf 0.6 (was 0.75): "configure the auth
    # system" is routinely complex — transcript mining (2026-06-12) found
    # 340-turn sessions triaged "simple setup". 0.6 forces the LLM fallback;
    # with no LLM available the directive gate (<0.7) keeps it silent.
    (r"\b(?:install|setup|configure|add\s+hook|register\s+mcp)\b",
     "simple", "quick-fix", "haiku", 0.6, "setup task", []),
    # Complex signals — multi-file refactor, architecture, design
    (r"\b(?:refactor|architect|design|redesign|implement.{0,20}system|multi[-\s]?file|across)\b",
     "hard", "none", "opus", 0.9, "complex task -- opus appropriate", []),
    # Commit/push — mechanical
    (r"^\s*(?:commit|push|git (?:add|commit|push|stash))\b",
     "simple", "quick-fix", "haiku", 0.9, "git mechanical", []),
    # Long-context local hint (no dedicated subagent yet; fall through to opus,
    # which the user can manually route to a local long-context model if needed).
    # Previous rule emitted agent="turboquant-local" but no such agent ships;
    # the dispatch failed silently. Treat as 'hard' so triage stays out of the way.
    (r"\b(?:long[-\s]?context|turboquant|kv[-\s]?cache|35b|70b|128k)\b",
     "hard", "none", "opus", 0.6,
     "long-ctx hint -- no local agent available, defer to main model",
     []),
]


def regex_classify(prompt: str) -> dict | None:
    text = _match_text(prompt)
    for pat, tier, agent, model, conf, reason, ctx in RULES:
        if re.search(pat, text, re.IGNORECASE):
            return {
                "tier": tier, "agent": agent, "model": model,
                "confidence": conf, "reason": reason,
                "lean_context": ctx,
            }
    return None


# Anti-pattern phrases that should never route to haiku via the fast regex path —
# regardless of which rule matched, if any of these appear, force LLM classification.
# These signal "complex / long / careful work" — exactly what cheap models botch.
COMPLEX_HINTS = re.compile(
    r"\b(?:comprehensive|deep|in[-\s]?depth|thorough|architect|design|"
    r"refactor|audit|analyze|investigate|debug|trace|root[-\s]?cause|"
    r"review|critique|production|critical|migrate|"
    r"multi[-\s]?file|across|system|integration)\b",
    re.I,
)


# Prompts that lean on the CURRENT conversation/session state can never be
# cheaply dispatched — a fresh subagent has no access to the chat history, so
# any directive forces the main model to evaluate-and-override (worse than
# silence; live incident 2026-06-12: "summarize what this current suite does"
# routed to a context-blind local model). Silence is the only safe verdict.
# Scope note: "this repo/branch/codebase" deliberately NOT matched — a
# subagent CAN read the filesystem, so those stay routable ("commit and push
# this branch" must keep its cheap route; codex round-3). Only references to
# the *conversation* — which no subagent can see — trigger the guard.
CONTEXT_HINTS = re.compile(
    r"\b(?:this (?:session|conversation|chat|thread)|"
    r"current (?:session|suite|state)|"
    r"our (?:previous|earlier|last) (?:conversation|session|chat|discussion)|"
    r"we(?:'ve| have| were| just)? (?:built|made|did|done|changed|"
    r"discuss(?:ed|ing)|decided|been (?:doing|working))|"
    r"you(?:'ve| have| were| just)? (?:said|did|done|made|created|wrote|"
    r"written|changed|suggested)|"
    r"your (?:last|previous|earlier)|as discussed|earlier today|"
    r"so far|this session'?s)\b",
    re.I,
)


def _needs_session_context(prompt: str) -> bool:
    return bool(CONTEXT_HINTS.search(prompt.translate(_UNICODE_FOLD)))


def _looks_complex(prompt: str) -> bool:
    """Heuristic guard: long prompts or prompts containing complex-work phrases
    should never be regex-routed to the cheapest tier."""
    if len(prompt) > 800:
        return True
    # Unicode-fold only — do NOT quote-strip here. Stripping quotes guards the
    # cheap-route rules against quoted bait (safe direction); stripping them
    # from the complex guard would REMOVE protection for quoted complex asks
    # (unsafe direction). The two matchers are deliberately asymmetric.
    if COMPLEX_HINTS.search(prompt.translate(_UNICODE_FOLD)):
        return True
    return False


def _smart_truncate(prompt: str, budget: int = 2000) -> str:
    """Head + tail truncation. Long stack-trace dumps end with an imperative
    ("fix this"); naive head-only truncation drops the actual task. Take the
    first 60% from the head and the last 40% from the tail."""
    if len(prompt) <= budget:
        return prompt
    head_len = int(budget * 0.6)
    tail_len = budget - head_len - len("\n...[truncated]...\n")
    return prompt[:head_len] + "\n...[truncated]...\n" + prompt[-tail_len:]


OLLAMA_URL = "http://127.0.0.1:11434/api/generate"
OLLAMA_TAGS_URL = "http://127.0.0.1:11434/api/tags"

# Fallback-model resolution. Hardcoding one tag rots silently when machines
# change (the shipped `qwen3:8b` default was absent on the dev machine for
# weeks — every LLM fallback failed silently and complex prompts fell through
# to the regex-low-conf path; caught 2026-06-12 when a misroute hit production).
# Resolution order:
#   1. AGENTS_TRIAGE_OLLAMA_MODEL env (explicit pin)
#   2. first PREFERRED_MODELS entry present in `ollama /api/tags` (exact, then
#      family-prefix match so qwen2.5:7b-instruct matches a qwen2.5:* tag)
#   3. None — caller falls back to fail-closed handling, never a random model
#      (a stray 30B+ reasoning model would blow the timeout AND page 19GB in).
PREFERRED_MODELS = [
    "qwen3:8b", "qwen2.5:7b-instruct", "llama3.1:8b", "gemma2:9b", "phi4:14b",
]


def _resolve_ollama_model(timeout: float = 1) -> str | None:
    env = os.environ.get("AGENTS_TRIAGE_OLLAMA_MODEL")
    if env:
        return env
    try:
        with urllib.request.urlopen(OLLAMA_TAGS_URL, timeout=timeout) as r:
            names = [m.get("name", "") for m in json.loads(r.read()).get("models", [])]
    except Exception:
        return None
    name_set = set(names)
    for pref in PREFERRED_MODELS:
        if pref in name_set:
            return pref
    for pref in PREFERRED_MODELS:
        family = pref.split(":")[0]
        for n in names:
            if n.split(":")[0] == family:
                return n
    return None

LLM_PROMPT = """Classify this user task for an LLM agent. Output ONLY one-line JSON:
{"tier":"simple|medium|hard","agent":"wiki-note|quick-fix|research-lite|general-purpose|none","model":"haiku|sonnet|opus","confidence":0-1,"reason":"<15 words"}

Rules:
- simple = single file edit, add note, one-line fix, factual question, summarize
- If the task references the current conversation/session ("what we did", "this suite") output agent="none" — subagents cannot see chat history
- medium = multi-step but bounded (research a topic, refactor one file, write one script)
- hard = multi-file, architecture, design, novel reasoning
- A task bundling 3+ distinct objectives (e.g. review AND research AND implement AND test) is hard
- agent="none" means fall through to main model (opus)
- Prefer lowest capable tier. Haiku ~$0.25/M-tok input; sonnet ~$3; opus ~$15.
- If task mentions "simple", "quick", "tiny" — bias simple.
- If task starts with imperative verb (add/fix/summarize/commit) — usually simple.

TASK: {task}
JSON:"""


def ollama_classify(prompt: str, model: str | None = None, timeout: float = 2) -> dict | None:
    """`timeout` is the TOTAL budget. Tag resolution and generation previously
    stacked their own timeouts (1s + 2s = 3s worst case on a hook path billed
    as 2s; codex round-3) — now resolution spends at most 0.5s and generation
    gets whatever remains of the single deadline."""
    import time as _time
    deadline = _time.monotonic() + timeout
    if model is None:
        model = _resolve_ollama_model(timeout=min(0.5, timeout / 4))
    if model is None:
        return None
    timeout = max(0.1, deadline - _time.monotonic())
    # Head + tail (was: head only at 800) — long stack-trace prompts ended
    # with the actual imperative; we used to drop it. 2000 chars ≈ 500 tokens.
    full = LLM_PROMPT.replace("{task}", _smart_truncate(prompt, 2000))
    if "qwen3" in model:
        full += " /no_think"
    data = json.dumps({
        "model": model, "prompt": full, "stream": False, "think": False,
        # keep_alive 2h: a cold 5GB model load blows the 2s timeout, so the
        # first fallback of a session may fail-closed (safe); keeping the
        # model resident makes every subsequent fallback hit the warm path.
        "keep_alive": "2h",
        "options": {"num_predict": 80, "temperature": 0.0, "seed": 42},
    }).encode()
    req = urllib.request.Request(OLLAMA_URL, data=data,
                                  headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            resp = json.loads(r.read()).get("response", "")
    except Exception:
        return None
    obj = _extract_json_obj(resp)
    if obj is None:
        return None
    return _validate_llm_result(obj)


_VALID_TIERS = {"simple", "medium", "hard"}
_VALID_AGENTS = {"wiki-note", "quick-fix", "research-lite", "general-purpose", "none"}
_VALID_MODELS = {"haiku", "sonnet", "opus"}


def _validate_llm_result(obj: dict) -> dict | None:
    """Reject wrong-but-parseable LLM output (codex review 2026-06-12): a
    schema echo like {"tier":"simple|medium|hard"} parses as JSON but must
    never reach emit_context. Enum-check tier/agent, coerce confidence."""
    tier = obj.get("tier")
    agent = obj.get("agent")
    if tier not in _VALID_TIERS or agent not in _VALID_AGENTS:
        return None
    try:
        conf = float(obj.get("confidence", 0))
    except (TypeError, ValueError):
        return None
    if not (0.0 <= conf <= 1.0):
        return None
    obj["confidence"] = conf
    # Model must be in-platform (codex round-3: a valid-agent response with
    # "model":"local:foo" slipped through). Out-of-enum → clamp to the
    # tier-appropriate platform default, never pass through verbatim.
    if obj.get("model") not in _VALID_MODELS:
        obj["model"] = {"simple": "haiku", "medium": "sonnet"}.get(tier, "opus")
    obj.setdefault("reason", "llm")
    obj["lean_context"] = obj.get("lean_context") or []
    return obj


# Above this many chars, no cheap-route directive is ever emitted — not even
# on an LLM verdict. A 7B classifier rated a 4k-char multi-objective
# orchestration prompt "medium/research-lite" (2026-06-12); the cost asymmetry
# (cheap-routing complex work vs. main-model handling something simple) makes
# the hard gate the right default. Pin with AGENTS_TRIAGE_LENGTH_GATE.
try:
    LENGTH_GATE_CHARS = int(os.environ.get("AGENTS_TRIAGE_LENGTH_GATE", "1500"))
except ValueError:  # bad env value must degrade to the default, never crash the hook
    LENGTH_GATE_CHARS = 1500


def classify(prompt: str, use_ollama_fallback: bool = True) -> dict:
    # Session-context guard runs FIRST: no classifier (regex or LLM) can know
    # what's in the conversation, so any verdict on these prompts is noise the
    # main model must spend tokens overriding.
    if _needs_session_context(prompt):
        return {"tier": "hard", "agent": "none", "model": "opus",
                "confidence": 1.0,
                "reason": "references current session context; subagents cannot see it",
                "lean_context": [], "source": "context-guard"}
    if len(prompt) > LENGTH_GATE_CHARS:
        return {"tier": "hard", "agent": "none", "model": "opus",
                "confidence": 1.0,
                "reason": f"prompt >{LENGTH_GATE_CHARS} chars; main model handles long briefs",
                "lean_context": [], "source": "length-gate"}
    fast = regex_classify(prompt)
    # "commit and push" earns 0.9 only when that's the WHOLE ask. A long
    # close-out prompt starting with "commit everything and push. check
    # there is nothing left running..." (replay audit 2026-06-12) bundles
    # work beyond quick-fix; downgrade below the directive gate.
    if fast and fast["reason"] == "git mechanical" and len(prompt) > 120:
        fast["confidence"] = 0.6
        fast["reason"] += " (downgraded: long multi-clause prompt)"
    # If the prompt contains complex-work hints (audit / refactor / architect /
    # comprehensive / etc), force LLM classification regardless of regex hit.
    # Cheap regex routing on complex prompts was sending high-stakes work to haiku.
    if fast and _looks_complex(prompt):
        fast["confidence"] = min(fast["confidence"], 0.6)
        fast["reason"] = f"{fast['reason']} (downgraded: complex-work hints)"
    if fast and fast["confidence"] >= 0.8:
        fast["source"] = "regex"
        return fast
    if use_ollama_fallback:
        llm = ollama_classify(prompt)
        if llm:
            llm["source"] = "ollama"
            llm.setdefault("lean_context", [])
            # Hint veto (codex review 2026-06-12): a 7B "simple" verdict does
            # not overrule complex-work hints — the LLM may still route medium,
            # but the cheapest tier on a hint-flagged prompt is exactly the
            # asymmetric mistake this skill must never make.
            if llm.get("tier") == "simple" and _looks_complex(prompt):
                return {"tier": "hard", "agent": "none", "model": "opus",
                        "confidence": 0.0,
                        "reason": "LLM said simple but complex-work hints present; defer to main model",
                        "lean_context": [], "source": "hint-veto"}
            return llm
    # Fail CLOSED on complex prompts: if the prompt carries complex-work hints
    # and no LLM was available to overrule the regex, never emit the (cheap)
    # regex route — defer to the main model. The old fail-open path shipped a
    # "Strong recommendation: dispatch to <cheap agent>" for a multi-objective
    # orchestration prompt (2026-06-12 incident).
    if fast and _looks_complex(prompt):
        return {"tier": "hard", "agent": "none", "model": "opus",
                "confidence": 0.0,
                "reason": "complex-work hints + LLM fallback unavailable; defer to main model",
                "lean_context": [], "source": "fail-closed"}
    if fast:
        fast["source"] = "regex-low-conf"
        return fast
    # Default: unknown → let opus handle
    return {"tier": "unknown", "agent": "none", "model": "opus",
            "confidence": 0.0, "reason": "no classifier signal",
            "lean_context": [], "source": "default"}


# Bypass-flag detector. L3 fix: previously `/opus` matched anywhere, including
# command paths like `git log /opus/file.md`. Now we anchor:
#   - "NO TRIAGE" / "NO-TRIAGE" / "NO_TRIAGE" can appear anywhere (it's distinctive enough)
#   - `/opus` must be at the start of the prompt (after optional whitespace) OR
#     be a slash-command-style token sitting on its own (word-boundary on both
#     sides — `/opus` followed by whitespace/EOL, not a path segment).
_NO_TRIAGE_RE = re.compile(r"\bNO[ _-]?TRIAGE\b", re.I)
_SLASH_OPUS_RE = re.compile(r"(?:^|\s)/opus(?=\s|$)")


def is_bypass(prompt: str) -> bool:
    if not prompt:
        return False
    if _NO_TRIAGE_RE.search(prompt):
        return True
    if _SLASH_OPUS_RE.search(prompt):
        return True
    return False


def _read_prompt_from_stdin() -> str:
    """Parse the CC UserPromptSubmit hook stdin payload. Tolerant of empty /
    malformed input — the hook must not crash on a weird payload."""
    # 1MB cap: hook payloads are small; an adversarially huge stdin should
    # cost bounded memory and fail closed, not stall the prompt.
    raw = sys.stdin.read(1_000_000)
    if not raw or len(raw) >= 1_000_000:
        return ""
    try:
        d = json.loads(raw)
    except Exception:
        return ""
    if not isinstance(d, dict):
        return ""
    prompt = d.get("prompt") or d.get("user_prompt") or ""
    # Hosts may send non-string prompts ({"prompt": 123}); regex calls on a
    # non-str crash the classifier (silently, behind hook.sh's stderr
    # suppression) — coerce, never trust the payload shape.
    return prompt if isinstance(prompt, str) else str(prompt)


def emit_context(prompt: str, use_ollama_fallback: bool = True) -> str:
    """H1 fix: produce the exact directive block hook.sh used to assemble — but
    inside the same Python process that parsed stdin and ran the classifier.
    Eliminates 3 of the 4 python3 spawns per UserPromptSubmit.

    Returns the directive string (possibly empty — caller should print as-is
    without a trailing newline injection). Empty string means "emit nothing"
    which causes the hook to inject no context.
    """
    if not prompt or is_bypass(prompt):
        return ""
    result = classify(prompt, use_ollama_fallback=use_ollama_fallback)
    # If main-model required (tier=hard or agent=none), emit nothing — preserves
    # the prior hook.sh behavior of early-exiting on these classifications.
    if result.get("tier") == "hard" or result.get("agent") == "none":
        return ""
    # A "Strong recommendation" below 0.7 confidence is miscalibrated language;
    # silence lets the main model proceed normally (the safe direction).
    try:
        if float(result.get("confidence", 0)) < 0.7:
            return ""
    except (TypeError, ValueError):
        return ""
    # Drop empty lean_context from the wire — pure noise when [].
    if not result.get("lean_context"):
        result.pop("lean_context", None)
    cls_json = json.dumps(result)
    # Directive trimmed 122→~70 tokens (2026-06-12 self-audit): the directive
    # is injected on EVERY routed prompt, so its own size is part of the
    # skill's cost. One imperative line beats three paragraphs of rationale.
    return (
        "⚡ [agents-triage] Task classified:\n"
        f"{cls_json}\n"
        "Dispatch via the Task tool to this subagent+model and return its "
        "result — skip deep thinking. Wrong call? User can resend with \"NO TRIAGE\"."
    )


def main():
    no_ollama = os.environ.get("AGENTS_TRIAGE_NO_OLLAMA") == "1"
    # --emit-context mode is the one invoked by hook.sh: it reads the hook
    # stdin payload, runs the bypass check, classifies, and prints the final
    # context block (or nothing). One process, end-to-end.
    if len(sys.argv) > 1 and sys.argv[1] == "--emit-context":
        prompt = _read_prompt_from_stdin()
        block = emit_context(prompt, use_ollama_fallback=not no_ollama)
        if block:
            print(block)
        return
    # Legacy / direct CLI mode: emit raw classifier JSON.
    if len(sys.argv) > 1:
        prompt = " ".join(sys.argv[1:])
    else:
        # Direct stdin mode (used by tests / manual invocation): treat the
        # entire stdin as the prompt text, OR parse it as a JSON hook payload.
        raw = sys.stdin.read()
        try:
            data = json.loads(raw)
            prompt = data.get("prompt") or data.get("user_prompt") or ""
        except Exception:
            prompt = raw
    out = classify(prompt, use_ollama_fallback=not no_ollama)
    print(json.dumps(out))


if __name__ == "__main__":
    main()
