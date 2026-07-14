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

import json
import os
import subprocess
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


def test_render_prompt_redacts_secrets_before_egress():
    # a leaked key/.env/Authorization header in task/brief must be scrubbed before
    # the prompt crosses a vendor boundary (R12a, enforced at render).
    p = mr.render_prompt("advisor", task="key=sk-proj-abcdef0123456789abcdef",
                         brief="Authorization: Bearer ghp_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa")
    return ("sk-proj-abcdef" not in p and "ghp_aaaa" not in p and "[REDACTED]" in p)


def test_render_prompt_redacts_gitlab_and_slack():
    # standalone GitLab/Slack token shapes (not env-assignments) must scrub too
    # (2026-07-05 review found these uncovered).
    # The GitLab literal is assembled from two pieces so no contiguous
    # `glpat-<20 chars>` string exists in this source file — otherwise GitHub
    # secret-scanning push-protection flags this dummy fixture and blocks the
    # push (2026-07-07: it did exactly that on screenery-lean). The runtime
    # value is identical, so the scrub coverage is unchanged.
    gitlab_shape = "glpat-" + "abcdef0123456789ABCD"
    p = mr.render_prompt("advisor", task=gitlab_shape,
                         brief="slack xoxb-1234567890-abcdefghij")
    return ("glpat-abcdef" not in p and "xoxb-1234567890" not in p)


def test_run_dispatch_fails_closed_not_crashes_when_redactor_raises(monkeypatch=None):
    # egress redaction fails CLOSED (render_prompt raises), but run_dispatch must
    # catch it and return ok=False so the panel drops the member, never crashes.
    orig = mr.render_prompt
    mr.render_prompt = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("redactor missing"))
    try:
        b = mr.Backend(vendor="glm", lane=mr.LANE_GLM, kind="http",
                       invocation="", available=True, probe="test", models=["glm-5.2"])
        res = mr.run_dispatch(b, "verifier", task="t", brief="b")
        return res["ok"] is False and "redactor missing" in res["error"]
    finally:
        mr.render_prompt = orig


def test_verifier_quorum_requires_odd_ge3():
    return (mr.verifier_quorum(3)["ok"] is True
            and mr.verifier_quorum(1)["ok"] is False        # too few
            and mr.verifier_quorum(2)["ok"] is False        # even
            and mr.verifier_quorum(5)["ok"] is True)


def test_run_panel_attaches_quorum_for_verifier_only():
    # no network: an empty roster yields 0 survivors; verifier gets a quorum verdict,
    # advisor does not (advisors don't gate, so quorum is meaningless for them).
    v = mr.run_panel([], 3, "verifier", "t", "b")
    a = mr.run_panel([], 3, "advisor", "t", "b")
    return ("quorum" in v and v["quorum"]["ok"] is False and "quorum" not in a)


def test_run_refuses_egress_without_consent():
    import io
    from contextlib import redirect_stderr
    buf = io.StringIO()
    with redirect_stderr(buf):
        rc = mr.main(["--panel", "2", "--role", "verifier", "--run", "--task", "t", "--brief", "b"])
    return rc == 2 and "consent" in buf.getvalue().lower()


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


# --- per-lane telemetry (usage/latency/served_model) ----------------------
# Mocks urllib.request.urlopen (not _run_glm/_run_openrouter themselves) so the
# actual usage/served_model extraction code in those functions is exercised,
# not bypassed.

class _FakeHTTPResponse:
    def __init__(self, body: bytes):
        self._body = body

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def test_run_glm_captures_usage_and_served_model_via_meta():
    import urllib.request
    orig_urlopen = urllib.request.urlopen
    orig_key = mr._zai_key
    mr._zai_key = lambda: "test-key"
    body = json.dumps({
        "model": "glm-5.2-air", "choices": [{"message": {"content": "FINDINGS: ok"}}],
        "usage": {"prompt_tokens": 11, "completion_tokens": 22},
    }).encode()
    urllib.request.urlopen = lambda req, timeout=0: _FakeHTTPResponse(body)
    try:
        meta: dict = {}
        ok, text, err = mr._run_glm("p", timeout=5, model="glm-5.2", meta=meta)
        return (ok and meta.get("usage") == {"prompt_tokens": 11, "completion_tokens": 22}
                and meta.get("served_model") == "glm-5.2-air")
    finally:
        urllib.request.urlopen = orig_urlopen
        mr._zai_key = orig_key


