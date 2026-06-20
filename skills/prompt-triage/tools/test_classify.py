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
    _validate_llm_result,
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

# Neutral long fixture for the length-gate test: a single-line factual
# question with NO session-ref phrases, <3 newlines, and <3 imperative
# sentences — so it bypasses the context-guard and brief-gate and falls
# straight onto the >LENGTH_GATE_CHARS path. (The old test reused
# INCIDENT_PROMPT, which contains "we built" and so tripped the EARLIER
# context-guard — the length-gate branch was never exercised, letting a
# mutation that deletes the gate survive.)
NEUTRAL_LONG_PROMPT = ("what is the capital of France " * 60).strip() + "?"


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
    assert r["source"] in ("fail-closed", "context-guard", "brief-gate"), r
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
    # Uses a NEUTRAL fixture (no session-ref phrases, <3 newlines, <3
    # imperatives) so the earlier context-guard / brief-gate cannot shadow the
    # length-gate — the assertion is source=="length-gate" EXACTLY, which a
    # mutation deleting the gate would fail (it would fall through to the regex
    # research-lite route or default, never length-gate).
    assert len(NEUTRAL_LONG_PROMPT) > 1500, len(NEUTRAL_LONG_PROMPT)
    assert NEUTRAL_LONG_PROMPT.count("\n") < 3
    r = classify(NEUTRAL_LONG_PROMPT, use_ollama_fallback=True)
    assert r["source"] == "length-gate", r
    assert r["tier"] == "hard" and r["agent"] == "none", r
    assert emit_context(NEUTRAL_LONG_PROMPT, use_ollama_fallback=True) == ""


def test_env_pin_wins_model_resolution():
    os.environ["AGENTS_TRIAGE_OLLAMA_MODEL"] = "pinned:tag"
    try:
        assert _resolve_ollama_model() == "pinned:tag"
    finally:
        del os.environ["AGENTS_TRIAGE_OLLAMA_MODEL"]


def test_only_oversized_models_resolves_to_none():
    # Major logic fix: the old family-prefix fallback returned ANY same-family
    # installed tag regardless of size, so a machine carrying only qwen3:32b /
    # llama3.1:70b got a 30B+/70B model — violating the docstring contract
    # (never a random model that would blow the timeout AND page ~19GB in).
    # With only oversized variants installed, resolution must return None.
    import json as _json
    import urllib.request as _ur
    import classify as mod

    os.environ.pop("AGENTS_TRIAGE_OLLAMA_MODEL", None)

    class _FakeResp:
        def __init__(self, payload):
            self._p = _json.dumps(payload).encode()

        def read(self):
            return self._p

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    orig = _ur.urlopen
    _ur.urlopen = lambda *a, **k: _FakeResp(
        {"models": [{"name": "qwen3:32b"}, {"name": "llama3.1:70b"}]})
    try:
        assert mod._resolve_ollama_model() is None
        # ...and an exact small-tag hit still resolves (regression guard that
        # the fix didn't break the happy path).
        _ur.urlopen = lambda *a, **k: _FakeResp(
            {"models": [{"name": "qwen3:32b"}, {"name": "qwen3:8b"}]})
        assert mod._resolve_ollama_model() == "qwen3:8b"
    finally:
        _ur.urlopen = orig


def test_research_outranks_summarize_on_mixed_prompts():
    # round-2 codex: summarize rule shadowed research under first-match-wins.
    r = classify("summarize and research the available literature on X", use_ollama_fallback=False)
    assert r["agent"] == "research-lite" and r["tier"] == "medium", r
    # plain summarize routes to glm-executor (2026-06-19 policy override: bounded
    # self-contained content tasks go to GLM-5.2/z.ai; model="haiku" is the
    # coordinator subagent, real work runs on GLM). research still outranks it
    # under first-match-wins (asserted above).
    r2 = classify("summarize this paragraph for me", use_ollama_fallback=False)
    assert r2["agent"] == "glm-executor" and r2["model"] == "haiku" and r2["tier"] == "medium", r2


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
        # "research" in the prompt makes the regex corroborate the LLM verdict
        # (same agent); the verdict passes through at the regex prior's conf.
        assert r2["source"] == "ollama+regex-corroborated" and r2["tier"] == "medium", r2
    finally:
        mod.ollama_classify = orig


