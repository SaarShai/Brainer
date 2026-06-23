#!/usr/bin/env python3
"""Tests for model_roster.py — plain-python (no pytest dep), runnable standalone.

Shape mirrors skills/loop-engineering/tools/test_loop_lint.py: a list of test_*
functions, a main() that runs them and returns the failure count (exit 0 == all
pass), registered in scripts/run_all_tests.sh.

Pure-logic only: panel selection, lane diversity, exclude-self, and the two role
scaffolds. Detection (which/env/ollama) is host-dependent and intentionally NOT
asserted here — we build Backend lists directly so the tests are deterministic
on any machine, CLIs installed or not.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import model_roster as mr  # noqa: E402


def _b(lane, available=True, kind="cli", invocation="tool exec", models=None):
    return mr.Backend(vendor=f"{lane}-vendor", lane=lane, kind=kind,
                      invocation=invocation, available=available,
                      probe="test", models=models or [])


FULL = [
    _b(mr.LANE_GPT),
    _b(mr.LANE_GEMINI),
    _b(mr.LANE_CLAUDE),
    _b(mr.LANE_GLM, kind="api", invocation="dispatch via glm-executor"),
    _b(mr.LANE_LOCAL, kind="local", invocation="ollama run {model}", models=["llama3.2"]),
]


def test_panel_respects_n():
    panel = mr.pick_panel(FULL, 2)
    return len(panel) == 2


def test_panel_is_lane_diverse():
    panel = mr.pick_panel(FULL, 5)
    lanes = [b.lane for b in panel]
    return len(lanes) == len(set(lanes))            # no lane repeats


def test_panel_excludes_self_lane():
    # Claude orchestrator must not get a Claude verifier in its cross-vendor panel.
    panel = mr.pick_panel(FULL, 5, exclude_lane=mr.LANE_CLAUDE)
    return all(b.lane != mr.LANE_CLAUDE for b in panel)


def test_panel_skips_unavailable():
    roster = [_b(mr.LANE_GPT, available=False), _b(mr.LANE_GEMINI, available=True)]
    panel = mr.pick_panel(roster, 3)
    return [b.lane for b in panel] == [mr.LANE_GEMINI]


def test_panel_empty_when_nothing_reachable():
    roster = [_b(mr.LANE_GPT, available=False), _b(mr.LANE_CLAUDE, available=False)]
    return mr.pick_panel(roster, 3) == []


def test_panel_prefers_strong_external_first():
    # Order preference puts gpt/gemini ahead of local when N forces a choice.
    panel = mr.pick_panel(FULL, 1)
    return panel and panel[0].lane == mr.LANE_GPT


def test_advisor_scaffold_is_divergent_not_a_verdict():
    p = mr.render_prompt("advisor", task="fix the parser", brief="tried regex, failed")
    low = p.lower()
    # must forbid a verdict and demand fresh approaches
    return ("not a judge" in low and "pass/fail" in low
            and "structurally different" in low and "read-only" in low)


def test_verifier_scaffold_is_convergent_refutation():
    p = mr.render_prompt("verifier", task="the fix works", brief="exit 0 on pytest")
    low = p.lower()
    return ("refute" in low and "holds:" in low and "read-only" in low)


def test_advisor_and_verifier_scaffolds_differ():
    a = mr.render_prompt("advisor", "t", "b")
    v = mr.render_prompt("verifier", "t", "b")
    return a != v


def test_render_dispatch_cli_uses_heredoc():
    d = mr.render_dispatch(_b(mr.LANE_GPT, invocation="codex exec"),
                           "advisor", "task", "brief")
    return "codex exec <<'LOOP_ADVISOR_EOF'" in d and d.rstrip().endswith("LOOP_ADVISOR_EOF")


def test_render_dispatch_fills_local_model():
    b = _b(mr.LANE_LOCAL, kind="local", invocation="ollama run {model}", models=["qwen2.5"])
    d = mr.render_dispatch(b, "verifier", "task", "brief")
    return "ollama run qwen2.5 <<'LOOP_VERIFIER_EOF'" in d


def test_render_dispatch_api_is_not_a_heredoc():
    b = _b(mr.LANE_GLM, kind="api", invocation="dispatch via the glm-executor subagent")
    d = mr.render_dispatch(b, "advisor", "task", "brief")
    return "glm-executor" in d and "<<'" not in d


def test_detect_roster_returns_all_known_lanes():
    # Detection result is host-dependent, but the SHAPE is fixed: one Backend per
    # known lane, each with a probe string explaining the verdict.
    roster = mr.detect_roster()
    lanes = {b.lane for b in roster}
    expected = {mr.LANE_GPT, mr.LANE_GEMINI, mr.LANE_CLAUDE, mr.LANE_GLM, mr.LANE_LOCAL}
    return lanes == expected and all(b.probe for b in roster)


# --- executor (--run) -----------------------------------------------------
# Deterministic on any host: drive run_dispatch with stock POSIX commands
# (`cat`, `false`) instead of a real model, so stdin-plumbing, capture, FINDINGS
# extraction, and the failure/survivor split are tested without network or a CLI.

def test_strip_ansi_removes_spinner_noise():
    noisy = "\x1b[?25l\x1b[1GUse a stream\x1b[K\x1b[?25h\nFINDINGS: ok"
    clean = mr._strip_ansi(noisy)
    return "\x1b" not in clean and "FINDINGS: ok" in clean


def test_extract_findings_prefers_findings_line():
    return mr._extract_findings("blah\nFINDINGS: the answer\ntrailing") == "the answer"


def test_extract_findings_falls_back_to_last_line():
    return mr._extract_findings("only line here") == "only line here"


def test_run_dispatch_cat_roundtrips_stdin():
    # `cat` echoes the prompt back → ok, and the scaffold's own FINDINGS: line is captured.
    b = _b(mr.LANE_GPT, invocation="cat")
    r = mr.run_dispatch(b, "advisor", task="unstick me", brief="tried X", timeout=10)
    return r["ok"] and "unstick me" in r["raw"] and r["findings"] != ""


def test_run_dispatch_nonzero_exit_is_dropped():
    r = mr.run_dispatch(_b(mr.LANE_GPT, invocation="false"), "verifier", "claim", "ev", timeout=10)
    return (not r["ok"]) and r["error"].startswith("exit 1")


def test_run_dispatch_missing_binary_is_dropped_not_raised():
    r = mr.run_dispatch(_b(mr.LANE_GPT, invocation="definitely_not_a_real_binary_xyz"),
                        "advisor", "t", "b", timeout=10)
    return (not r["ok"]) and "dispatch failed" in r["error"]


def test_run_dispatch_api_lane_not_auto_runnable():
    b = _b(mr.LANE_GLM, kind="api", invocation="dispatch via the glm-executor subagent")
    r = mr.run_dispatch(b, "advisor", "t", "b")
    return (not r["ok"]) and "glm-executor" in r["error"]


def test_run_panel_splits_survivors_and_failures():
    # one good (`cat`), one bad (`false`): panel proceeds with the survivor.
    roster = [_b(mr.LANE_GPT, invocation="cat"), _b(mr.LANE_GEMINI, invocation="false")]
    res = mr.run_panel(roster, 2, "verifier", "claim", "ev", timeout=10)
    return (len(res["survivors"]) == 1 and len(res["failures"]) == 1
            and res["survivors"][0]["lane"] == mr.LANE_GPT)


# --- detection helpers ----------------------------------------------------

def test_codex_glm_config_detects_zai_provider():
    import tempfile, os as _os
    fd, path = tempfile.mkstemp(suffix=".toml")
    try:
        with _os.fdopen(fd, "w") as fh:
            fh.write('model = "gpt-5.5"\n[model_providers.zai]\nbase_url = "https://api.z.ai"\n')
        return mr._codex_glm_config(path) == path
    finally:
        _os.unlink(path)


def test_codex_glm_config_detects_profile_or_model():
    import tempfile, os as _os
    fd, path = tempfile.mkstemp(suffix=".toml")
    try:
        with _os.fdopen(fd, "w") as fh:
            fh.write('[profiles.glm]\nmodel = "glm-5.2"\n')
        return mr._codex_glm_config(path) == path
    finally:
        _os.unlink(path)


def test_codex_glm_config_absent_when_no_zai():
    import tempfile, os as _os
    fd, path = tempfile.mkstemp(suffix=".toml")
    try:
        with _os.fdopen(fd, "w") as fh:
            fh.write('model = "gpt-5.5"\nmodel_reasoning_effort = "high"\n')
        return mr._codex_glm_config(path) == ""
    finally:
        _os.unlink(path)


def test_codex_glm_config_missing_file_is_empty():
    return mr._codex_glm_config("/no/such/codex/config.toml") == ""


def test_run_dispatch_routes_glm_http_to_run_glm():
    # http+glm must call _run_glm (not the CLI argv path); deterministic via a stub.
    orig = mr._run_glm
    mr._run_glm = lambda prompt, **kw: (True, "a different approach\nFINDINGS: try mmap windowing", "")
    try:
        b = _b(mr.LANE_GLM, kind="http", invocation="z.ai chat/completions (glm-5.2)")
        r = mr.run_dispatch(b, "advisor", "t", "b", timeout=5)
        return r["ok"] and r["findings"] == "try mmap windowing"
    finally:
        mr._run_glm = orig


def test_run_dispatch_glm_http_failure_is_dropped():
    orig = mr._run_glm
    mr._run_glm = lambda prompt, **kw: (False, "", "z.ai dispatch failed: timeout")
    try:
        b = _b(mr.LANE_GLM, kind="http", invocation="z.ai chat/completions (glm-5.2)")
        r = mr.run_dispatch(b, "verifier", "t", "b", timeout=5)
        return (not r["ok"]) and "timeout" in r["error"]
    finally:
        mr._run_glm = orig


# --- OpenRouter transport + Fusion advisor --------------------------------

def _orb(lane, slug="x/y"):
    return mr.Backend(vendor=f"{lane} via OpenRouter", lane=lane, kind="http",
                      invocation=f"OpenRouter ({slug})", available=True, probe="key",
                      transport="openrouter", slug=slug)


def test_openrouter_slug_env_override():
    import os as _os
    key = "OPENROUTER_MODEL_GPT"
    prev = _os.environ.get(key)
    _os.environ[key] = "vendor/custom-model"
    try:
        return mr._openrouter_slug(mr.LANE_GPT) == "vendor/custom-model"
    finally:
        if prev is None:
            _os.environ.pop(key, None)
        else:
            _os.environ[key] = prev


def test_openrouter_default_slug_per_lane():
    # every eligible lane has a real default slug; local is NOT eligible.
    return (all(mr._openrouter_slug(l) for l in mr._OPENROUTER_LANES)
            and mr.LANE_LOCAL not in mr._OPENROUTER_LANES)


def test_openrouter_lanes_exclude_local_survivor():
    # the on-box survivor backstop must never be routed THROUGH the proxy.
    return mr.LANE_LOCAL not in mr._OPENROUTER_LANES


def test_run_dispatch_routes_openrouter_http_to_run_openrouter():
    orig = mr._run_openrouter
    mr._run_openrouter = lambda prompt, **kw: (True, "idea\nFINDINGS: try a streaming parser", "")
    try:
        r = mr.run_dispatch(_orb(mr.LANE_GPT, "openai/gpt-5-mini"), "advisor", "t", "b", timeout=5)
        return r["ok"] and r["findings"] == "try a streaming parser"
    finally:
        mr._run_openrouter = orig


def test_run_dispatch_openrouter_passes_slug_as_model():
    seen = {}
    orig = mr._run_openrouter

    def _stub(prompt, **kw):
        seen["model"] = kw.get("model")
        return (True, "FINDINGS: ok", "")
    mr._run_openrouter = _stub
    try:
        mr.run_dispatch(_orb(mr.LANE_GEMINI, "google/gemini-3-flash-preview"), "advisor", "t", "b", timeout=5)
        return seen["model"] == "google/gemini-3-flash-preview"
    finally:
        mr._run_openrouter = orig


def test_run_dispatch_openrouter_failure_is_dropped():
    orig = mr._run_openrouter
    mr._run_openrouter = lambda prompt, **kw: (False, "", "OpenRouter: Insufficient credits")
    try:
        r = mr.run_dispatch(_orb(mr.LANE_GPT), "verifier", "t", "b", timeout=5)
        return (not r["ok"]) and "credits" in r["error"]
    finally:
        mr._run_openrouter = orig


def test_run_openrouter_no_key_errors():
    orig = mr._openrouter_key
    mr._openrouter_key = lambda: ""
    try:
        ok, _text, err = mr._run_openrouter("p", timeout=5, model="x/y")
        return (not ok) and "no OpenRouter key" in err
    finally:
        mr._openrouter_key = orig


def test_run_openrouter_no_slug_errors():
    orig = mr._openrouter_key
    mr._openrouter_key = lambda: "sk-test"
    try:
        ok, _text, err = mr._run_openrouter("p", timeout=5, model="")
        return (not ok) and "slug" in err
    finally:
        mr._openrouter_key = orig


def test_detect_roster_no_openrouter_without_key():
    orig = mr._openrouter_key
    mr._openrouter_key = lambda: ""
    try:
        roster = mr.detect_roster()
        return not any(b.transport == "openrouter" for b in roster)
    finally:
        mr._openrouter_key = orig


def test_detect_roster_prefer_replaces_eligible_lanes():
    # with a key and prefer_transport, every eligible lane resolves to exactly one
    # OpenRouter-backed backend (native replaced); local stays native.
    orig = mr._openrouter_key
    mr._openrouter_key = lambda: "sk-test"
    try:
        roster = mr.detect_roster(prefer_transport="openrouter")
        for lane in mr._OPENROUTER_LANES:
            same = [b for b in roster if b.lane == lane]
            if not (len(same) == 1 and same[0].transport == "openrouter"):
                return False
        locals_ = [b for b in roster if b.lane == mr.LANE_LOCAL]
        return all(b.transport == "" for b in locals_)
    finally:
        mr._openrouter_key = orig


def test_detect_roster_backfill_never_doubles_a_lane():
    # backfill (no prefer): an OpenRouter backend exists for a lane ONLY when no
    # native backend in that lane is available — never both.
    orig = mr._openrouter_key
    mr._openrouter_key = lambda: "sk-test"
    try:
        roster = mr.detect_roster()
        for b in roster:
            if b.transport == "openrouter":
                clash = [o for o in roster if o.lane == b.lane and o is not b and o.available]
                if clash:
                    return False
        return True
    finally:
        mr._openrouter_key = orig


def test_fusion_request_body_shape():
    body = mr.fusion_request_body("the task", "the brief",
                                  analysis_models=["a/1", "b/2"], judge_model="j/3",
                                  preset="general-high")
    if body["model"] != "openrouter/fusion":
        return False
    plugin = body["plugins"][0]
    return (plugin["id"] == "fusion" and plugin["preset"] == "general-high"
            and plugin["analysis_models"] == ["a/1", "b/2"] and plugin["model"] == "j/3"
            and "the task" in body["messages"][0]["content"])


def test_fusion_request_body_minimal_omits_optionals():
    body = mr.fusion_request_body("t", "b")
    plugin = body["plugins"][0]
    return (plugin == {"id": "fusion"} and body["model"] == "openrouter/fusion")


def test_fusion_uses_advisor_scaffold_not_verifier():
    # Fusion is advisor-only; its prompt must carry the advisor framing, never the
    # verifier's pass/fail framing (keeping the gate ours).
    body = mr.fusion_request_body("t", "b")
    content = body["messages"][0]["content"]
    return ("ADVISOR" in content) and ("holds:" not in content)


def test_run_fusion_no_key_errors():
    orig = mr._openrouter_key
    mr._openrouter_key = lambda: ""
    try:
        r = mr.run_fusion("t", "b")
        return (not r["ok"]) and "no OpenRouter key" in r["error"]
    finally:
        mr._openrouter_key = orig


TESTS = [v for k, v in sorted(globals().items()) if k.startswith("test_")]


def main() -> int:
    failures = 0
    for t in TESTS:
        try:
            ok = t()
        except Exception as e:  # noqa: BLE001
            ok = False
            print(f"ERROR {t.__name__}: {e}")
        if ok:
            print(f"PASS {t.__name__}")
        else:
            failures += 1
            print(f"FAIL {t.__name__}")
    total = len(TESTS)
    print(f"\n{total - failures}/{total} passed")
    return failures


if __name__ == "__main__":
    sys.exit(main())
