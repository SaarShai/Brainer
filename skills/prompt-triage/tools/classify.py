#!/usr/bin/env python3
"""Fast task classifier for agents-triage hook.

Two-tier classifier:
  1. Regex fast-path (<5ms): pattern-match common simple tasks.
  2. Ollama fallback (<1500ms): local qwen3:8b one-shot classifier on uncertain.

Output (stdout, JSON one-line):
  {"tier": "simple|medium|hard|unknown",
   "agent": "wiki-note|quick-fix|research-lite|general-purpose|glm-executor|none",
   "model": "haiku|sonnet|opus",
   "confidence": 0.0-1.0,
   "reason": "<short>",
   "lean_context": ["paths or globs to load"]}

  Note: agent="glm-executor" routes to GLM-5.2 via z.ai (out-of-platform). Its
  `model` is "haiku" — that is the thin COORDINATOR subagent; the real inference
  runs on GLM through the agent's Bash call, billed to the user's z.ai account.
  See the 2026-06-19 policy note at the summarize rule below.

Called by UserPromptSubmit hook; stdout is injected into CC context.
"""
from __future__ import annotations
import json, os, re, sys, urllib.request
from pathlib import Path


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
    # Summarize / condense / rewrite THIS content. Routes to glm-executor.
    # POLICY (2026-06-19, supersedes the 2026-06-12 in-platform-only rule):
    # the original policy barred routing to out-of-platform models because a
    # context-blind subagent + billing was deemed too risky for auto-dispatch.
    # That is now OVERRIDDEN for the glm-executor agent specifically: it wraps
    # the out-of-platform call in a bounded coordinator (one call, capped
    # tokens, validated output, no fan-out), and these task shapes
    # (summarize/condense/rewrite of supplied content) are self-contained — the
    # subagent reads the file/content, it does not need chat history. GLM-5.2's
    # 1M context also handles large inputs that haiku truncates. Other rules
    # still route in-platform; only these bounded content tasks go to GLM.
    (r"\b(?:summari[sz]e|tldr|abstract|condense|rewrite)\b",
     "medium", "glm-executor", "haiku", 0.8, "bounded summarize/rewrite -- GLM-5.2",
     []),
    # Classify / label / extract / tag structured output from supplied content.
    # GLM-5.2 sweet spot (frontier-capable structured output, cheap, 1M ctx);
    # previously these fell through to opus or none. Self-contained like above.
    (r"\b(?:classif\w*|categor\w*|label\w*|tag\w*|extract\w*|normaliz\w*|parse\s+out)\b",
     "medium", "glm-executor", "haiku", 0.7, "bounded classify/extract -- GLM-5.2",
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
    r"written|changed|suggested|updated)|"
    r"your (?:last|previous|earlier|stated role|role|goal|instructions)|"
    r"are you sure|as discussed|earlier today|"
    r"so far|this session'?s)\b",
    re.I,
)


# Conversational continuations steer work already in flight — "continue",
# "do PROMPTER", "please apply all fixes", "let's skip m1". A fresh subagent
# has no idea what's in flight; routing these is always wrong (simulated-week
# sweep 2026-06-12: the LLM fallback routed 7+ of them). Anchored at start.
CONTINUATION_RE = re.compile(
    r"^\s*(?:continue\b|proceed\b|go ahead\b|go on\b|keep going\b|carry on\b|"
    r"resume\b|next\b|yes\b|yep\b|ok(?:ay)?\b|sure\b|sounds good\b|"
    r"do (?:it|that|this|the rest)\b|"
    r"please (?:do|continue|proceed|apply|fix (?:it|that|them|those|these))\b|"
    r"apply (?:all|the|those|these|it)\b|let'?s\b|that'?s\b|"
    r"now (?:do|try|run|the)\b|same (?:for|with)\b|and (?:then|also)\b|"
    r"again\b|retry\b|try again\b)",
    re.I,
)


def _needs_session_context(prompt: str) -> bool:
    folded = prompt.translate(_UNICODE_FOLD)
    return bool(CONTEXT_HINTS.search(folded)) or bool(CONTINUATION_RE.match(folded))


