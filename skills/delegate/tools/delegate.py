from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from cost import preflight as cost_preflight


DEFAULT_MODELS = {
    "reasoning_top": ["opus", "gpt-frontier", "gemini-pro", "local:deepseek-r1:32b"],
    "coding_top": ["sonnet", "gpt-coding", "gemini-pro", "local:qwen-coder"],
    "medium": ["sonnet", "gpt-medium"],
    "lightweight": ["haiku", "gpt-low", "gemini-flash", "local:qwen3:8b"],
    "local": ["local:qwen3:8b", "local:gemma4:26b", "local:phi4:14b"],
    "high_context": ["local:turboquant", "long-context-api"],
}

EFFORT_GUIDANCE = {
    "reasoning_top": {"anthropic": "thinking: high", "openai": "reasoning.effort: high", "google": "thinking_budget: high", "local": "allow reasoning, concise final"},
    "coding_top": {"anthropic": "thinking: medium", "openai": "reasoning.effort: medium", "google": "thinking_budget: medium", "local": "code-focused prompt"},
    "medium": {"anthropic": "thinking: low/medium", "openai": "reasoning.effort: medium", "google": "thinking_budget: medium", "local": "bounded exploration"},
    "lightweight": {"anthropic": "thinking: low", "openai": "reasoning.effort: low", "google": "thinking_budget: low", "local": "concise; skip exploration"},
    "local": {"anthropic": "n/a", "openai": "n/a", "google": "n/a", "local": "single compact prompt"},
    "high_context": {"anthropic": "cache/retrieve first", "openai": "low effort unless synthesis", "google": "budget by task", "local": "TurboQuant/long-context server"},
}

PA_PREFIX_RE = re.compile(r"^\s*/(?:pa|btw)(?::|\s|$)", re.IGNORECASE)
WIKI_CONTEXT_RE = re.compile(r"\b(wiki|markdown|note|memory|document|ingest|project|repo|framework|decision|sop|l[0-4])\b", re.IGNORECASE)
FILE_CONTEXT_RE = re.compile(r"\b(file|path|code|test|bug|diff|function|class|module|script)\b", re.IGNORECASE)
WEB_CONTEXT_RE = re.compile(r"\b(web|online|latest|current|url|http|research|survey|compare|source)\b", re.IGNORECASE)
PATH_RE = re.compile(r"(?<![\w.-])(?:\.{0,2}/|/|[A-Za-z0-9_.-]+/)[^\s,;:]+")
DOCUMENTATION_RE = re.compile(r"\b(durable|verified|wiki-documenter|documenter|document important|document (?:the )?result|document results|record memory|write memory|l3 sop|sop)\b", re.IGNORECASE)
CODING_WORK_RE = re.compile(r"\b(implement|build feature|crud|debug|bug|refactor|review|code review|write tests?|fix failing|stack trace|endpoint|api|component)\b", re.IGNORECASE)


@dataclass
class Route:
    tier: str
    model_class: str
    suggested_model: str
    worker: str
    confidence: float
    parallelizable: bool
    context_policy: str
    reason: str

    def as_dict(self) -> dict[str, Any]:
        return self.__dict__.copy()


def load_models(path: Path | None = None) -> dict[str, list[str]]:
    if not path or not path.exists():
        return DEFAULT_MODELS
    models = {k: v[:] for k, v in DEFAULT_MODELS.items()}
    current = None
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw.split("#", 1)[0].rstrip()
        if not line:
            continue
        if not line.startswith(" ") and line.endswith(":"):
            current = line[:-1].strip()
            models.setdefault(current, [])
        elif current and line.strip().startswith("- "):
            models[current].append(line.strip()[2:])
    if "cheap" in models and "lightweight" not in models:
        models["lightweight"] = models["cheap"]
    if "frontier" in models and "reasoning_top" not in models:
        models["reasoning_top"] = models["frontier"]
    return models


