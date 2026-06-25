#!/usr/bin/env python3
"""model_roster — detect reachable cross-vendor model backends and render a
read-only, synchronous dispatch for two distinct loop roles.

This is the shared primitive behind the multi-model panels Brainer wires into a
loop (see skills/loop-engineering/SKILL.md). It answers one question — *which
other models can this host actually reach right now* — and renders the exact
dispatch command + role-scaffolded prompt for each, so a skill never hardcodes a
fixed `codex / gemini / claude` triple again.

TWO ROLES, one roster (the distinction is the whole point — collapsing them
re-opens the LLM-judge hole loop_lint R1/R3 exist to refuse):

  • ADVISOR  — DIVERGENT. Feeds the GENERATOR. Proposes structurally-different
    approaches / tools / methods to break a stall. Output is fresh hypotheses,
    NEVER a pass/fail verdict. Fired on STUCK (loop-engineering's ≥3-attempt
    stuck detector), cost-gated, one round, bounded panel.

  • VERIFIER — CONVERGENT. IS the gate. Re-runs the key check and REFUTES if it
    can. Output is holds:bool + evidence. Odd-N (default 3) majority, refutation
    blocks ship. The same mechanism verify-before-completion Part D already names.

A panel prefers VENDOR DIVERSITY (distinct lanes) and EXCLUDES the orchestrator's
own lane — a cross-vendor check from the same family is barely a second opinion.

The dispatch contract is read-only + SYNCHRONOUS + findings-in-the-final-message
by construction (a fire-and-forget `codex exec` returns nothing the loop can
gate on — the lesson behind the codex-rescue sync-dispatch rule).

Stdlib only (house style mirrors loop_lint.py / cache_lint.py). Detection is
cheap and never blocks: `shutil.which` for CLIs, env vars for API lanes, one
best-effort short-timeout `ollama list` for local model tags.

DETECTION IS PATH-LEVEL, NOT A LIVENESS PROBE: a CLI in PATH is reported
available, but `which` != usable — an unauthenticated or misconfigured CLI (e.g.
a logged-out `gemini`) parses fine and then throws at dispatch. A consuming panel
must treat a dispatch failure as "drop that member and proceed with the
survivors", never as a hard stop; that is why a verifier panel wants an ODD count
of ACTUALLY-RESPONDING members, recomputed after dispatch, not before.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from dataclasses import asdict, dataclass, field
from typing import Literal

# Cross-vendor egress is the moment repo content leaves this host for a third-party
# model. Scrub a broad secret family from the prompt BEFORE it is rendered, so a
# leaked key/.env value/PEM block never crosses the wire — whether the caller
# copy-pastes render_dispatch's output or auto-runs via run_dispatch (both funnel
# through render_prompt). One shared scrubber (skills/_shared/audit_redact.py), so
# the redaction surface matches the audit tools. Borrowed control: ksimback/looper's
# redaction globs, generalized to secret-shape detection. cf. loop_lint R12.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    from audit_redact import redact as _redact          # type: ignore
except Exception:                                        # pragma: no cover - defensive
    def _redact(s: str) -> str:                          # never let a missing import egress raw
        return s

Role = Literal["advisor", "verifier"]

# Vendor LANES — the diversity unit. Two backends in the same lane (codex + an
# OpenAI API key) are NOT a cross-vendor pair; panel selection dedups by lane.
LANE_GPT = "gpt"
LANE_CLAUDE = "claude"
LANE_GEMINI = "gemini"
LANE_LOCAL = "local"
LANE_GLM = "glm"


@dataclass
class Backend:
    vendor: str          # human label, e.g. "GPT via Codex CLI"
    lane: str            # diversity key, one of the LANE_* constants
    kind: str            # "cli" | "api" | "http" | "local"
    invocation: str      # the read-only command stem; "{model}" filled if local/tiered
    available: bool      # detected on this host right now
    probe: str           # how availability was decided (for transparency)
    models: list[str] = field(default_factory=list)   # local tags, if enumerable
    notes: str = ""
    transport: str = ""  # "" = native CLI/local/zai; "openrouter" = dispatched via the OpenRouter proxy
    slug: str = ""       # provider model id for a proxied lane, e.g. "openai/gpt-5-mini"


# --- Detection ------------------------------------------------------------

def _ollama_models(timeout: float = 3.0) -> list[str]:
    """Best-effort local model tags. Never raises, never blocks past `timeout`."""
    if not shutil.which("ollama"):
        return []
    try:
        out = subprocess.run(
            ["ollama", "list"], capture_output=True, text=True, timeout=timeout
        )
    except (subprocess.TimeoutExpired, OSError):
        return []
    tags: list[str] = []
    for line in out.stdout.splitlines()[1:]:      # skip the header row
        tok = line.split()
        if tok:
            tags.append(tok[0])
    return tags


def _codex_glm_config(path: str = "") -> str:
    """Return the codex z.ai/GLM config signal if `~/.codex/config.toml` (or a
    given path) wires a z.ai provider or glm profile, else "". This is why GLM can
    be reachable even when the bare ZAI_API_KEY is not exported into this process:
    codex reads its own `env_key` from the user's shell. Best-effort, never raises."""
    p = path or os.path.expanduser("~/.codex/config.toml")
    try:
        with open(p, encoding="utf-8", errors="ignore") as fh:
            text = fh.read()
    except OSError:
        return ""
    if "[model_providers.zai]" in text or "[profiles.glm]" in text or "glm-5.2" in text:
        return p
    return ""