def test_run_glm_meta_defaults_none_when_absent_from_response():
    import urllib.request
    orig_urlopen = urllib.request.urlopen
    orig_key = mr._zai_key
    mr._zai_key = lambda: "test-key"
    body = json.dumps({"choices": [{"message": {"content": "FINDINGS: ok"}}]}).encode()
    urllib.request.urlopen = lambda req, timeout=0: _FakeHTTPResponse(body)
    try:
        meta: dict = {}
        mr._run_glm("p", timeout=5, meta=meta)
        return meta.get("usage") is None and meta.get("served_model") is None
    finally:
        urllib.request.urlopen = orig_urlopen
        mr._zai_key = orig_key


def test_run_glm_meta_is_untouched_when_not_passed():
    # meta=None (the default) must not raise — existing 3-tuple callers are
    # unaffected by the telemetry addition.
    import urllib.request
    orig_urlopen = urllib.request.urlopen
    orig_key = mr._zai_key
    mr._zai_key = lambda: "test-key"
    body = json.dumps({"model": "glm-5.2", "choices": [{"message": {"content": "FINDINGS: ok"}}]}).encode()
    urllib.request.urlopen = lambda req, timeout=0: _FakeHTTPResponse(body)
    try:
        ok, text, err = mr._run_glm("p", timeout=5)
        return ok and "FINDINGS: ok" in text
    finally:
        urllib.request.urlopen = orig_urlopen
        mr._zai_key = orig_key


def test_run_openrouter_captures_usage_and_served_model_via_meta():
    import urllib.request
    orig_urlopen = urllib.request.urlopen
    orig_key = mr._openrouter_key
    mr._openrouter_key = lambda: "test-key"
    body = json.dumps({
        "model": "openai/gpt-5.4-mini", "choices": [{"message": {"content": "FINDINGS: ok"}}],
        "usage": {"prompt_tokens": 5, "completion_tokens": 9},
    }).encode()
    urllib.request.urlopen = lambda req, timeout=0: _FakeHTTPResponse(body)
    try:
        meta: dict = {}
        ok, text, err = mr._run_openrouter("p", timeout=5, model="openai/gpt-5.4-mini", meta=meta)
        return (ok and meta.get("usage") == {"prompt_tokens": 5, "completion_tokens": 9}
                and meta.get("served_model") == "openai/gpt-5.4-mini")
    finally:
        urllib.request.urlopen = orig_urlopen
        mr._openrouter_key = orig_key


def test_run_dispatch_glm_populates_usage_latency_served_model():
    orig = mr._run_glm

    def _stub(prompt, *, timeout, model="glm-5.2", meta=None, **kw):
        if meta is not None:
            meta["usage"] = {"prompt_tokens": 3, "completion_tokens": 4}
            meta["served_model"] = "glm-5.2"
        return True, "FINDINGS: ok", ""
    mr._run_glm = _stub
    try:
        b = _b(mr.LANE_GLM, kind="http", invocation="z.ai chat/completions (glm-5.2)")
        r = mr.run_dispatch(b, "advisor", "t", "b", timeout=5)
        return (r["usage"] == {"prompt_tokens": 3, "completion_tokens": 4}
                and r["served_model"] == "glm-5.2"
                and isinstance(r["latency_ms"], float) and r["latency_ms"] >= 0)
    finally:
        mr._run_glm = orig


def test_run_dispatch_openrouter_populates_usage_latency_served_model():
    orig = mr._run_openrouter

    def _stub(prompt, *, timeout, model, meta=None, **kw):
        if meta is not None:
            meta["usage"] = {"prompt_tokens": 7, "completion_tokens": 8}
            meta["served_model"] = model
        return True, "FINDINGS: ok", ""
    mr._run_openrouter = _stub
    try:
        r = mr.run_dispatch(_orb(mr.LANE_GPT, "openai/gpt-5-mini"), "advisor", "t", "b", timeout=5)
        return (r["usage"] == {"prompt_tokens": 7, "completion_tokens": 8}
                and r["served_model"] == "openai/gpt-5-mini"
                and isinstance(r["latency_ms"], float))
    finally:
        mr._run_openrouter = orig


def test_run_dispatch_cli_lane_leaves_usage_none_but_sets_served_model():
    # CLI transports never report token usage; served_model is set only when
    # trivially known from the resolved {model} substitution (ollama here).
    b = _b(mr.LANE_LOCAL, kind="local", invocation="cat", models=["qwen2.5"])
    r = mr.run_dispatch(b, "advisor", "t", "b", timeout=5)
    return r["usage"] is None and r["latency_ms"] is not None