def classify(task: str, registry: dict[str, list[str]] | None = None) -> Route:
    text = task.lower()
    models = registry or DEFAULT_MODELS
    high_risk = bool(re.search(r"\b(medical|legal|security|credential|delete|destructive|finance|privacy)\b", text))
    hard = bool(re.search(r"\b(architect|design|framework|multi[- ]?file|migration|novel|ambiguous|strategy|system)\b", text))
    research = bool(re.search(r"\b(research|survey|compare|find repos?|literature|web)\b", text))
    simple = bool(re.search(r"\b(typo|one[- ]?line|summari[sz]e|classify|extract|lint|format|small fix)\b", text))
    coding_work = bool(CODING_WORK_RE.search(task))
    repo_maintenance = bool(re.search(r"\b(commit|push|checkpoint|save progress|save-point|github|git status)\b", text))
    wiki = bool(re.search(r"\b(wiki|markdown|note|memory|document|ingest|l[0-4])\b", text))
    parallel = bool(re.search(r"\b(parallel|independent|separate|each of|split)\b", text)) or task.count("\n- ") >= 2

    if DOCUMENTATION_RE.search(task) and wiki:
        return Route("simple", "lightweight", models["lightweight"][0], "wiki-documenter", 0.88, False, "use compact verified evidence only; update wiki/log/index after retrieval", "durable wiki documentation task")
    if high_risk or hard:
        return Route("hard", "reasoning_top", models["reasoning_top"][0], "main-orchestrator", 0.86, parallel, "retrieve exact relevant context first", "high-risk or architectural task")
    if coding_work:
        return Route("medium", "coding_top", models["coding_top"][0], "coding-worker", 0.80, parallel, "map/search first; load only touched files and nearby tests", "serious coding task")
    if research:
        return Route("medium", "medium", models["medium"][0], "research-worker", 0.78, parallel, "search first, fetch cited sources only", "bounded research task")
    if repo_maintenance:
        return Route("simple", "lightweight", models["lightweight"][0], "repo-maintainer", 0.86, False, "inspect git status/remotes; stage intended files only", "GitHub repo save-point task")
    if wiki:
        return Route("simple", "lightweight", models["lightweight"][0], "wiki-worker", 0.84, False, "use wiki search/timeline/fetch", "wiki/documentation task")
    if simple:
        return Route("simple", "lightweight", models["lightweight"][0], "quick-worker", 0.82, False, "load mentioned files only", "simple bounded task")
    if "local" in text or "ollama" in text:
        return Route("simple", "local", models["local"][0], "local-worker", 0.76, False, "local model; compact prompt", "explicit local hint")
    return Route("medium", "medium", models["medium"][0], "general-worker", 0.62, parallel, "retrieve minimally, escalate if uncertain", "default bounded task")


def strip_pa_prefix(prompt: str) -> tuple[bool, str]:
    match = PA_PREFIX_RE.match(prompt)
    if not match:
        return False, prompt.strip()
    return True, prompt[match.end() :].strip()


def delegation_plan(task: str, registry: dict[str, list[str]] | None = None) -> dict[str, Any]:
    route = classify(task, registry)
    rejected = [tier for tier in ("reasoning_top", "coding_top", "medium", "lightweight", "local", "high_context") if tier != route.model_class]
    brief = {
        "worker": route.worker,
        "model": route.suggested_model,
        "scope": "only the files/sources named or retrieved as relevant",
        "output": "compact result packet: outcome, changed files, verification, sources, confidence, risks",
        "budget": "lightweight/local for simple; medium for bounded research; reasoning_top only for synthesis/risk",
    }
    steps = [
        "Main agent states goal and success criteria.",
        "Retrieve L1/wiki/search pointers before loading full context.",
        "Delegate independent bounded work using compact briefs." if route.parallelizable else "Handle or delegate one bounded worker task.",
        "Reject subagent reports missing sources/confidence.",
        "Orchestrator keeps final synthesis and final plan authorship.",
        "Main agent verifies result and records durable facts after success.",
    ]
    return {
        "task_class": route.tier,
        "route": route.as_dict(),
        "chosen_tier": route.model_class,
        "rejected_tiers": rejected,
        "effort": EFFORT_GUIDANCE.get(route.model_class, {}),
        "minimal_context_bundle": ["task", "success criteria", "only relevant paths/sources", "budget", "expected output"],
        "result_contract": ["outcome", "sources", "confidence", "verification", "changed files", "risks"],
        "orchestrator_rule": "Orchestrator does not delegate final synthesis.",
        "brief": brief,
        "steps": steps,
    }


def cost_control_packet(task: str, registry: dict[str, list[str]] | None = None) -> dict[str, Any]:
    """Compatibility alias for the provider-free cost preflight."""
    return cost_preflight(task)


def documentation_lifecycle_packet(task: str, evidence: str, verified: bool, registry: dict[str, list[str]] | None = None) -> dict[str, Any]:
    models = registry or DEFAULT_MODELS
    clean_evidence = evidence.strip()
    if not verified:
        return {
            "mode": "documentation_lifecycle",
            "action": "skip",
            "persist": False,
            "reason": "unverified evidence must not become durable memory",
            "task": task,
            "evidence": clean_evidence[:900],
        }
    if not clean_evidence:
        return {
            "mode": "documentation_lifecycle",
            "action": "skip",
            "persist": False,
            "reason": "no evidence supplied",
            "task": task,
            "evidence": "",
        }
    model = (models.get("lightweight") or DEFAULT_MODELS["lightweight"])[0]
    return {
        "mode": "documentation_lifecycle",
        "action": "route",
        "persist": True,
        "task": task,
        "worker": "wiki-documenter",
        "model_class": "lightweight",
        "suggested_model": model,
        "prompt": "prompts/subagents/wiki-documenter.prompt.md",
        "context_policy": "send only verified evidence, exact paths/commands/results, and candidate wiki targets; never send full transcript",
        "evidence_packet": clean_evidence[:1800],
        "result_contract": ["created", "updated", "evidence_used", "skipped_as_non_durable", "follow_up_risk"],
        "main_model_instruction": "Route this packet to a lightweight wiki-documenter after meaningful verified work; final synthesis stays with the main agent.",
    }