def _zai_key() -> str:
    """The z.ai key from the env, else the file the shell rc exports it from
    (`~/.config/zai/key`). This is why GLM is reachable without the var exported
    into a non-login tool shell. Never raises."""
    k = next((os.environ[v] for v in ("ZAI_API_KEY", "Z_AI_API_KEY", "GLM_API_KEY") if os.environ.get(v)), "")
    if k:
        return k
    try:
        with open(os.path.expanduser("~/.config/zai/key"), encoding="utf-8", errors="ignore") as fh:
            return fh.read().strip()
    except OSError:
        return ""


def _run_glm(prompt: str, *, timeout: float, model: str = "glm-5.2",
             base: str = "https://api.z.ai/api/coding/paas/v4") -> tuple[bool, str, str]:
    """Dispatch GLM directly over z.ai's OpenAI-compatible chat/completions
    (proven HTTP 200; codex's Responses-only wire 404s here, so this bypasses
    codex entirely). Returns (ok, text, error). Never raises."""
    key = _zai_key()
    if not key:
        return False, "", "no z.ai key (env ZAI_API_KEY/… or ~/.config/zai/key)"
    import urllib.error
    import urllib.request
    # max_tokens is REQUIRED in practice: glm-5.2 is a reasoning model, and without a
    # cap it emits an unbounded reasoning trace and the request times out (measured).
    body = json.dumps({"model": model, "max_tokens": 2048,
                       "messages": [{"role": "user", "content": prompt}]}).encode()
    req = urllib.request.Request(f"{base}/chat/completions", data=body, method="POST",
                                 headers={"Authorization": f"Bearer {key}",
                                          "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8", "ignore"))
        msg = data["choices"][0]["message"]
        # glm-5.2 splits thinking into `reasoning_content`; when the budget lands the
        # whole reply there and leaves `content` empty, fall back to it so a panel
        # member is never silently dropped for a non-empty response.
        text = (msg.get("content") or "").strip() or (msg.get("reasoning_content") or "").strip()
        if not text:
            return False, "", "z.ai returned empty content + reasoning"
        return True, text, ""
    except (urllib.error.URLError, OSError) as e:
        return False, "", f"z.ai dispatch failed: {e}"
    except (KeyError, ValueError, IndexError) as e:
        return False, "", f"z.ai unexpected response shape: {e}"


# --- OpenRouter transport -------------------------------------------------
# OpenRouter is NOT a lane — it is a TRANSPORT that can serve many vendor lanes
# through one OpenAI-compatible API + one key. It BACKFILLS a lane when no native
# CLI exists (preserving diversity-by-lane and the free subscription reuse of the
# native CLIs), and can OPTIONALLY be preferred for every non-orchestrator lane
# (`prefer_transport`) to consolidate everything behind one provider. The verifier
# gate logic is unchanged either way — OpenRouter is wire, not judgment.

# Default production slugs per lane (real ids from the live catalog; override with
# env OPENROUTER_MODEL_<LANE>, e.g. OPENROUTER_MODEL_GPT). Mid-tier, chat-capable,
# non-image/-codex variants — a panel member, not a flagship spend.
_OPENROUTER_SLUGS = {
    LANE_GPT: "openai/gpt-5-mini",
    LANE_GEMINI: "google/gemini-3-flash-preview",
    LANE_CLAUDE: "anthropic/claude-haiku-4.5",
    LANE_GLM: "z-ai/glm-4.6",
}
# Lanes OpenRouter is allowed to provide. LOCAL is deliberately excluded: the
# ollama lane is the on-box SURVIVOR backstop against the proxy being a single
# point of failure (the documented June-2025 OpenRouter 403 of Claude+Gemini), so
# it must never be routed THROUGH the proxy.
_OPENROUTER_LANES = (LANE_GPT, LANE_GEMINI, LANE_CLAUDE, LANE_GLM)
_OPENROUTER_BASE = "https://openrouter.ai/api/v1"


