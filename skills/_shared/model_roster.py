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
    kind: str            # "cli" | "api" | "local"
    invocation: str      # the read-only command stem; "{model}" filled if local/tiered
    available: bool      # detected on this host right now
    probe: str           # how availability was decided (for transparency)
    models: list[str] = field(default_factory=list)   # local tags, if enumerable
    notes: str = ""


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


def detect_roster() -> list[Backend]:
    """Every KNOWN backend, each flagged available or not on this host. The full
    list (not just the available subset) is returned so a caller can show what is
    missing — `available_only()` filters."""
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

    return [
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
    return _SCAFFOLDS[role].format(task=task.strip() or "(task not given)",
                                   brief=brief.strip() or "(none recorded)")


def render_dispatch(b: Backend, role: Role, task: str, brief: str, *, model: str = "") -> str:
    """A copy-paste-runnable, read-only, synchronous dispatch for one backend.
    CLI lanes use a single-quoted heredoc on stdin so the multiline prompt needs
    no escaping and the shell expands nothing inside it."""
    prompt = render_prompt(role, task, brief)
    if b.kind in ("api", "http"):
        how = ("auto-runnable with --run (direct z.ai chat/completions)" if b.kind == "http"
               else "hand the agent this prompt, demand a synchronous final-message result")
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


def run_panel(roster: list[Backend], n: int, role: Role, task: str, brief: str, *,
              exclude_lane: str | None = None, timeout: float = 120.0) -> dict:
    """Pick a diverse panel and run every member. Returns survivors + failures
    separately so the caller can recompute quorum over who ACTUALLY responded."""
    panel = pick_panel(roster, n, exclude_lane=exclude_lane)
    runs = [run_dispatch(b, role, task, brief, timeout=timeout) for b in panel]
    survivors = [r for r in runs if r["ok"]]
    failures = [r for r in runs if not r["ok"]]
    return {"role": role, "requested": n, "dispatched": len(panel),
            "survivors": survivors, "failures": failures}


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
    ap.add_argument("--timeout", type=float, default=120.0, help="per-member dispatch timeout in seconds (--run)")
    args = ap.parse_args(argv)

    roster = detect_roster()

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