def test_run_dispatch_never_raises_when_trace_writer_missing():
    # Simulate an import failure of orchestration_trace (defensive fallback);
    # run_dispatch must still work and telemetry keys must still be present.
    orig = mr._record_lane_event
    mr._record_lane_event = None
    try:
        r = mr.run_dispatch(_b(mr.LANE_GPT, invocation="cat"), "advisor", "t", "b", timeout=5)
        return r["ok"] and "usage" in r and "latency_ms" in r and "served_model" in r
    finally:
        mr._record_lane_event = orig


def test_run_dispatch_trace_disabled_by_env():
    calls = []
    orig = mr._record_lane_event
    mr._record_lane_event = lambda path, event: calls.append(event) or True
    prev = os.environ.get("BRAINER_TRACE")
    os.environ["BRAINER_TRACE"] = "0"
    try:
        mr.run_dispatch(_b(mr.LANE_GPT, invocation="cat"), "advisor", "t", "b", timeout=5)
        return calls == []
    finally:
        mr._record_lane_event = orig
        if prev is None:
            os.environ.pop("BRAINER_TRACE", None)
        else:
            os.environ["BRAINER_TRACE"] = prev


def test_run_dispatch_trace_enabled_by_default():
    calls = []
    orig = mr._record_lane_event
    mr._record_lane_event = lambda path, event: calls.append(event) or True
    prev = os.environ.pop("BRAINER_TRACE", None)
    try:
        mr.run_dispatch(_b(mr.LANE_GPT, invocation="cat"), "advisor", "unstick me", "b", timeout=5)
        correlation_id = calls[0]["correlation_id"] if calls else ""
        return (len(calls) == 1 and calls[0]["lane"] == mr.LANE_GPT
                and correlation_id.startswith("run:") and len(correlation_id) == 36
                and "unstick me" not in correlation_id)
    finally:
        mr._record_lane_event = orig
        if prev is not None:
            os.environ["BRAINER_TRACE"] = prev


def test_run_dispatch_correlation_id_is_unique_by_default_and_caller_stable():
    calls = []
    orig = mr._record_lane_event
    mr._record_lane_event = lambda path, event: calls.append(event) or True
    prev = os.environ.pop("BRAINER_TRACE", None)
    try:
        backend = _b(mr.LANE_GPT, invocation="cat")
        mr.run_dispatch(backend, "advisor", "same task", "b", timeout=5)
        mr.run_dispatch(backend, "verifier", "same task", "b", timeout=5)
        mr.run_dispatch(backend, "advisor", "different task", "b", timeout=5,
                        correlation_id="run:caller-stable")
        mr.run_dispatch(backend, "verifier", "different task", "b", timeout=5,
                        correlation_id="run:caller-stable")
        ids = [call["correlation_id"] for call in calls]
        return (ids[0] != ids[1] and ids[2:] == ["run:caller-stable"] * 2
                and all(1 <= len(value) <= 128 for value in ids))
    finally:
        mr._record_lane_event = orig
        if prev is not None:
            os.environ["BRAINER_TRACE"] = prev


def test_run_dispatch_correlation_id_rejects_unbounded_or_illegal_values():
    calls = []
    orig = mr._record_lane_event
    mr._record_lane_event = lambda path, event: calls.append(event) or True
    prev = os.environ.pop("BRAINER_TRACE", None)
    try:
        backend = _b(mr.LANE_GPT, invocation="cat")
        valid = "x" * 128
        oversized = "y" * 129
        illegal = "raw task text with spaces"
        mr.run_dispatch(backend, "advisor", "t", "b", timeout=5,
                        correlation_id=valid)
        mr.run_dispatch(backend, "advisor", "t", "b", timeout=5,
                        correlation_id=oversized)
        mr.run_dispatch(backend, "advisor", "t", "b", timeout=5,
                        correlation_id=illegal)
        ids = [call["correlation_id"] for call in calls]
        return (ids[0] == valid
                and all(value.startswith("run:") and len(value) == 36
                        for value in ids[1:])
                and ids[1] != ids[2]
                and oversized not in ids and illegal not in ids)
    finally:
        mr._record_lane_event = orig
        if prev is not None:
            os.environ["BRAINER_TRACE"] = prev


def test_run_panel_shares_one_correlation_id_across_lanes():
    calls = []
    orig = mr._record_lane_event
    mr._record_lane_event = lambda path, event: calls.append(event) or True
    prev = os.environ.pop("BRAINER_TRACE", None)
    try:
        roster = [_b(mr.LANE_GPT, invocation="cat"),
                  _b(mr.LANE_GEMINI, invocation="cat")]
        mr.run_panel(roster, 2, "advisor", "same panel task", "b", timeout=5)
        ids = [call["correlation_id"] for call in calls]
        return len(ids) == 2 and ids[0] == ids[1] and ids[0].startswith("run:")
    finally:
        mr._record_lane_event = orig
        if prev is not None:
            os.environ["BRAINER_TRACE"] = prev