def test_llm_medium_haiku_verdict_vetoed_on_complex_hints():
    # Major logic fix: the veto previously fired ONLY when tier=="simple", but
    # _validate_llm_result passes any in-enum model verbatim — so a verdict of
    # tier="medium", model="haiku" on an audit/refactor-hinted prompt slipped
    # through and dispatched audit work to haiku. The veto now also fires when
    # the LLM named the cheapest model (haiku) under complex hints.
    import classify as mod
    orig = mod.ollama_classify
    mod.ollama_classify = lambda *a, **k: {
        "tier": "medium", "agent": "research-lite", "model": "haiku",
        "confidence": 0.8, "reason": "llm says medium but cheap model"}
    try:
        p = "research and audit the production deployment pipeline"
        r = classify(p, use_ollama_fallback=True)
        assert r["source"] == "hint-veto", r
        assert r["tier"] == "hard" and r["agent"] == "none", r
        assert "haiku" not in emit_context(p, use_ollama_fallback=True)
        assert emit_context(p, use_ollama_fallback=True) == ""
        # ...but a medium/SONNET verdict on the same prompt is still respected
        # (only the cheapest model is vetoed, not all of medium).
        mod.ollama_classify = lambda *a, **k: {
            "tier": "medium", "agent": "research-lite", "model": "sonnet",
            "confidence": 0.8, "reason": "bounded research"}
        r2 = classify(p, use_ollama_fallback=True)
        assert r2["source"] == "ollama+regex-corroborated" and r2["model"] == "sonnet", r2
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
    assert r["source"] in ("fail-closed", "context-guard", "brief-gate"), r
    assert emit_context(p, use_ollama_fallback=False) == ""
    # single-objective research still routes
    r2 = classify("research the history of the QWERTY layout", use_ollama_fallback=False)
    assert r2["agent"] == "research-lite" and r2["source"] == "regex", r2


def test_continuation_prompts_stay_silent():
    # incident class #7 (simulated-week sweep 2026-06-12): conversational
    # steering of in-flight work must never be routed.
    for p in [
        "continue. no need to ask me for approval to continue.",
        "continue with round 3. make sure your tests are reliable.",
        "please apply all fixes",
        "let's forget m1 for now, use m2 and kaggle and this device.",
        "do PROMPTER",                      # short, no rule match
        "that's weird because the session was fine yesterday",
        "ok go ahead",
        "retry",
    ]:
        r = classify(p, use_ollama_fallback=False)
        assert r["source"] in ("context-guard", "short-unmatched"), (p, r)
        assert emit_context(p, use_ollama_fallback=False) == "", p
    # self-contained short imperatives still route via their rules:
    assert classify("commit and push", use_ollama_fallback=False)["source"] == "regex"
    assert classify("what is the capital of France?", use_ollama_fallback=False)["source"] == "regex"


def test_llm_cannot_reopen_downgraded_git_route():
    # sweep finding: 170-char multi-clause "commit everything and push.
    # check nothing left running..." was regex-downgraded to 0.6, but the
    # live LLM said simple/quick-fix and the route reopened.
    import classify as mod
    orig = mod.ollama_classify
    mod.ollama_classify = lambda *a, **k: {
        "tier": "simple", "agent": "quick-fix", "model": "haiku",
        "confidence": 0.9, "reason": "llm says simple"}
    try:
        p = ("commit everything and push. check there is nothing you left "
             "running (agents in the background or on devices) and if yes - "
             "let them finish if needed and then close.")
        r = classify(p, use_ollama_fallback=True)
        assert r["source"] == "hint-veto", r
        assert emit_context(p, use_ollama_fallback=True) == ""
    finally:
        mod.ollama_classify = orig


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
    assert r["source"] in ("fail-closed", "context-guard", "brief-gate"), r
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