def mentioned_paths(task: str) -> list[str]:
    seen: set[str] = set()
    paths: list[str] = []
    for raw in PATH_RE.findall(task):
        path = raw.rstrip(".,);]")
        if path not in seen:
            seen.add(path)
            paths.append(path)
    return paths[:12]


def personal_assistant_packet(task: str, registry: dict[str, list[str]] | None = None) -> dict[str, Any]:
    invoked, clean_task = strip_pa_prefix(task)
    models = registry or DEFAULT_MODELS
    route_plan = delegation_plan(clean_task or task, registry)
    route = route_plan["route"]
    text = clean_task.lower()
    paths = mentioned_paths(clean_task)
    needs_wiki = bool(WIKI_CONTEXT_RE.search(text))
    needs_files = bool(paths or FILE_CONTEXT_RE.search(text))
    needs_web = bool(WEB_CONTEXT_RE.search(text))
    escalate = route["model_class"] == "reasoning_top" or route["confidence"] < 0.60
    context_bundle = {
        "include_full_transcript": False,
        "include_start_md": False,
        "include_l0_rules": True,
        "include_l1_index": needs_wiki,
        "wiki_queries": [clean_task] if needs_wiki and clean_task else [],
        "mentioned_paths": paths,
        "file_policy": "Load mentioned files only; if none are named, search compact indexes before fetching files." if needs_files else "Do not read repo files unless the handler proves relevance.",
        "web_policy": "Use current web/source retrieval and cite URLs." if needs_web else "No web search unless required by the task or uncertainty.",
        "memory_policy": "Search L1/wiki first for project facts; fetch full notes only after compact-hit relevance.",
        "token_budget": "Fit router brief under 500 tokens and handler brief under 1500 tokens by default.",
    }
    return {
        "mode": "personal_assistant",
        "invoked": invoked,
        "aliases": ["/pa", "/btw"],
        "bypass_context": True,
        "task": clean_task,
        "router": {
            "worker": "personal-assistant-router",
            "model_class": "lightweight",
            "suggested_model": (models.get("lightweight") or DEFAULT_MODELS["lightweight"])[0],
            "effort": EFFORT_GUIDANCE["lightweight"],
            "job": "classify prompt, choose cheapest capable handler, attach only needed context, escalate when unsafe.",
        },
        "handler": {
            "worker": route["worker"],
            "model_class": route["model_class"],
            "suggested_model": route["suggested_model"],
            "task_class": route_plan["task_class"],
            "effort": route_plan["effort"],
            "context_policy": route["context_policy"],
            "reason": route["reason"],
        },
        "context_bundle": context_bundle,
        "dispatch": {
            "action": "escalate_to_main" if escalate else "delegate_to_handler",
            "escalate_to_main": escalate,
            "parallelizable": route["parallelizable"],
            "orchestrator_keeps_final_synthesis": True,
        },
        "result_contract": {
            "format": "compact packet",
            "required": ["answer_or_outcome", "sources_or_evidence", "confidence", "verification", "risks"],
            "code_tasks_add": ["changed_files", "tests_run", "exact_errors"],
            "max_tokens": 900,
        },
        "main_model_instruction": "Do not answer a /pa prompt directly with the full context. Route this packet to the suggested handler, or handle only if dispatch.action is escalate_to_main.",
        "subagent_instruction": "You are the PA router. Preserve exact code, paths, numbers, math, and errors. Use cheapest capable model/context. Return only the compact result contract.",
    }


def personal_assistant_directive(packet: dict[str, Any]) -> str:
    handler = packet["handler"]
    context = packet["context_bundle"]
    dispatch = packet["dispatch"]
    lines = [
        "[token-economy:/pa] personal assistant route",
        "",
        f"Task: {packet['task']}",
        f"Action: {dispatch['action']}",
        f"Handler: {handler['worker']} on {handler['model_class']} ({handler['suggested_model']})",
        f"Effort: {handler['effort']}",
        "Context: no full transcript; no start.md reload; use L1/wiki only if listed below.",
        f"Wiki queries: {context['wiki_queries']}",
        f"Mentioned paths: {context['mentioned_paths']}",
        f"File policy: {context['file_policy']}",
        "",
        "Do not answer directly from the token-hungry model. Dispatch this compact packet unless escalation is required.",
        "Expected result: answer_or_outcome, sources_or_evidence, confidence, verification, risks; add changed_files/tests/exact_errors for code.",
    ]
    return "\n".join(lines)


def dumps(obj: Any) -> str:
    return json.dumps(obj, indent=2, sort_keys=True)