def test_trace_dispatch_never_raises_when_writer_throws():
    orig = mr._record_lane_event
    mr._record_lane_event = lambda path, event: (_ for _ in ()).throw(RuntimeError("disk full"))
    try:
        r = mr.run_dispatch(_b(mr.LANE_GPT, invocation="cat"), "advisor", "t", "b", timeout=5)
        return r["ok"] is True   # dispatch result unaffected by a broken trace writer
    finally:
        mr._record_lane_event = orig


# --- effort tiers -----------------------------------------------------------

def test_effort_tiers_include_gpt_style_granularity():
    return set(mr.EFFORT_TIERS) == {"instant", "light", "standard", "high", "xhigh"}


def test_openrouter_slug_for_effort_env_override():
    key = "OPENROUTER_MODEL_GPT_HIGH"
    prev = os.environ.get(key)
    os.environ[key] = "openai/gpt-5.4-high-tier"
    try:
        return mr._openrouter_slug_for_effort(mr.LANE_GPT, "high") == "openai/gpt-5.4-high-tier"
    finally:
        if prev is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = prev


def test_openrouter_slug_for_effort_falls_back_to_default_slug():
    key = "OPENROUTER_MODEL_GPT_XHIGH"
    os.environ.pop(key, None)
    # no override set for xhigh -> falls back to the plain per-lane default/env slug
    return mr._openrouter_slug_for_effort(mr.LANE_GPT, "xhigh") == mr._openrouter_slug(mr.LANE_GPT)


def test_openrouter_slug_for_effort_standard_matches_plain_slug():
    return mr._openrouter_slug_for_effort(mr.LANE_GPT, "standard") == mr._openrouter_slug(mr.LANE_GPT)


def test_run_dispatch_all_openrouter_lanes_honor_effort_override():
    # 2026-07-05 review (T2): the effort-scoped env override
    # (OPENROUTER_MODEL_<LANE>_<EFFORT>) used to be applied ONLY on the GPT
    # lane inside run_dispatch, even though _openrouter_effort_override is
    # lane-generic and the env var is named per-lane. Every OpenRouter-routed
    # lane with an override set for the requested tier must honor it.
    env_keys = {
        mr.LANE_GPT: "OPENROUTER_MODEL_GPT_HIGH",
        mr.LANE_GEMINI: "OPENROUTER_MODEL_GEMINI_HIGH",
        mr.LANE_CLAUDE: "OPENROUTER_MODEL_CLAUDE_HIGH",
        mr.LANE_GLM: "OPENROUTER_MODEL_GLM_HIGH",
    }
    prev = {k: os.environ.get(k) for k in env_keys.values()}
    for lane, key in env_keys.items():
        os.environ[key] = f"override/{lane}-high"
    seen = {}
    orig = mr._run_openrouter

    def _stub(prompt, **kw):
        return (True, "FINDINGS: ok", "")
    mr._run_openrouter = _stub
    try:
        for lane in (mr.LANE_GPT, mr.LANE_GEMINI, mr.LANE_CLAUDE, mr.LANE_GLM):
            def _capture(prompt, **kw):
                seen[lane] = kw.get("model")
                return (True, "FINDINGS: ok", "")
            mr._run_openrouter = _capture
            mr.run_dispatch(_orb(lane, f"base/{lane}"), "advisor", "t", "b", effort="high", timeout=5)
        expected = {lane: f"override/{lane}-high" for lane in env_keys}
        return seen == expected
    finally:
        mr._run_openrouter = orig
        for k, v in prev.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


def test_run_dispatch_openrouter_lane_without_override_falls_back_to_slug():
    # A lane with NO effort-scoped override set for the requested tier still
    # falls back to its own already-detected slug (never another lane's, and
    # never the bare per-lane default over an explicitly-detected slug).
    key = "OPENROUTER_MODEL_GEMINI_HIGH"
    os.environ.pop(key, None)
    seen = {}
    orig = mr._run_openrouter

    def _stub(prompt, **kw):
        seen["model"] = kw.get("model")
        return (True, "FINDINGS: ok", "")
    mr._run_openrouter = _stub
    try:
        mr.run_dispatch(_orb(mr.LANE_GEMINI, "detected/gemini-slug"), "advisor", "t", "b",
                        effort="high", timeout=5)
        return seen["model"] == "detected/gemini-slug"
    finally:
        mr._run_openrouter = orig