def test_classify_extract_routes_to_glm_executor():
    # 2026-06-19: bounded structured-output tasks over supplied content go to GLM.
    for p in ("classify these log lines as ERROR/WARN/INFO",
              "extract the email addresses from this file",
              "label each row by category"):
        r = classify(p, use_ollama_fallback=False)
        assert r["agent"] == "glm-executor" and r["model"] == "haiku", (p, r)


def test_glm_executor_never_fires_on_session_context():
    # The context-blind guard runs BEFORE regex, so a summarize/classify verb
    # bound to chat history must NOT reach glm-executor (it can't see history).
    for p in ("summarize what we did this session",
              "classify the decisions we made in this conversation"):
        r = classify(p, use_ollama_fallback=False)
        assert r["agent"] == "none", (p, r)


def test_verbalized_confidence_uncorroborated_is_suppressed():
    # Research 2026-06-19: a local LLM's self-reported confidence is ~random as a
    # routing signal. An LLM verdict with NO regex corroboration must not clear
    # the 0.7 emit gate on its own confidence — it defers to the main model.
    import classify as mod
    orig = mod.ollama_classify
    # High verbalized confidence, but the prompt matches NO regex rule.
    mod.ollama_classify = lambda *a, **k: {
        "tier": "simple", "agent": "general-purpose", "model": "haiku",
        "confidence": 0.95, "reason": "llm feels sure"}
    try:
        # ≥80 chars (clears the short-unmatched gate) and matches NO regex rule
        # and no complex hint, so the Ollama path runs and is the ONLY signal.
        p = ("take a good look at the widget thing and let me know what you "
             "generally make of it whenever you get a free moment")
        r = classify(p, use_ollama_fallback=True)
        assert r["source"] == "ollama-uncorroborated", r
        assert r["confidence"] < 0.7, r          # pushed below emit gate
        assert emit_context(p, use_ollama_fallback=True) == "", r  # no directive
    finally:
        mod.ollama_classify = orig


def test_verbalized_confidence_corroborated_uses_regex_prior():
    # When the regex layer independently agrees, the verdict passes through —
    # but at the deterministic regex prior's confidence, not the verbalized one.
    import classify as mod
    orig = mod.ollama_classify
    mod.ollama_classify = lambda *a, **k: {
        "tier": "medium", "agent": "research-lite", "model": "sonnet",
        "confidence": 0.99, "reason": "llm very sure"}
    try:
        # "investigate" matches the research rule (sonnet/0.8) → corroborated.
        r = classify("investigate the options here", use_ollama_fallback=True)
        assert r["source"] == "ollama+regex-corroborated", r
        assert r["confidence"] <= 0.8, r  # clamped to regex prior, not 0.99
    finally:
        mod.ollama_classify = orig


def test_glm_executor_in_valid_agents():
    # LLM-fallback verdicts naming glm-executor must validate, not be dropped.
    r = _validate_llm_result({"tier": "medium", "agent": "glm-executor",
                              "model": "haiku", "confidence": 0.8})
    assert r and r["agent"] == "glm-executor" and r["model"] == "haiku", r


def test_router_eval_gate_no_misroute_down():
    # The cost-quality harness (router_eval.py) is the verifier SEPARATE from the
    # router. Asymmetric gate: never route a needs_frontier prompt to a cheap
    # worker. This locks the gate into CI so a future rule change can't regress
    # it silently (research 2026-06-19; see wiki/projects/delegate-router.md).
    import os
    from router_eval import evaluate, load_corpus
    corpus = load_corpus(os.path.join(os.path.dirname(__file__), "router_eval_corpus.jsonl"))
    report = evaluate(corpus)
    assert report["misroute_down"]["count"] == 0, report["misroute_down"]["cases"]
    # Sanity: the router must also beat the always-opus baseline on cost.
    assert report["cost_proxy"]["vs_opus_pct"] < 100, report["cost_proxy"]


def main():
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"pass {fn.__name__}")
    print(f"OK ({len(fns)} tests)")


if __name__ == "__main__":
    main()