_SENSITIVE_EGRESS_RE = re.compile(
    r"\b(?:api[_-]?key|access[_-]?token|auth[_-]?token|password|passwd|"
    r"client[_-]?secret|private[_-]?key)\b\s*[:=]\s*[^\s,;]+|"
    r"\b(?:sk-(?:proj-)?[A-Za-z0-9_-]{16,}|AKIA[A-Z0-9]{16}|"
    r"gh[pousr]_[A-Za-z0-9]{20,})\b|"
    r"-----BEGIN [A-Z ]*PRIVATE KEY-----|"
    r"(?:^|[/\\\s])(?:\.env(?:\.[A-Za-z0-9_-]+)?|"
    r"\.ssh/(?:id_rsa|id_ed25519|authorized_keys)|\.aws/credentials|"
    r"\.config/gcloud/application_default_credentials\.json|etc/shadow)\b",
    re.I,
)

_CREDENTIAL_TERM_RE = re.compile(
    r"\b(?:api[_ -]?key|access[_ -]?token|auth[_ -]?token|password|passwd|"
    r"client[_ -]?secret|private[_ -]?key)\b",
    re.I,
)
_CREDENTIAL_FILE_RE = re.compile(
    r"(?<!\w)[~./\\\w-]*(?:credentials?|secrets?|passwords?)[\w.-]*\."
    r"(?:toml|json|ya?ml|ini|cfg|conf|env|txt|pem|key)\b",
    re.I,
)
_CREDENTIAL_SOURCE_RE = re.compile(
    r"\b(?:from|in|inside|within|under)\b[^\n]{0,80}?"
    r"(?:[~./\\\w-]+\.(?:toml|json|ya?ml|ini|cfg|conf|env|txt|pem|key)\b|"
    r"(?:app\s+)?(?:config|settings|credentials?|secrets?)(?:\s+file)?\b|"
    r"(?:what we did|(?:this|the current)\s+(?:session|conversation))\b)",
    re.I,
)


def _has_sensitive_egress(prompt: str) -> bool:
    """Credential value/path, credential-named file, or credential + source.

    The last form is deliberately verb-independent: access phrasing changes
    constantly (show/read/tell/get/what-is), while the risky invariant is a
    credential term tied to a concrete file or session source.
    """
    return bool(
        _SENSITIVE_EGRESS_RE.search(prompt)
        or _CREDENTIAL_FILE_RE.search(prompt)
        or (_CREDENTIAL_TERM_RE.search(prompt) and _CREDENTIAL_SOURCE_RE.search(prompt))
    )


# Imperative sentence-starts for multi-objective counting (field misroute,
# PROMPTER 2026-06-12: "look through X. find a method. document it. otherwise
# research..." routed research-lite/0.8 — four objectives, one cheap agent).
_IMPERATIVE_START = re.compile(
    r"^\s*(?:look|find|search|read|review|check|build|make|create|fix|add|"
    r"run|test|document|write|research|think|implement|install|deploy|"
    r"measure|compare|explain|update|sync|verify|otherwise)\b", re.I)


def _multi_objective(prompt: str) -> bool:
    """≥3 sentences opening with imperative verbs ⇒ a bundled brief, not a
    single dispatchable task."""
    n = 0
    for sent in re.split(r"[.!?\n;]+", prompt):
        if _IMPERATIVE_START.match(sent) and len(sent.split()) >= 3:
            n += 1
            if n >= 3:
                return True
    return False


def _looks_complex(prompt: str) -> bool:
    """Heuristic guard: long prompts or prompts containing complex-work phrases
    should never be regex-routed to the cheapest tier."""
    if len(prompt) > 800:
        return True
    if _multi_objective(prompt):
        return True
    # Multi-paragraph prompts are briefs, not single dispatchable tasks —
    # incident #6 (2026-06-12): a 3-workstream brief at 758 chars with zero
    # imperative-start sentences cheap-routed because "extract.py rewrite"
    # (noun, mid-list) hit the summarize rule's \brewrite\b. Cheap-routable
    # tasks are one-or-two-liners; structure means scope.
    if prompt.count("\n") >= 3:
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
    # No exact PREFERRED_MODELS hit ⇒ None (the docstring contract). The old
    # family-prefix fallback (`qwen3:8b`'s family "qwen3" matching ANY qwen3:*
    # tag) returned oversized variants — on a machine carrying only qwen3:32b /
    # llama3.1:70b it shipped a 30B+/70B model that blows the timeout AND pages
    # ~19GB in. Honour fail-closed: an exact small-tag pin or env override only.
    return None

