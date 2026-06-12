#!/usr/bin/env python3
"""Deterministic regression tests for classify.py — no pytest, no network.

Every test runs with use_ollama_fallback=False so results are stable on any
machine. The fail-closed cases below regression-lock the 2026-06-12 incident:
a long multi-objective orchestration prompt matched the `research` regex,
got confidence-downgraded by the complex-hints guard, the LLM fallback was
silently dead (model tag not installed), and the hook still emitted a
"Strong recommendation" to dispatch to a cheap subagent.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from classify import (  # noqa: E402
    _resolve_ollama_model,
    classify,
    emit_context,
    is_bypass,
)

# The shape of the incident prompt: long (>800 chars), multi-objective, and
# carrying both a cheap-route regex keyword ("research") and complex-work hints.
# One copy (~1.1k chars) sits between the 800-char complex threshold and the
# 1500-char length gate — exercising fail-closed. Doubled (~2.2k chars) it
# crosses the length gate — exercising the short-circuit.
INCIDENT_PROMPT_MID = (
    "review this project and write a goal for yourself for optimizing this "
    "repo and set of skills for token usage, context window, learning and "
    "self-improving, memory management, delegation and orchestration. you may "
    "make changes to skills and tools that we built. you may run tests. "
    "i want to make sure that what we have is robust, well tested, functional, "
    "provides gains, reliable, and efficient. below are resources (e.g. github "
    "repos) you should review and decide how to use and learn from. "
    "you should review session logs and other documentation of previous "
    "sessions and try to identify patterns, repeated issues and obstacles, "
    "room for improvement and increased efficiency and reliability. "
    "research the available literature, survey the repos, investigate the "
    "failures, and audit the suite end to end. "
)
INCIDENT_PROMPT = INCIDENT_PROMPT_MID * 2  # past the 1500-char length gate


def test_simple_imperatives_still_route_cheap():
    r = classify("commit and push", use_ollama_fallback=False)
    assert r["tier"] == "simple" and r["model"] == "haiku", r
    assert r["source"] == "regex", r

    r = classify("what is the capital of France?", use_ollama_fallback=False)
    assert r["tier"] == "simple" and r["agent"] == "research-lite", r


def test_short_research_prompt_unchanged():
    r = classify("research the history of the QWERTY layout", use_ollama_fallback=False)
    assert r["tier"] == "medium" and r["agent"] == "research-lite", r
    assert r["source"] == "regex", r


def test_incident_prompt_fails_closed_without_llm():
    assert 800 < len(INCIDENT_PROMPT_MID) <= 1500, len(INCIDENT_PROMPT_MID)
    r = classify(INCIDENT_PROMPT_MID, use_ollama_fallback=False)
    assert r["tier"] == "hard", r
    assert r["agent"] == "none", r
    # "we built" in the prompt now trips the (earlier) context-guard; both
    # sources are the same safe verdict — hard/none, zero directive.
    assert r["source"] in ("fail-closed", "context-guard"), r
    # And the hook must emit NOTHING for it.
    assert emit_context(INCIDENT_PROMPT_MID, use_ollama_fallback=False) == ""


def test_complex_hints_alone_fail_closed_without_llm():
    # Short prompt, cheap-route keyword + complex hint ("audit").
    p = "research and audit the production deployment pipeline"
    r = classify(p, use_ollama_fallback=False)
    assert r["source"] == "fail-closed", r
    assert emit_context(p, use_ollama_fallback=False) == ""


def test_low_confidence_never_emits_directive():
    # Non-vacuous gate check (codex round-3: the old fixture was already
    # tier=hard, so it stayed silent even with the gate deleted). The setup
    # rule yields simple/quick-fix at conf 0.6 — routable agent+tier, silent
    # ONLY because of the <0.7 confidence gate.
    p = "install the hook"
    r = classify(p, use_ollama_fallback=False)
    assert r["tier"] == "simple" and r["agent"] == "quick-fix", r
    assert r["confidence"] < 0.7, r
    assert emit_context(p, use_ollama_fallback=False) == ""
    # legacy fixture (tier-hard path) still silent too
    assert emit_context("we need the 70b long-context variant for this",
                        use_ollama_fallback=False) == ""


def test_high_confidence_simple_emits_directive():
    out = emit_context("commit and push", use_ollama_fallback=False)
    assert "agents-triage" in out and "haiku" in out, out[:200]


def test_bypass_flags():
    assert is_bypass("NO TRIAGE just do it")
    assert is_bypass("/opus think hard about this")
    assert not is_bypass("cat /opus/file.md")
    assert emit_context("NO TRIAGE research everything", use_ollama_fallback=False) == ""


def test_length_gate_blocks_cheap_route_even_with_llm():
    # >1500 chars → hard/none regardless of fallback availability; the gate
    # must short-circuit BEFORE any LLM call (so this stays offline-stable).
    r = classify(INCIDENT_PROMPT, use_ollama_fallback=True)
    assert r["source"] in ("length-gate", "context-guard"), r
    assert r["tier"] == "hard" and r["agent"] == "none", r
    assert emit_context(INCIDENT_PROMPT, use_ollama_fallback=True) == ""


def test_env_pin_wins_model_resolution():
    os.environ["AGENTS_TRIAGE_OLLAMA_MODEL"] = "pinned:tag"
    try:
        assert _resolve_ollama_model() == "pinned:tag"
    finally:
        del os.environ["AGENTS_TRIAGE_OLLAMA_MODEL"]


def test_research_outranks_summarize_on_mixed_prompts():
    # round-2 codex: summarize rule shadowed research under first-match-wins.
    r = classify("summarize and research the available literature on X", use_ollama_fallback=False)
    assert r["agent"] == "research-lite" and r["tier"] == "medium", r
    # plain summarize routes to haiku in-platform (never local-ollama —
    # 2026-06-12 policy: triage targets platform models only)
    r2 = classify("summarize this paragraph for me", use_ollama_fallback=False)
    assert r2["agent"] == "general-purpose" and r2["model"] == "haiku", r2


def test_quoted_bait_does_not_trigger_cheap_rules():
    # round-2 codex: quick-fix regex fired on QUOTED text.
    p = 'explain why the prompt "fix the typo" routes to haiku'
    r = classify(p, use_ollama_fallback=False)
    assert r.get("agent") != "quick-fix", r
    # ...but quoted complex hints still protect (asymmetric stripping):
    p2 = 'please "refactor the system" end to end'
    from classify import _looks_complex
    assert _looks_complex(p2)


def test_unicode_hyphen_complex_hint_detected():
    # round-2 codex: U+2011 in `multi‑file` bypassed COMPLEX_HINTS.
    from classify import _looks_complex
    assert _looks_complex("fix this multi‑file refactoring issue")


def test_llm_schema_echo_and_garbage_rejected():
    # round-2 codex: wrong-but-parseable LLM dicts must not reach emit_context.
    from classify import _validate_llm_result
    assert _validate_llm_result({"tier": "simple|medium|hard", "agent": "wiki-note|quick-fix"}) is None
    assert _validate_llm_result({"tier": "simple"}) is None                       # missing agent
    assert _validate_llm_result({"tier": "simple", "agent": "rm-rf"}) is None     # bad enum
    assert _validate_llm_result({"tier": "simple", "agent": "quick-fix",
                                 "confidence": "0-1"}) is None                    # bad conf
    assert _validate_llm_result({"tier": "simple", "agent": "quick-fix",
                                 "confidence": 1.7}) is None                      # out of range
    # missing model → clamped to the tier default (haiku for simple)
    ok = _validate_llm_result({"tier": "simple", "agent": "quick-fix", "confidence": 0.9})
    assert ok and ok["model"] == "haiku" and ok["lean_context"] == [], ok


def test_non_string_prompt_never_crashes():
    # round-2 audit: {"prompt": 123} crashed is_bypass (regex on int) —
    # silently, behind hook.sh stderr suppression.
    import subprocess
    here = Path(__file__).parent
    for payload in ['{"prompt": 123}', '{"prompt": null}', '{"prompt": ["a"]}']:
        r = subprocess.run(
            [sys.executable, str(here / "classify.py"), "--emit-context"],
            input=payload, env={**os.environ, "AGENTS_TRIAGE_NO_OLLAMA": "1"},
            capture_output=True, text=True, timeout=30,
        )
        assert r.returncode == 0, (payload, r.stderr[-200:])


def test_bad_length_gate_env_never_crashes_hook():
    # codex finding #1: unguarded int() on the env var crashed at import.
    import subprocess
    here = Path(__file__).parent
    r = subprocess.run(
        [sys.executable, str(here / "classify.py"), "commit and push"],
        env={**os.environ, "AGENTS_TRIAGE_LENGTH_GATE": "banana",
             "AGENTS_TRIAGE_NO_OLLAMA": "1"},
        capture_output=True, text=True, timeout=30,
    )
    assert r.returncode == 0, r.stderr[-300:]
    import json
    out = json.loads(r.stdout)
    assert out["tier"] == "simple", out


def test_llm_simple_verdict_vetoed_on_complex_hints():
    # codex finding #3: the LLM must not be able to emit the cheapest tier
    # for a hint-flagged prompt. Monkeypatch the module-level fallback.
    import classify as mod
    orig = mod.ollama_classify
    mod.ollama_classify = lambda *a, **k: {
        "tier": "simple", "agent": "quick-fix", "model": "haiku",
        "confidence": 0.9, "reason": "llm says simple"}
    try:
        p = "research and audit the production deployment pipeline"
        r = classify(p, use_ollama_fallback=True)
        assert r["source"] == "hint-veto", r
        assert r["tier"] == "hard" and r["agent"] == "none", r
        # ...but an LLM "medium" verdict on the same prompt is respected.
        mod.ollama_classify = lambda *a, **k: {
            "tier": "medium", "agent": "research-lite", "model": "sonnet",
            "confidence": 0.8, "reason": "bounded research"}
        r2 = classify(p, use_ollama_fallback=True)
        assert r2["source"] == "ollama" and r2["tier"] == "medium", r2
    finally:
        mod.ollama_classify = orig


def test_setup_prompt_silent_without_llm_is_intended():
    # codex finding #2 flagged this as a regression; it is DELIBERATE:
    # "setup/configure" prompts are routinely complex (mining: 340-turn
    # sessions triaged "simple setup"), so without an LLM to check, the
    # directive stays silent and the main model handles the prompt.
    p = "setup the dev environment"
    r = classify(p, use_ollama_fallback=False)
    assert r["confidence"] < 0.7, r
    assert emit_context(p, use_ollama_fallback=False) == ""


def test_session_context_prompts_stay_silent():
    # live incident 2026-06-12 #2: "summarize what this current suite does"
    # got a dispatch directive; a fresh subagent cannot see the conversation.
    for p in [
        "summarize in plain language what this current suite of skills does",
        "summarize what we built today",
        "tldr of what you changed",
        "research the thing we discussed earlier today",
        # codex round-3: contractions / modifiers / thread phrasing
        "summarize what we've built today",
        "tldr of what you just changed",
        "summarize this thread",
        "summarize our previous conversation",
        "note down what we were discussing",
    ]:
        r = classify(p, use_ollama_fallback=False)
        assert r["source"] == "context-guard", (p, r)
        assert emit_context(p, use_ollama_fallback=False) == "", p
    # ...but context-free summarize still routes cheap:
    r = classify("summarize this paragraph for me", use_ollama_fallback=False)
    assert r["source"] == "regex" and r["model"] == "haiku", r
    # ...and filesystem-state references stay routable — a subagent CAN read
    # the repo (codex round-3 over-match: "this branch" was silencing git):
    r = classify("commit and push this branch", use_ollama_fallback=False)
    assert r["source"] == "regex" and r["agent"] == "quick-fix", r


def test_multi_objective_prompt_never_routes_cheap():
    # PROMPTER field misroute 2026-06-12: 4-objective brief carrying the
    # "research" keyword routed research-lite/0.8 via regex.
    p = ("look through the ~/Documents/screenery-lean project. they should "
         "have a way to edit google sheets somewhere. find a working method "
         "and document it so you always have a way to do it. otherwise, think "
         "and research the most efficient and reliable tool for the job.")
    from classify import _multi_objective
    assert _multi_objective(p), p
    r = classify(p, use_ollama_fallback=False)
    assert r["source"] in ("fail-closed", "context-guard"), r
    assert emit_context(p, use_ollama_fallback=False) == ""
    # single-objective research still routes
    r2 = classify("research the history of the QWERTY layout", use_ollama_fallback=False)
    assert r2["agent"] == "research-lite" and r2["source"] == "regex", r2


def test_multiline_brief_never_routes_cheap():
    # incident #6 (2026-06-12): 758-char 3-workstream brief cheap-routed via
    # \brewrite\b matching the NOUN in "extract.py rewrite". Multi-paragraph
    # structure (>=3 newlines) now flags complex regardless of keywords.
    p = ("you may continue. continue with:\n"
         "Cross-host smoke test — exercise the host wiring.\n"
         "Baseline — measure gains; re-mine after a week.\n"
         "wiki-refresh pass — today churned code paths (extract.py rewrite).")
    assert len(p) < 800
    r = classify(p, use_ollama_fallback=False)
    assert r["source"] in ("fail-closed", "context-guard"), r
    assert emit_context(p, use_ollama_fallback=False) == ""
    # one-line summarize with a single trailing newline still routes
    r2 = classify("summarize this paragraph for me\n", use_ollama_fallback=False)
    assert r2["source"] == "regex" and r2["model"] == "haiku", r2


def test_long_git_prompt_downgraded():
    # replay audit 2026-06-12: multi-clause close-out prompts start with
    # "commit ... and push" but bundle more work; must stay silent.
    p = ("commit everything and push. check there is nothing you left running "
         "(agents in the background or on devices) and if yes - let them finish "
         "if needed and then close.")
    assert len(p) > 120
    assert emit_context(p, use_ollama_fallback=False) == ""
    # short form still routes
    assert "haiku" in emit_context("commit and push", use_ollama_fallback=False)


def test_no_local_models_in_routing_surface():
    # platform-models-only policy: no rule, enum, or LLM verdict may emit a
    # local:* model or the local-ollama agent.
    from classify import RULES, _VALID_AGENTS, _validate_llm_result
    for rule in RULES:
        assert rule[2] != "local-ollama", rule
        assert not rule[3].startswith("local:"), rule
    assert "local-ollama" not in _VALID_AGENTS
    assert _validate_llm_result(
        {"tier": "simple", "agent": "local-ollama", "confidence": 0.9}) is None
    # codex round-3: valid agent + out-of-platform model must be CLAMPED to
    # the tier default, never passed through.
    r = _validate_llm_result({"tier": "simple", "agent": "quick-fix",
                              "model": "local:foo", "confidence": 0.9})
    assert r and r["model"] == "haiku", r
    r = _validate_llm_result({"tier": "medium", "agent": "research-lite",
                              "model": "gpt-4o", "confidence": 0.9})
    assert r and r["model"] == "sonnet", r


def main():
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"pass {fn.__name__}")
    print(f"OK ({len(fns)} tests)")


if __name__ == "__main__":
    main()