def test_render_dispatch_codex_effort_adds_reasoning_flag():
    b = _b(mr.LANE_GPT, invocation="codex exec")
    d = mr.render_dispatch(b, "advisor", "task", "brief", effort="high")
    return "codex exec -c model_reasoning_effort=high <<'LOOP_ADVISOR_EOF'" in d


def test_render_dispatch_codex_effort_only_applies_to_gpt_lane():
    # a non-GPT lane's invocation is untouched even if effort is passed.
    b = _b(mr.LANE_GEMINI, invocation="gemini --approval-mode plan -p ''")
    d = mr.render_dispatch(b, "advisor", "task", "brief", effort="high")
    return "model_reasoning_effort" not in d


def test_render_dispatch_no_effort_flag_is_byte_identical_to_before():
    # DONE MEANS (5): no --effort flag given -> rendered command matches the
    # pre-feature baseline exactly for both the default-effort Backend and an
    # explicit empty-string effort call.
    b = _b(mr.LANE_GPT, invocation="codex exec")
    baseline = "codex exec <<'LOOP_ADVISOR_EOF'\n" + mr.render_prompt("advisor", "task", "brief") + "\nLOOP_ADVISOR_EOF"
    no_effort_kwarg = mr.render_dispatch(b, "advisor", "task", "brief")
    explicit_empty = mr.render_dispatch(b, "advisor", "task", "brief", effort="")
    explicit_standard = mr.render_dispatch(b, "advisor", "task", "brief", effort="standard")
    return no_effort_kwarg == baseline == explicit_empty == explicit_standard


def test_run_dispatch_no_effort_argv_is_byte_identical_to_before():
    # Same DONE MEANS, at the run_dispatch/argv level: capture the argv codex
    # would be invoked with, before vs after adding --effort, with no effort given.
    seen = []
    orig_run = subprocess.run

    def _spy(argv, **kw):
        seen.append(list(argv))
        return orig_run(["cat"], **kw)
    subprocess.run = _spy
    try:
        b = _b(mr.LANE_GPT, invocation="cat")   # stand-in binary; argv shape is what's under test
        mr.run_dispatch(b, "advisor", "t", "b", timeout=5)
        mr.run_dispatch(b, "advisor", "t", "b", timeout=5, effort="")
        return seen[0] == seen[1] == ["cat"]
    finally:
        subprocess.run = orig_run


def test_effort_backend_field_defaults_to_standard():
    b = _b(mr.LANE_GPT)
    return b.effort == "standard"


# --- T3: effort validation (render_dispatch/run_dispatch) ------------------
# The CLI restricts --effort via argparse choices=, but render_dispatch and
# run_dispatch are also callable directly (not just via main()); an unknown
# effort value must not be interpolated as extra argv tokens on a CLI
# invocation (2026-07-05 review: "high --danger=1" repro).

def test_render_dispatch_rejects_unknown_effort():
    b = _b(mr.LANE_GPT, invocation="codex exec")
    try:
        mr.render_dispatch(b, "advisor", "task", "brief", effort="high --danger=1")
        return False    # must have raised
    except ValueError as e:
        return "high --danger=1" in str(e)


def test_render_dispatch_accepts_empty_and_known_efforts():
    b = _b(mr.LANE_GPT, invocation="codex exec")
    for tier in ("", *mr.EFFORT_TIERS):
        mr.render_dispatch(b, "advisor", "task", "brief", effort=tier)   # must not raise
    return True


def test_run_dispatch_unknown_effort_is_dropped_not_raised():
    # run_dispatch's never-raise contract is absolute: an unknown effort must
    # come back as ok=False (like any other dispatch failure), never propagate
    # the ValueError render_dispatch raises for the same input.
    b = _b(mr.LANE_GPT, invocation="codex exec")
    r = mr.run_dispatch(b, "advisor", "task", "brief", effort="high --danger=1", timeout=5)
    return (not r["ok"]) and "high --danger=1" in r["error"]


def test_run_dispatch_unknown_effort_never_invokes_subprocess():
    # The bad effort must be rejected BEFORE argv constructed from it ever
    # reaches subprocess.run — confirms this is validated at render/prepare
    # time, not just caught after a failed exec.
    calls = []
    orig_run = subprocess.run

    def _spy(argv, **kw):
        calls.append(list(argv))
        return orig_run(argv, **kw)
    subprocess.run = _spy
    try:
        b = _b(mr.LANE_GPT, invocation="cat")
        mr.run_dispatch(b, "advisor", "t", "b", effort="high --danger=1", timeout=5)
        return calls == []
    finally:
        subprocess.run = orig_run


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