LLM_PROMPT = """Classify this user task for an LLM agent. Output ONLY one-line JSON:
{"tier":"simple|medium|hard","agent":"wiki-note|quick-fix|research-lite|general-purpose|glm-executor|none","model":"haiku|sonnet|opus","confidence":0-1,"reason":"<15 words"}

Rules:
- simple = single file edit, add note, one-line fix, factual question, summarize
- If the task references the current conversation/session ("what we did", "this suite") output agent="none" — subagents cannot see chat history
- medium = multi-step but bounded (research a topic, refactor one file, write one script)
- hard = multi-file, architecture, design, novel reasoning
- A task bundling 3+ distinct objectives (e.g. review AND research AND implement AND test) is hard
- agent definitions: quick-fix = small scoped FILE EDITS only (never running tasks, tests, or simulations); wiki-note = wiki/markdown notes; research-lite = bounded web lookups; glm-executor = bounded summarize/rewrite/classify/extract over SUPPLIED content, routed to GLM-5.2/z.ai (use for self-contained content tasks, esp. large input — set model="haiku", the coordinator); general-purpose = everything else simple/medium
- agent="none" means fall through to main model (opus)
- Prefer lowest capable tier. Haiku ~$0.25/M-tok input; sonnet ~$3; opus ~$15. glm-executor is cheap + 1M ctx but out-of-platform — only for bounded self-contained content tasks, never anything needing chat history.
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
_VALID_AGENTS = {"wiki-note", "quick-fix", "research-lite", "general-purpose", "glm-executor", "none"}
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


# Per-agent acceptance gates (adopted 2026-07-01 from blader/arbitrage: "a
# dispatch without acceptance criteria is malformed — codex returns 'done'
# with red tests"). The gate names what the subagent's output must show
# before the main model accepts it; the directive binds escalation to a
# FAILED gate (observed), never to predicted difficulty. Keyed by agent —
# every routable agent in _VALID_AGENTS except "none" must have an entry
# (test-locked) so a routed directive always carries a gate.
GATES = {
    "wiki-note": "quote the changed wiki lines",
    "quick-fix": "show the edited hunk; rerun the named check (lint/test) green",
    "research-lite": "answer cites >=1 source URL",
    "glm-executor": "output matches the requested shape; spot-check 2 items against input",
    "general-purpose": "state what was verified and quote the check's output",
}


# Above this many chars, no cheap-route directive is ever emitted — not even
# on an LLM verdict. A 7B classifier rated a 4k-char multi-objective
# orchestration prompt "medium/research-lite" (2026-06-12); the cost asymmetry
# (cheap-routing complex work vs. main-model handling something simple) makes
# the hard gate the right default. Pin with AGENTS_TRIAGE_LENGTH_GATE.
try:
    LENGTH_GATE_CHARS = int(os.environ.get("AGENTS_TRIAGE_LENGTH_GATE", "1500"))
except ValueError:  # bad env value must degrade to the default, never crash the hook
    LENGTH_GATE_CHARS = 1500


# Harness-payload guard (live misfire, 2026-07-06): a `<task-notification>`
# harness payload (long, >1500 chars) hit the length-gate and got tier=hard,
# then — under escalate-up — the main model was told to dispatch a
# frontier-verifier subagent on it. These payloads are not user asks; they're
# the harness talking to the agent (task-notification / system-reminder /
# bracketed SYSTEM NOTIFICATION blocks). No verdict on one should ever carry
# an escalate-up directive. Matched on a short PREFIX scan (not a full-body
# regex) — these markers appear at or near the very start of the payload when
# the harness is the author; a user prompt that merely *mentions*
# "task-notification" deep in prose does not match.
_HARNESS_PAYLOAD_RE = re.compile(
    r"^\s*(?:<task-notification|<system-reminder|\[SYSTEM NOTIFICATION)",
    re.I,
)


def _is_harness_payload(prompt: str) -> bool:
    return bool(_HARNESS_PAYLOAD_RE.match(prompt))


def classify(prompt: str, use_ollama_fallback: bool = True) -> dict:
    # Sensitive egress outranks every routing route, including the otherwise
    # first session-context guard: a prompt can carry both, and context-shaped
    # wording must not reopen cross-vendor dispatch for credential material.
    if _has_sensitive_egress(prompt):
        return {"tier": "hard", "agent": "none", "model": "opus",
                "confidence": 1.0,
                "reason": "secret-like material or a sensitive credential path; cross-vendor routing vetoed",
                "lean_context": [], "source": "sensitive-egress-veto"}
    # Session-context guard runs before every ordinary classifier: no regex or
    # LLM can know what's in the conversation, so those prompts stay local.
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
    # Brief-shaped prompts are a HARD gate, same rank as length: ≥3
    # imperative-start sentences or ≥3 newlines means a bundled brief, and an
    # LLM "medium" verdict must not reopen it (simulated-week sweep
    # 2026-06-12: the 4-objective screenery brief re-routed via LLM medium
    # after the soft downgrade had closed the regex path).
    if _multi_objective(prompt) or prompt.count("\n") >= 3:
        return {"tier": "hard", "agent": "none", "model": "opus",
                "confidence": 1.0,
                "reason": "brief-shaped (multi-objective or multi-paragraph); main model handles briefs",
                "lean_context": [], "source": "brief-gate"}
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
    # Short prompts that matched NO regex rule are conversational replies, not
    # self-contained tasks ("do PROMPTER", "fix per discussion") — the LLM
    # fallback routed several in the simulated-week sweep. Self-contained
    # short tasks are exactly what RULES encode; no hit + short ⇒ silent,
    # don't even spend the LLM call.
    if not fast and len(prompt.strip()) < 80:
        return {"tier": "unknown", "agent": "none", "model": "opus",
                "confidence": 0.0,
                "reason": "short prompt with no rule match — likely conversational; defer",
                "lean_context": [], "source": "short-unmatched"}
    if use_ollama_fallback:
        llm = ollama_classify(prompt)
        if llm:
            llm["source"] = "ollama"
            llm.setdefault("lean_context", [])
            # Hint veto (codex review 2026-06-12): a 7B "simple" verdict does
            # not overrule complex-work hints — the LLM may still route medium,
            # but the cheapest tier on a hint-flagged prompt is exactly the
            # asymmetric mistake this skill must never make. Extended to any
            # regex-DOWNGRADED verdict (e.g. >120-char multi-clause git
            # prompts): the LLM must not reopen a route the regex layer
            # deliberately closed (simulated-week sweep 2026-06-12).
            downgraded = bool(fast and "downgraded" in fast.get("reason", ""))
            # The veto also fires when the LLM kept tier="medium" but still
            # named the CHEAPEST model (haiku) — _validate_llm_result passes any
            # in-enum model verbatim, so a medium/haiku verdict on an
            # audit/refactor-hinted prompt would otherwise dispatch high-stakes
            # work to haiku. Cheapest-model-on-a-hint-flagged-prompt is the same
            # asymmetric mistake whether the tier says simple or medium.
            cheap = llm.get("tier") == "simple" or llm.get("model") == "haiku"
            if cheap and (_looks_complex(prompt) or downgraded):
                return {"tier": "hard", "agent": "none", "model": "opus",
                        "confidence": 0.0,
                        "reason": "LLM picked the cheapest model but complex-work hints present; defer to main model",
                        "lean_context": [], "source": "hint-veto"}
            # Verbalized-confidence guard (research 2026-06-19): a local LLM's
            # SELF-REPORTED confidence is an unreliable routing signal — "in the
            # best case comparable to random routing" (arXiv:2502.00409, citing
            # Xiong et al. ICLR 2024 arXiv:2306.13063; corroborated 2502.04428).
            # So the 7B verdict's own confidence number must NOT, by itself,
            # clear the 0.7 emit gate. Require corroboration from the
            # deterministic regex layer (same agent, or same tier); when they
            # agree, trust the regex PRIOR's confidence, not the verbalized one.
            # Uncorroborated → push below the emit gate so the strongest (main)
            # model decides — the IPR empty-feasible-set→strongest fallback
            # pattern (arXiv:2509.06274). This is the safe asymmetric direction.
            corroborated = bool(fast and (
                fast.get("agent") == llm.get("agent")
                or fast.get("tier") == llm.get("tier")))
            if corroborated:
                llm["confidence"] = min(float(fast.get("confidence", 0.7)),
                                        float(llm.get("confidence", 0.7)))
                llm["source"] = "ollama+regex-corroborated"
            else:
                llm["confidence"] = 0.5  # < emit gate: advisory only, defers
                llm["source"] = "ollama-uncorroborated"
                llm["reason"] = (f"{llm.get('reason', '')} (uncorroborated LLM "
                                 "verdict; verbalized confidence not trusted — "
                                 "deferring to main model)")
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


# Escalate-UP mode (BRAINER_TRIAGE_ESCALATE_UP=1): today, a hard/agent-none
# verdict emits silence — correct when the SESSION model is already frontier
# (it handles hard prompts itself; team-lead only fires from a frontier main
# loop). Wrong when the session model is cheap: the hard prompt gets a cheap
# answer with no escalation path. Under this env flag, hard/agent-none instead
# emits a directive telling the (cheap) main model to spawn a frontier
# subagent. Default (env unset) stays byte-identical to today — proven by
# test_classify.py.
_VERIFY_INTENT_RE = re.compile(
    r"\b(?:verify|verifier|review|judge|audit|critique|grade|assess|evaluate|vet|"
    r"double[-\s]?check|sanity[-\s]?check|sign[-\s]?off|pass\/fail|"
    r"pass or fail|find\s+bugs?|red[-\s]?team|safe\s+to\s+ship|"
    r"correctness\s+risks?)\b",
    re.I,
)


# _AMBIGUOUS_VERIFY_RE — the subset of _VERIFY_INTENT_RE that is genuinely
# ambiguous between "judge existing work" and "plan/design something new":
# "evaluate"/"assess" show up both in genuine review asks ("evaluate whether
# this is safe to ship") and in planning asks ("evaluate two architecture
# options and design the migration plan"). Every OTHER verify word (review,
# audit, judge, double-check, sanity-check, find bugs, red-team, ...) is a
# strong, unambiguous verify signal — it does not also mean "plan this".
_AMBIGUOUS_VERIFY_RE = re.compile(r"\b(?:assess|evaluate)\b", re.I)


# Precedence between plan-intent and verify-intent (cross-vendor review P2 fix
# 2026-07-05, refined 2026-07-06 for verify-dominant+plan-tail misroute): a
# bare "plan verb present" test used to win unconditionally, which misrouted
# "I need you to double-check the auth flow and propose fixes" to the advisor
# even though the dominant ask is verification (double-check) and the trailing
# plan verb (propose fixes) just names the fix that verification should
# propose, not a separate planning ask. Plan-intent now only outranks
# verify-intent when the verify hit is one of the AMBIGUOUS words
# (evaluate/assess) — those genuinely go either way, so a co-occurring plan
# verb resolves the ambiguity toward "plan this" ("evaluate two architecture
# options and design the migration plan"). A STRONG, unambiguous verify verb
# (review/audit/judge/double-check/sanity-check/find bugs/red-team/...) always
# wins the verifier seat regardless of a trailing plan verb. Verify-only
# prompts (no plan verb at all) are unaffected; they still fall through to the
# verify-intent check below.
_PLAN_INTENT_RE = re.compile(
    r"\b(?:design|propose|architect)\b",
    re.I,
)


def _project_root() -> str:
    """Resolve the consuming project's root. CLAUDE_PROJECT_DIR is the
    mechanism Claude Code injects at hook invocation time (install.sh's
    HOOK_CMD relies on the same var: `${CLAUDE_PROJECT_DIR:-$PWD}`) — the
    authoritative source when a hook is actually running. Falls back to
    walking up from this file's own location (skills/prompt-triage/tools/
    classify.py -> parents[3] == repo root), the same fixed-depth idiom used
    by sibling tools (brainer-audit, task-retrospective, compliance-canary's
    hook_validate.py) — robust to whatever cwd a bare CLI/test invocation
    happens to run from, unlike os.getcwd()."""
    env = os.environ.get("CLAUDE_PROJECT_DIR")
    if env:
        return env
    try:
        return str(Path(__file__).resolve().parents[3])
    except Exception:
        return os.getcwd()


def _agent_def_installed(agent: str) -> bool:
    """Cheap, never-raising check that the escalate-up target's agent def is
    actually installed in the consuming project (cross-vendor review fix): a
    consumer that opted out of the frontier-advisor/frontier-verifier roster
    seats (.brainer-sync-optout, or never ran --adopt-agents) has no
    `.claude/agents/<agent>.md` file, so a directive naming that subagent
    points at nothing. Any exception (permission error, weird env value)
    degrades to "not installed" — silence is always the safe default here."""
    try:
        return os.path.exists(
            os.path.join(_project_root(), ".claude", "agents", f"{agent}.md"))
    except Exception:
        return False


def _escalate_up_agent(prompt: str) -> str:
    """Pick which frontier seat the escalate-up directive targets. Reuses the
    existing intent vocabulary (COMPLEX_HINTS' review/audit/critique overlap
    is deliberate — those already signal 'judge this', not 'plan this').

    A STRONG (unambiguous) verify verb always wins the verifier seat, even
    with a trailing plan verb present ("double-check the auth flow and
    propose fixes" -> verifier: the propose-tail names the fix the check
    should surface, not a separate planning ask). Plan/design-shaped prompts
    only get the advisor seat over verify-intent when the sole verify hit is
    one of the genuinely AMBIGUOUS words (evaluate/assess) — see
    _PLAN_INTENT_RE / _AMBIGUOUS_VERIFY_RE docstrings. Otherwise:
    verify/review/judge-shaped prompts get the cold verifier seat;
    plan/architecture/decision prompts (the default) get the advisor seat."""
    folded = prompt.translate(_UNICODE_FOLD)
    has_plan = bool(_PLAN_INTENT_RE.search(folded))
    verify_hit = _VERIFY_INTENT_RE.search(folded)
    if has_plan:
        if verify_hit and not _AMBIGUOUS_VERIFY_RE.fullmatch(verify_hit.group(0)):
            # A strong verify verb (not evaluate/assess) is present alongside
            # a plan verb -> verify-dominant+plan-tail: verifier wins.
            return "frontier-verifier"
        return "frontier-advisor"
    if verify_hit:
        return "frontier-verifier"
    return "frontier-advisor"


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
    # A sensitive-egress verdict is an absolute cross-vendor boundary. The
    # escalate-up feature may route other hard prompts to a frontier seat, but
    # must never reopen a verdict that exists specifically to keep credentials
    # in the current session boundary.
    if result.get("source") == "sensitive-egress-veto":
        return ""
    # If main-model required (tier=hard or agent=none), emit nothing — preserves
    # the prior hook.sh behavior of early-exiting on these classifications.
    if result.get("tier") == "hard" or result.get("agent") == "none":
        if (os.environ.get("BRAINER_TRIAGE_ESCALATE_UP") == "1"
                and not _is_harness_payload(prompt)):
            # Harness payloads (task-notification / system-reminder / SYSTEM
            # NOTIFICATION blocks) are exempt: they're the harness talking to
            # the agent, not a user ask, so there is no "task" to escalate
            # (live misfire, 2026-07-06).
            agent = _escalate_up_agent(prompt)
            # Guard (cross-vendor review): the consuming project may not have
            # adopted the frontier-advisor/frontier-verifier agent roster.
            # A directive naming a missing subagent is worse than silence —
            # fall through to the pre-escalate-up default (empty string).
            if not _agent_def_installed(agent):
                return ""
            return (
                "⚡ [agents-triage] Task classified:\n"
                f'{json.dumps({"tier": result.get("tier"), "agent": agent, "reason": result.get("reason")})}\n'
                f"This prompt needs frontier judgment but the session model is "
                f"cheap-tier. Dispatch via the Task tool to the `{agent}` "
                "subagent (its agent def pins model: opus as a frontier floor) "
                "with a self-contained brief. Accept its report; do not answer "
                "this yourself at cheap tier. Wrong call? User can resend with "
                "\"NO TRIAGE\". If the session model is already frontier-tier, "
                "handle it yourself; this directive is for cheap-tier sessions."
            )
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
    # Every emitted directive carries its acceptance gate (arbitrage adoption
    # 2026-07-01). Routed agents are guaranteed a GATES entry (test-locked).
    result["gate"] = GATES.get(result.get("agent"),
                               "state what was verified and quote the check's output")
    cls_json = json.dumps(result)
    # Directive trimmed 122→~70 tokens (2026-06-12 self-audit): the directive
    # is injected on EVERY routed prompt, so its own size is part of the
    # skill's cost. 2026-07-01: +~40 tokens buy the arbitrage rules — gate
    # check, two-strike ladder, observed-not-predicted — which close failure
    # modes #1/#4 (no escalation policy) and the main model's "faster to do
    # it myself" override.
    return (
        "⚡ [agents-triage] Task classified:\n"
        f"{cls_json}\n"
        "Dispatch via the Task tool to this subagent+model — skip deep "
        "thinking. Accept the result only if it passes `gate`. Escalate only "
        "on OBSERVED failure, never predicted difficulty ('this needs my "
        "judgment' is not a reason): on gate fail, retry ONCE with concrete "
        "corrective feedback, then take over, salvaging the partial output. "
        "Wrong call? User can resend with \"NO TRIAGE\"."
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