def _openrouter_key() -> str:
    """The OpenRouter key from the env, else `~/.config/openrouter/key` (mirrors
    `_zai_key` — same reason: reachable without the var exported into this shell).
    Never raises."""
    k = next((os.environ[v] for v in ("OPENROUTER_API_KEY", "OPENROUTER_KEY") if os.environ.get(v)), "")
    if k:
        return k
    try:
        with open(os.path.expanduser("~/.config/openrouter/key"), encoding="utf-8", errors="ignore") as fh:
            return fh.read().strip()
    except OSError:
        return ""


def _openrouter_slug(lane: str) -> str:
    """The model slug for a lane, env-overridable per lane."""
    return os.environ.get(f"OPENROUTER_MODEL_{lane.upper()}") or _OPENROUTER_SLUGS.get(lane, "")


def _run_openrouter(prompt: str, *, timeout: float, model: str,
                    base: str = _OPENROUTER_BASE) -> tuple[bool, str, str]:
    """Dispatch one prompt through OpenRouter's OpenAI-compatible chat/completions
    (twin of `_run_glm`, different base/key/headers). max_tokens is capped for the
    same reason — a reasoning model with no cap can run unbounded — and the reply
    falls back to `reasoning` when `content` lands empty. Returns (ok, text, err);
    never raises so a failing member is dropped, not fatal."""
    key = _openrouter_key()
    if not key:
        return False, "", "no OpenRouter key (env OPENROUTER_API_KEY/… or ~/.config/openrouter/key)"
    if not model:
        return False, "", "no OpenRouter model slug for this lane"
    import urllib.error
    import urllib.request
    body = json.dumps({"model": model, "max_tokens": 2048,
                       "messages": [{"role": "user", "content": prompt}]}).encode()
    req = urllib.request.Request(f"{base}/chat/completions", data=body, method="POST",
                                 headers={"Authorization": f"Bearer {key}",
                                          "Content-Type": "application/json",
                                          # OpenRouter attribution headers (optional, recommended).
                                          "HTTP-Referer": "https://github.com/brainer/loop-engineering",
                                          "X-Title": "Brainer loop-engineering panel"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8", "ignore"))
    except (urllib.error.URLError, OSError) as e:
        return False, "", f"OpenRouter dispatch failed: {e}"
    except ValueError as e:
        return False, "", f"OpenRouter unparseable response: {e}"
    # OpenRouter surfaces upstream errors (402 credits, provider overload) in-body.
    if isinstance(data, dict) and data.get("error"):
        return False, "", f"OpenRouter: {str(data['error'].get('message', data['error']))[:160]}"
    try:
        msg = data["choices"][0]["message"]
    except (KeyError, IndexError, TypeError) as e:
        return False, "", f"OpenRouter unexpected response shape: {e}"
    text = (msg.get("content") or "").strip() or (msg.get("reasoning") or "").strip()
    if not text:
        return False, "", "OpenRouter returned empty content + reasoning"
    return True, text, ""


def detect_roster(*, prefer_transport: str = "") -> list[Backend]:
    """Every KNOWN backend, each flagged available or not on this host. The full
    list (not just the available subset) is returned so a caller can show what is
    missing — `available_only()` filters.

    `prefer_transport="openrouter"` flips selection to prefer the OpenRouter-backed
    backend for every eligible lane even when a native CLI exists (one-provider
    consolidation / the ours-vs-OpenRouter comparison). Default "" keeps native
    CLIs preferred and only BACKFILLS lanes OpenRouter can reach but the host
    cannot natively."""
    codex = shutil.which("codex")
    claude = shutil.which("claude")
    gemini = shutil.which("gemini")
    agy = shutil.which("agy")                             # Antigravity headless CLI (subscription auth)
    ollama = shutil.which("ollama")
    local_models = _ollama_models() if ollama else []
    zai_key = _zai_key()                                 # env OR ~/.config/zai/key
    codex_glm = _codex_glm_config()                      # GLM also wired through codex config
    gemini_key = next((k for k in ("GEMINI_API_KEY", "GOOGLE_API_KEY", "GOOGLE_GENAI_API_KEY")
                       if os.environ.get(k)), "")
    or_key = _openrouter_key()                           # OpenRouter transport, if configured

    native = [
        Backend(
            vendor="GPT via Codex CLI", lane=LANE_GPT, kind="cli",
            invocation="codex exec",
            available=bool(codex),
            probe="which(codex)" + ("" if codex else " → not found"),
            notes="synchronous; demand a FINDINGS: block in the final message or it fire-and-forgets.",
        ),
        Backend(
            # PREFER `agy` — Antigravity's headless CLI — it dispatches Gemini on the
            # SUBSCRIPTION (no API key), reading the prompt on stdin (`-p`). The plain
            # `gemini` CLI's oauth-personal free tier was retired by Google, so it only
            # works headless with a GEMINI_API_KEY; agy is the subscription path.
            vendor="Gemini via Antigravity (agy)" if agy else "Gemini CLI",
            lane=LANE_GEMINI, kind="cli",
            invocation=("agy -p --print-timeout 120s --model 'Gemini 3.5 Flash (Low)'" if agy
                        else "gemini --approval-mode plan -p ''"),
            available=bool(agy or (gemini and gemini_key)),
            probe=("which(agy) → Antigravity subscription (no API key)" if agy
                   else ("which(gemini)" if gemini else "which(gemini) → not found")
                   + (f"+{gemini_key}" if gemini_key
                      else " → no GEMINI_API_KEY (oauth-personal free tier retired by Google)")),
            notes=("Antigravity `agy -p` runs Gemini on your subscription (no API key). Models: Gemini 3.5 Flash "
                   "(L/M/H), Gemini 3.1 Pro (L/H) — pick via --model. Read-only here (advisor/verifier prompts "
                   "don't ask it to edit)." if agy
                   else "plan mode = read-only. The `gemini` CLI's free oauth tier was RETIRED by Google; needs a "
                        "GEMINI_API_KEY or an eligible account. Subscription path is the `agy` CLI (not installed here)."),
        ),
        Backend(
            vendor="Claude via CLI", lane=LANE_CLAUDE, kind="cli",
            invocation="claude -p --model {model}",
            available=bool(claude),
            probe="which(claude)" + ("" if claude else " → not found"),
            notes="cross-vendor only when the orchestrator is NOT Claude; otherwise a same-lane self-check.",
        ),
        Backend(
            vendor="Local model via Ollama", lane=LANE_LOCAL, kind="local",
            invocation="ollama run {model}",
            available=bool(ollama and local_models),
            probe=("which(ollama)+list" if ollama else "which(ollama) → not found")
                  + ("" if local_models else " → no tags"),
            models=local_models,
            notes="zero API cost; weakest reasoning — use as an extra divergent voice, not the deciding verifier.",
        ),
        Backend(
            # kind=http → run_dispatch calls z.ai's chat/completions directly (proven 200).
            # Falls back to kind=api (handoff to glm-executor) only when no key is obtainable.
            vendor="GLM-5.2 via z.ai", lane=LANE_GLM,
            kind="http" if zai_key else "api",
            invocation="z.ai chat/completions (glm-5.2)" if zai_key else "dispatch via the glm-executor subagent",
            available=bool(zai_key or codex_glm),
            probe=("key: env or ~/.config/zai/key" if zai_key
                   else f"codex config {codex_glm} (key not readable here)" if codex_glm
                   else "no z.ai key (env/​~/.config/zai/key) and no codex zai provider"),
            notes="glm-5.2, 1M context, low cost. Auto-runnable here over z.ai's OpenAI-compatible "
                  "chat/completions. NOTE: codex's `--profile glm` route is wire-BLOCKED — recent codex speaks "
                  "ONLY the Responses API, but z.ai's coding endpoint serves chat/completions (/responses → 404); "
                  "not a config bug, a protocol mismatch, so the panel uses the direct z.ai path, not codex.",
        ),
    ]

    # OpenRouter transport: one OpenAI-compatible API + key fronting many lanes.
    # BACKFILL (default): add an OpenRouter-backed backend for any eligible lane the
    # host can't reach natively. PREFER (prefer_transport="openrouter"): override the
    # native backend for every eligible lane, so selection consolidates on the proxy.
    if or_key:
        native_avail = {b.lane for b in native if b.available}
        for lane in _OPENROUTER_LANES:
            slug = _openrouter_slug(lane)
            if not slug:
                continue
            prefer = prefer_transport == "openrouter"
            if not prefer and lane in native_avail:
                continue                                  # native CLI wins unless told to prefer the proxy
            orb = Backend(
                vendor=f"{lane.upper()} via OpenRouter ({slug})", lane=lane, kind="http",
                invocation=f"OpenRouter chat/completions ({slug})",
                available=True, probe="key: env or ~/.config/openrouter/key",
                transport="openrouter", slug=slug,
                notes="OpenRouter proxy — one key, many lanes, provider-level failover. "
                      "Auto-runnable here over its OpenAI-compatible chat/completions. "
                      + ("PREFERRED over the native lane (prefer_transport)." if prefer
                         else "BACKFILL — no native CLI for this lane on this host."),
            )
            if prefer:
                native = [b for b in native if b.lane != lane] + [orb]   # replace the native lane
            else:
                native.append(orb)

    return native


def available_only(roster: list[Backend]) -> list[Backend]:
    return [b for b in roster if b.available]


# --- Panel selection ------------------------------------------------------

def pick_panel(roster: list[Backend], n: int, *, exclude_lane: str | None = None) -> list[Backend]:
    """Up to `n` AVAILABLE backends, one per lane (max diversity), excluding the
    orchestrator's own `exclude_lane`. Lane order is a stable preference, not a
    quality ranking — diversity is the goal, so we take at most one per lane."""
    seen: set[str] = set()
    panel: list[Backend] = []
    # Preference order: strongest distinct external reasoners first, local last.
    order = [LANE_GPT, LANE_GEMINI, LANE_CLAUDE, LANE_GLM, LANE_LOCAL]
    by_lane = {b.lane: b for b in available_only(roster)}
    for lane in order:
        if len(panel) >= n:
            break
        if lane == exclude_lane or lane in seen:
            continue
        b = by_lane.get(lane)
        if b:
            panel.append(b)
            seen.add(lane)
    return panel


# --- Role scaffolds -------------------------------------------------------

_ADVISOR_SCAFFOLD = """\
You are an ADVISOR, not a judge. Do NOT return a pass/fail verdict — that is a
different agent's job. You are READ-ONLY: propose, do not edit files or run
mutating commands.

A loop is STUCK on this task:
{task}

Already tried and abandoned (do not re-suggest these):
{brief}

Propose 1-3 STRUCTURALLY DIFFERENT approaches — a different method, a different
tool, a different decomposition, or a different assumption to challenge. For each:
one line of rationale + the first concrete step. End with:
FINDINGS: <one-line summary of your strongest fresh hypothesis>"""

_VERIFIER_SCAFFOLD = """\
You are an independent VERIFIER from a different vendor. You are READ-ONLY.
Re-run the key check yourself and REFUTE the claim below if you can — assume it
is wrong until the evidence forces otherwise.

Claim to verify:
{task}

Evidence provided by the producer (re-derive it; do not trust it):
{brief}

Return strictly:
holds: true|false
evidence: <the command you ran + its output, or the artifact you checked>
FINDINGS: <one line — what would have to be true for the claim to fail>"""

_SCAFFOLDS = {"advisor": _ADVISOR_SCAFFOLD, "verifier": _VERIFIER_SCAFFOLD}


def render_prompt(role: Role, task: str, brief: str) -> str:
    # Redact BEFORE formatting: task/brief are repo-derived and about to egress to a
    # cross-vendor model. The scaffold text itself is static and safe.
    task = _redact(task.strip()) or "(task not given)"
    brief = _redact(brief.strip()) or "(none recorded)"
    return _SCAFFOLDS[role].format(task=task, brief=brief)


def render_dispatch(b: Backend, role: Role, task: str, brief: str, *, model: str = "") -> str:
    """A copy-paste-runnable, read-only, synchronous dispatch for one backend.
    CLI lanes use a single-quoted heredoc on stdin so the multiline prompt needs
    no escaping and the shell expands nothing inside it."""
    prompt = render_prompt(role, task, brief)
    if b.kind in ("api", "http"):
        if b.kind == "http" and b.transport == "openrouter":
            how = "auto-runnable with --run (OpenRouter chat/completions)"
        elif b.kind == "http":
            how = "auto-runnable with --run (direct z.ai chat/completions)"
        else:
            how = "hand the agent this prompt, demand a synchronous final-message result"
        return (f"# {b.vendor} — {b.invocation}\n"
                f"# role={role}; {how}:\n{prompt}")
    inv = b.invocation
    if "{model}" in inv:
        chosen = model or (b.models[0] if b.models else "MODEL")
        inv = inv.format(model=chosen)
    delim = f"LOOP_{role.upper()}_EOF"
    return f"{inv} <<'{delim}'\n{prompt}\n{delim}"


# --- Execution (opt-in) ---------------------------------------------------
# render_dispatch is the default (pure, testable, no spend). run_panel actually
# dispatches — opt-in because each call is real spend that can FAIL (an
# unauthenticated CLI throws), so the decision to spend belongs to the loop, not
# to detection. Every member runs through argv (no shell), prompt on stdin: no
# heredoc, no shell expansion, no injection surface. A member that times out,
# exits non-zero, or is missing is DROPPED (ok=False) and the panel proceeds with
# the survivors — never a hard stop (the which≠usable contract).

_ANSI = re.compile(r"\x1b\[[0-9;?]*[ -/]*[@-~]|\x1b[@-Z\\-_]")


def _strip_ansi(s: str) -> str:
    return _ANSI.sub("", s)


def _extract_findings(text: str) -> str:
    """The FINDINGS: line the scaffold demands, else the last non-empty line."""
    lines = [ln.strip() for ln in _strip_ansi(text).splitlines() if ln.strip()]
    for ln in reversed(lines):
        if ln.upper().startswith("FINDINGS:"):
            return ln[len("FINDINGS:"):].strip()
    return lines[-1] if lines else ""


def run_dispatch(b: Backend, role: Role, task: str, brief: str, *,
                 model: str = "", timeout: float = 120.0) -> dict:
    """Execute ONE backend read-only, prompt on stdin, capture the result. Never
    raises — a failure is reported as ok=False with the reason, so the caller can
    drop it and keep the survivors."""
    import shlex     # stdlib; local so the pure path needs no import
    result = {"vendor": b.vendor, "lane": b.lane, "role": role,
              "ok": False, "findings": "", "raw": "", "error": ""}
    if b.kind == "http" and b.transport == "openrouter":
        ok, text, err = _run_openrouter(render_prompt(role, task, brief),
                                        timeout=timeout, model=model or b.slug)
        text = _strip_ansi(text)
        result.update(ok=ok, raw=text,
                      findings=_extract_findings(text) if ok else "", error=err)
        return result
    if b.kind == "http" and b.lane == LANE_GLM:
        ok, text, err = _run_glm(render_prompt(role, task, brief),
                                 timeout=timeout, model=model or "glm-5.2")
        text = _strip_ansi(text)
        result.update(ok=ok, raw=text,
                      findings=_extract_findings(text) if ok else "", error=err)
        return result
    if b.kind == "api":
        result["error"] = "api lane: dispatch via the glm-executor subagent, not auto-runnable from this util"
        return result
    inv = b.invocation
    if "{model}" in inv:
        inv = inv.format(model=model or (b.models[0] if b.models else "MODEL"))
    try:
        argv = shlex.split(inv)
    except ValueError as e:
        result["error"] = f"unparseable invocation {inv!r}: {e}"
        return result
    prompt = render_prompt(role, task, brief)
    try:
        proc = subprocess.run(argv, input=prompt, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        result["error"] = f"timeout after {timeout:.0f}s"
        return result
    except (OSError, ValueError) as e:
        result["error"] = f"dispatch failed: {e}"
        return result
    out = _strip_ansi(proc.stdout or "")
    result["raw"] = out
    if proc.returncode != 0:
        # an unauthenticated / misconfigured CLI lands here (the gemini case)
        result["error"] = f"exit {proc.returncode}: {_strip_ansi(proc.stderr or '')[:200].strip()}"
        return result
    result["ok"] = True
    result["findings"] = _extract_findings(out)
    return result


def verifier_quorum(n_survivors: int) -> dict:
    """Assess whether a VERIFIER panel of `n_survivors` ACTUALLY-RESPONDING members
    is a sound gate. A verifier gate needs an ODD count ≥3 for a clean refute-able
    majority — `which != usable`, so members drop at dispatch and the count must be
    recomputed AFTER the run, never assumed from `requested`. R11b: a 1-member or
    even panel is a weak gate, not a quorum. Returns {ok, reason}."""
    if n_survivors >= 3 and n_survivors % 2 == 1:
        return {"ok": True, "reason": f"{n_survivors} responders, odd majority"}
    if n_survivors < 3:
        return {"ok": False, "reason": f"only {n_survivors} responder(s) — a verifier gate wants ≥3 "
                "(a 1-vendor check is barely a second opinion; majority is undefined)"}
    return {"ok": False, "reason": f"{n_survivors} responders is EVEN — no clean majority; drop one or "
            "add a tie-break before treating this as a gate"}


def run_panel(roster: list[Backend], n: int, role: Role, task: str, brief: str, *,
              exclude_lane: str | None = None, timeout: float = 120.0) -> dict:
    """Pick a diverse panel and run every member. Returns survivors + failures
    separately so the caller can recompute quorum over who ACTUALLY responded."""
    panel = pick_panel(roster, n, exclude_lane=exclude_lane)
    runs = [run_dispatch(b, role, task, brief, timeout=timeout) for b in panel]
    survivors = [r for r in runs if r["ok"]]
    failures = [r for r in runs if not r["ok"]]
    out = {"role": role, "requested": n, "dispatched": len(panel),
           "survivors": survivors, "failures": failures}
    # R11b: a verifier panel's quorum is only known after dispatch (members drop).
    if role == "verifier":
        out["quorum"] = verifier_quorum(len(survivors))
    return out


# --- Fusion advisor (OpenRouter) ------------------------------------------
# Fusion is OpenRouter's productised ADVISOR: fan the prompt to a panel (3–8
# models in parallel), a judge returns a STRUCTURED synthesis (consensus /
# contradictions / partial coverage / unique insights / blind spots). It is the
# diverge-and-synthesise half only — it is CONSENSUS-oriented, not refute-if-you-
# can, the judge prompt + output schema are FIXED, and it returns analysis not a
# boolean. So it maps to our ADVISOR, never the VERIFIER gate (that stays ours;
# wiring Fusion as the gate would re-open the LLM-judge hole loop_lint R1/R3
# refuse). The judge `model` and the `analysis_models` panel are configurable.

_FUSION_MODEL = "openrouter/fusion"


def fusion_request_body(task: str, brief: str, *, analysis_models: list[str] | None = None,
                        judge_model: str = "", preset: str = "", max_tokens: int = 2048) -> dict:
    """Pure builder for the Fusion request body (separated so it is testable with
    no network/credits). The advisor scaffold is reused so Fusion gets the same
    'propose, do not judge' framing the native advisor panel gets."""
    plugin: dict = {"id": "fusion"}
    if preset:
        plugin["preset"] = preset
    if analysis_models:
        plugin["analysis_models"] = list(analysis_models)
    if judge_model:
        plugin["model"] = judge_model
    return {"model": _FUSION_MODEL, "max_tokens": max_tokens,
            "plugins": [plugin],
            "messages": [{"role": "user", "content": render_prompt("advisor", task, brief)}]}


def run_fusion(task: str, brief: str, *, analysis_models: list[str] | None = None,
               judge_model: str = "", preset: str = "", timeout: float = 180.0,
               base: str = _OPENROUTER_BASE) -> dict:
    """Run OpenRouter Fusion as the advisor. Returns {ok, findings, raw, error}.
    Never raises — a credit/availability failure is reported, not fatal. NOTE: the
    exact Fusion plugin wire is confirmed against the live API the first time a
    credited key runs it; until then treat the request shape as provisional."""
    result = {"vendor": "Fusion panel (OpenRouter)", "role": "advisor",
              "ok": False, "findings": "", "raw": "", "error": ""}
    key = _openrouter_key()
    if not key:
        result["error"] = "no OpenRouter key"
        return result
    import urllib.error
    import urllib.request
    body = json.dumps(fusion_request_body(task, brief, analysis_models=analysis_models,
                                          judge_model=judge_model, preset=preset)).encode()
    req = urllib.request.Request(f"{base}/chat/completions", data=body, method="POST",
                                 headers={"Authorization": f"Bearer {key}",
                                          "Content-Type": "application/json",
                                          "HTTP-Referer": "https://github.com/brainer/loop-engineering",
                                          "X-Title": "Brainer loop-engineering Fusion advisor"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8", "ignore"))
    except (urllib.error.URLError, OSError) as e:
        result["error"] = f"Fusion dispatch failed: {e}"
        return result
    except ValueError as e:
        result["error"] = f"Fusion unparseable response: {e}"
        return result
    if isinstance(data, dict) and data.get("error"):
        result["error"] = f"Fusion: {str(data['error'].get('message', data['error']))[:160]}"
        return result
    try:
        text = _strip_ansi((data["choices"][0]["message"].get("content") or "").strip())
    except (KeyError, IndexError, TypeError) as e:
        result["error"] = f"Fusion unexpected response shape: {e}"
        return result
    if not text:
        result["error"] = "Fusion returned empty content"
        return result
    result.update(ok=True, raw=text, findings=_extract_findings(text) or text[:400])
    return result


# --- CLI ------------------------------------------------------------------

def _print_human(roster: list[Backend]) -> None:
    avail = available_only(roster)
    print(f"model roster — {len(avail)}/{len(roster)} backend(s) reachable")
    for b in roster:
        mark = "✓" if b.available else "·"
        extra = f"  models={b.models}" if b.models else ""
        print(f"  {mark} [{b.lane:6}] {b.vendor}  ({b.probe}){extra}")
        if b.available and b.notes:
            print(f"        → {b.notes}")


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(
        prog="model_roster",
        description="Detect reachable cross-vendor model backends and render read-only dispatches.")
    ap.add_argument("--json", action="store_true", help="emit the full roster as JSON")
    ap.add_argument("--panel", type=int, metavar="N",
                    help="select up to N diverse available backends and render dispatches")
    ap.add_argument("--role", choices=["advisor", "verifier"], default="advisor",
                    help="role scaffold for --panel dispatches (default: advisor)")
    ap.add_argument("--exclude-lane", choices=[LANE_GPT, LANE_CLAUDE, LANE_GEMINI, LANE_LOCAL, LANE_GLM],
                    help="the orchestrator's own lane, excluded from the panel (cross-vendor)")
    ap.add_argument("--task", default="", help="the task / claim text for the dispatch prompt")
    ap.add_argument("--brief", default="", help="the decision brief / evidence (what was tried, or the proof)")
    ap.add_argument("--run", action="store_true",
                    help="ACTUALLY dispatch the --panel (real spend); drop failed members, print survivors' findings")
    ap.add_argument("--consent", action="store_true",
                    help="explicit consent to egress repo-derived prompt content to cross-vendor models "
                         "(required by --run; or set MODEL_ROSTER_EGRESS_CONSENT=1). Prompts are secret-redacted "
                         "first, but the task/brief text still leaves this host — this gate makes that a choice, "
                         "not a default.")
    ap.add_argument("--timeout", type=float, default=120.0, help="per-member dispatch timeout in seconds (--run)")
    ap.add_argument("--via", choices=["openrouter"], default="",
                    help="prefer this transport for every eligible lane even when a native CLI exists "
                         "(one-provider consolidation / ours-vs-OpenRouter comparison)")
    ap.add_argument("--fusion", action="store_true",
                    help="advisor via OpenRouter Fusion (panel→judge synthesis) instead of the native panel; "
                         "with --run, dispatches it (needs credits). Advisor only — never the verifier gate.")
    ap.add_argument("--analysis-models", default="",
                    help="comma-separated OpenRouter slugs for the Fusion analysis panel (optional)")
    ap.add_argument("--judge-model", default="", help="OpenRouter slug for the Fusion judge (optional)")
    ap.add_argument("--preset", default="", help="Fusion preset, e.g. general-high | general-budget (optional)")
    args = ap.parse_args(argv)

    # R12b consent gate: any --run egresses repo-derived content cross-vendor. Refuse
    # unless the operator opted in (flag or env), so egress is a deliberate act. Pure
    # rendering (no --run) never egresses, so it is exempt.
    consent = args.consent or os.environ.get("MODEL_ROSTER_EGRESS_CONSENT", "").strip().lower() in {"1", "true", "yes", "on"}
    if args.run and not consent:
        print("# refusing --run: cross-vendor egress without consent. The prompt is secret-redacted, but the "
              "task/brief still leaves this host. Re-run with --consent (or MODEL_ROSTER_EGRESS_CONSENT=1) to "
              "authorize. Omit --run to render the dispatch locally without sending anything.", file=sys.stderr)
        return 2

    if args.fusion:
        am = [s.strip() for s in args.analysis_models.split(",") if s.strip()] or None
        if args.run:
            res = run_fusion(args.task, args.brief, analysis_models=am,
                             judge_model=args.judge_model, preset=args.preset, timeout=args.timeout)
            if args.json:
                print(json.dumps(res, indent=2))
            elif res["ok"]:
                print(f"# Fusion advisor RUN — ok\n  FINDINGS: {res['findings']}")
            else:
                print(f"# Fusion advisor — FAILED: {res['error']}", file=sys.stderr)
            return 0 if res["ok"] else 1
        body = fusion_request_body(args.task, args.brief, analysis_models=am,
                                   judge_model=args.judge_model, preset=args.preset)
        print("# Fusion advisor request body (POST {}/chat/completions); add --run to dispatch:".format(_OPENROUTER_BASE))
        print(json.dumps(body, indent=2))
        return 0

    roster = detect_roster(prefer_transport=args.via)

    if args.panel is not None:
        # verifier panels want an odd N for a clean majority; advisor panels do not.
        panel = pick_panel(roster, args.panel, exclude_lane=args.exclude_lane)
        if not panel:
            print("# no cross-vendor backend reachable — fall back to a fresh-context same-vendor "
                  "subagent (separate context/worktree), and say so explicitly.", file=sys.stderr)
            return 1
        if args.role == "verifier" and len(panel) % 2 == 0:
            print(f"# note: {len(panel)} verifiers is even — add a tie-break or drop to an odd panel "
                  "for a clean majority.", file=sys.stderr)
        if args.run:
            res = run_panel(roster, args.panel, args.role, args.task, args.brief,
                            exclude_lane=args.exclude_lane, timeout=args.timeout)
            if args.json:
                print(json.dumps(res, indent=2))
            else:
                print(f"# {args.role} panel RUN — {len(res['survivors'])}/{res['dispatched']} responded"
                      + (f", excluding lane '{args.exclude_lane}'" if args.exclude_lane else ""))
                for r in res["survivors"]:
                    print(f"  ✓ [{r['lane']}] {r['vendor']}\n      FINDINGS: {r['findings']}")
                for r in res["failures"]:
                    print(f"  ✗ [{r['lane']}] {r['vendor']}  (dropped: {r['error']})")
                q = res.get("quorum")
                if q and not q["ok"]:
                    print(f"  ⚠ R11b weak verifier quorum: {q['reason']} — do NOT treat this as a passed gate.",
                          file=sys.stderr)
            # survivors present → 0; all members failed → 1 (caller decides on an empty panel)
            return 0 if res["survivors"] else 1
        blocks = [render_dispatch(b, args.role, args.task, args.brief) for b in panel]
        if args.json:
            print(json.dumps({"role": args.role, "panel": [b.vendor for b in panel],
                              "dispatches": blocks}, indent=2))
        else:
            print(f"# {args.role} panel — {len(panel)} backend(s), vendor-diverse"
                  + (f", excluding lane '{args.exclude_lane}'" if args.exclude_lane else ""))
            print("\n\n".join(blocks))
        return 0

    if args.json:
        print(json.dumps([asdict(b) for b in roster], indent=2))
    else:
        _print_human(roster)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
