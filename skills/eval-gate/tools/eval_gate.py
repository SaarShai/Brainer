#!/usr/bin/env python3
"""eval-gate — LLM-as-judge quality gate for arbitrary agent / content output.

Promotes the internal eval/judge.py harness (which measures *this catalog's own
skills*) into a user-facing skill you point at *your own* output — content
(drafts, posts, answers) or product (an agent's reply, an extraction, a
generated payload).

Three verbs map to the three places an eval loop runs:

  score    — judge ONE output against a rubric -> 0-5 + reason + pass/fail.
             (runtime / pre-ship check; exit 1 = below the line)
  suite    — judge a saved case-set, compare to a baseline -> regression delta.
             (pre-ship regression gate; exit 1 = a case failed or mean regressed)
  add-case — append a flagged bad output to the case-set as a permanent case.
             (the ratchet: every failure becomes a test, so the floor rises)

`score` and `suite` also take a per-criterion rubric (--criteria-file / --criteria-json):
each criterion is judged PASS/FAIL independently in one call, yielding a weighted
`score_norm`, a per-criterion breakdown, and `blocking_criteria` (a failed `required`
criterion fails the gate even if the weighted mean clears the threshold — so a FAIL names
*which* criterion missed, not just *that* the output is below the line). Without any
--criteria*, behavior is unchanged (single holistic 0-5).

Judge backends are lifted from eval/judge.py: local Ollama by default (no key),
Xiaomi MiMo when MIMO_API_KEY is set (--backend mimo). Scores are integer 0-5;
--threshold is a 0-1 fraction (default 0.7, the line below which nothing ships)
compared against score/5.

No third-party deps (stdlib + urllib). --stub-score scores without a model so
the plumbing is testable offline / in CI.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import re
import statistics
import sys
import time
import urllib.request
import uuid
from pathlib import Path

OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://127.0.0.1:11434/api/generate")
# DEFAULT_MODEL must name an Ollama tag that is actually installed on the host
# (check `ollama list` / `curl $OLLAMA_URL/../tags`). A bare "qwen2.5:7b" is NOT
# the same tag as "qwen2.5:7b-instruct" — using an absent tag makes /api/generate
# return HTTP 404 and the gate exits 2 "judge unreachable" even when Ollama is up.
# Override per-host with EVAL_GATE_MODEL.
DEFAULT_MODEL = os.environ.get("EVAL_GATE_MODEL", "qwen2.5:7b-instruct")
DEFAULT_BACKEND = os.environ.get("EVAL_GATE_BACKEND", "ollama")
DEFAULT_THRESHOLD = 0.7
# Compare the weighted criteria ratio to the threshold with a tiny epsilon: a ratio
# that is mathematically == threshold but lands at 0.6999999998 in float must still
# pass, while a genuinely sub-threshold ratio (e.g. 0.6995) must NOT be rounded up
# into a pass. 1e-9 sits far below any meaningful weight ratio yet well above double
# rounding error (~1e-15). Holistic 0-5 scores are exact multiples of 0.2 — unaffected.
_NORM_EPS = 1e-9
JUDGE_SYSTEM = "You are an evaluation judge. Be strict, fair, terse."

DEFAULT_RUBRIC = """\
Rate the candidate output from 0 to 5 against this standard:

5 = ships as-is: specific, correct, does what the task needs, no filler
4 = correct, minor verbosity or one small gap
3 = mostly there, some filler or a minor error
2 = partial: notable gaps or errors
1 = mostly wrong, generic, or off-task
0 = blank, hallucinated, or refused

Meta-question: would a competent reader act on this without re-doing it?
If no, it is not a 4+.

Respond with exactly one digit 0-5 on the first line, then a one-line reason.
"""

JUDGE_CRITERIA_SYSTEM = (
    "You are an evaluation judge. Judge each criterion INDEPENDENTLY and strictly "
    "against the candidate. A criterion passes only if the candidate clearly satisfies "
    "it; when unsure, FAIL. Be terse."
)

# A reason for ratcheting a failure into the suite must say WHY it's bad or what
# good looks like — mirrors write-gate's why-clause rule so the suite teaches
# instead of just accumulating. (For heavier signal-scoring of the reason, pipe
# it through skills/write-gate first.)
WHY_TOKENS = (
    "because", "so that", "to avoid", "in order to", "due to", "should",
    "expected", "instead", "rather than", "missing", "wrong", "hallucinat",
)

_MODEL_ROSTER = None
_HOLDS_RE = re.compile(r"(?im)^\s*holds\s*:\s*(true|false)\b")


# -------------------------- judge --------------------------------------------

_SCORE_FRACTION = re.compile(r"(\d+)\s*/\s*5\b")
_SCORE_BOLD = re.compile(r"\*+\s*([0-5])\s*\*+")
_SCORE_WORD = re.compile(r"(?i)\bscore\b[^0-9]{0,12}([0-5])\b")
_SCORE_STANDALONE = re.compile(r"\b([0-5])\b")


def _parse_score(out: str):
    """Tolerant parse of a judge reply -> (score:int|None, reason:str).

    Tries the instructed format (leading digit) first, then common real-model
    deviations: 'Score: 5', '**5**/5', '5/5', a bare 0-5 anywhere. Returns
    None only when no 0-5 signal is present (caller treats that as exit 2 —
    fail-safe, never a fabricated pass)."""
    out = (out or "").strip()
    if not out:
        return None, ""
    lines = out.splitlines()
    first = lines[0].strip()
    led_with_digit = bool(first) and first[0].isdigit() and 0 <= int(first[0]) <= 5
    score = int(first[0]) if led_with_digit else None
    # An explicit "N/5" fraction is authoritative: take the numerator and REJECT
    # out-of-range (a '7/5' reply is an invalid score, not a 5 lifted from the
    # denominator). Must run before the standalone fallback, which would match '5'.
    if score is None:
        frac = _SCORE_FRACTION.search(out)
        if frac:
            num = int(frac.group(1))
            return (num, " ".join(out.split()).strip()) if 0 <= num <= 5 else (None, "")
    for rx in (_SCORE_BOLD, _SCORE_WORD, _SCORE_STANDALONE):
        if score is not None:
            break
        m = rx.search(out)
        if m:
            score = int(m.group(1))
    if score is None:
        return None, ""
    if led_with_digit:
        reason = " ".join([first[1:].lstrip(" .:-)")] + [ln.strip() for ln in lines[1:]])
    else:
        reason = out
    return score, " ".join(reason.split()).strip()


_CRIT_TOKEN = re.compile(r"(?i)\b(pass|fail|yes|no|true|false)\b|[✓✗]")
# strict = only the INSTRUCTED verdict words; used on the positional-fallback path
# where a bare line may be ordinary prose ("Yes, here goes:"), so yes/no/true/false
# must NOT be mistaken for a verdict (that would steal a slot and shift the mapping).
_CRIT_STRICT = re.compile(r"(?i)\b(pass|fail)\b|[✓✗]")
_TRUE_TOKENS = ("pass", "yes", "true", "✓")


def _coerce_verdict(v):
    """Normalize a stubbed/loose criterion verdict -> (pass:bool, reason:str)."""
    if isinstance(v, bool):
        return v, "stub"
    if isinstance(v, (int, float)):
        return bool(v), "stub"
    if isinstance(v, str):
        t = v.strip().lower()
        return t in ("pass", "yes", "true", "1", "ok", "✓"), "stub"
    if isinstance(v, dict):
        p = v.get("pass")
        if p is None:
            p, _ = _coerce_verdict(v.get("verdict", ""))
        return bool(p), str(v.get("reason", "stub"))
    return False, "stub"


def _verdict_from(text, strict=False):
    """Extract (pass:bool, reason:str) from a line/tail, or None if no verdict token.

    Prefer an explicit PASS/FAIL/✓/✗ found ANYWHERE in the text, so a reason that
    opens with a prose 'no …'/'true …' before the real verdict does not invert it
    ('correct: no major issues, PASS' -> PASS). In `strict` mode — the positional
    fallback, where a bare line may be ordinary prose — ONLY pass/fail/✓/✗ count;
    bare yes/no/true/false are NOT verdicts."""
    text = (text or "").strip()
    tok = _CRIT_STRICT.search(text)
    if tok is None and not strict:
        tok = _CRIT_TOKEN.search(text)
    if tok is None:
        return None
    passed = tok.group(0).lower() in _TRUE_TOKENS
    reason = (text[:tok.start()] + text[tok.end():]).strip(" -–—:.")
    return passed, (reason or text)


def _parse_criteria(out, ids):
    """Tolerant parse of a per-criterion judge reply -> {id: (pass:bool, reason:str)}.

    Real models format these replies inconsistently, so resolution is layered:
      1. STRICT — a line '<id>: PASS|FAIL …' keyed by the exact criterion id (accepts
         YES/NO/TRUE/FALSE/✓/✗ in the tail, a leading '-'/'*' bullet or 'N.'/'N)'
         list marker, in any order). A line that names the id but carries no token is
         fail-safe FALSE (addressed but ambiguous), not dropped.
      2. POSITIONAL fallback — criteria whose id was NOT echoed consume the remaining
         strict-verdict lines (pass/fail/✓/✗ only) in order, so a model that NUMBERS
         the criteria ('1: FAIL', '2: PASS', …) parses correctly. Applied ONLY when
         the count of such lines exactly matches the un-echoed criteria; any mismatch
         (a stray PASS/FAIL prose line, extra or missing verdicts) is fail-safe FALSE
         rather than risk a shifted mis-map.
      3. Anything still unresolved is fail-safe FALSE (never a silent pass).
    Returns None only when the reply carries ZERO verdicts — the caller treats that
    as exit 2, the same fail-safe the holistic path uses for an unparseable reply."""
    lines = (out or "").splitlines()
    by_id = {}
    consumed = set()
    for cid in ids:
        for idx, ln in enumerate(lines):
            if idx in consumed:
                continue
            m = re.match(rf"^[ \t]*(?:[-*]+|\d+[.\)])?\s*{re.escape(cid)}\s*[:\-–]\s*(.*)$", ln, re.I)
            if m:
                tail = m.group(1).strip()
                v = _verdict_from(tail)
                by_id[cid] = v if v is not None else (False, tail or "no PASS/FAIL token")
                consumed.add(idx)
                break
    # strict-verdict lines (pass/fail/✓/✗ only) not claimed by an id-keyed match, in order
    unnamed = [v for idx, ln in enumerate(lines)
               if idx not in consumed and (v := _verdict_from(ln, strict=True)) is not None]
    if not by_id and not unnamed:
        return None
    verdicts = dict(by_id)
    unfilled = [cid for cid in ids if cid not in verdicts]
    if len(unnamed) == len(unfilled):
        for cid, v in zip(unfilled, unnamed):
            verdicts[cid] = v
    else:
        # count mismatch -> a positional zip could shift and fabricate a pass; reject safe
        for cid in unfilled:
            verdicts[cid] = (False, "ambiguous positional verdicts — fail-safe reject")
    return verdicts


def judge_ollama(model, task, candidate, rubric, timeout=300):
    body = json.dumps({
        "model": model,
        "system": JUDGE_SYSTEM,
        "prompt": f"TASK:\n{task}\n\nCANDIDATE:\n{candidate}\n\nRUBRIC:\n{rubric}\n",
        "stream": False,
        "options": {"temperature": 0.0},
    }).encode()
    req = urllib.request.Request(OLLAMA_URL, data=body, headers={"Content-Type": "application/json"})
    t0 = time.time()
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data = json.loads(resp.read())
    score, reason = _parse_score(data.get("response", "").strip())
    return {"score": score, "reason": reason, "latency_ms": int((time.time() - t0) * 1000)}


def judge_mimo(model, task, candidate, rubric, timeout=120):
    key = os.environ.get("MIMO_API_KEY")
    if not key:
        raise RuntimeError("MIMO_API_KEY not set (source .token-economy/secrets.env)")
    base = os.environ.get("MIMO_BASE_URL", "https://api.xiaomimimo.com/v1").rstrip("/")
    body = json.dumps({
        "model": model,
        "messages": [
            {"role": "system", "content": JUDGE_SYSTEM},
            {"role": "user", "content": f"TASK:\n{task}\n\nCANDIDATE:\n{candidate}\n\nRUBRIC:\n{rubric}"},
        ],
        "max_tokens": 200,
        "temperature": 0.0,
    }).encode()
    req = urllib.request.Request(
        f"{base}/chat/completions", data=body,
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"})
    t0 = time.time()
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data = json.loads(resp.read())
    out = data["choices"][0]["message"]["content"].strip()
    score, reason = _parse_score(out)
    return {"score": score, "reason": reason, "latency_ms": int((time.time() - t0) * 1000)}


# -------------------------- per-criterion judge ------------------------------

def _criteria_prompt(task, candidate, criteria):
    lines = "\n".join(f"- {c['id']}: {c['description']}" for c in criteria)
    return (
        f"TASK:\n{task}\n\nCANDIDATE:\n{candidate}\n\n"
        "Judge the candidate against EACH criterion INDEPENDENTLY. For every criterion, "
        "output exactly one line that BEGINS WITH the criterion's id token exactly as "
        "shown below (e.g. `correct:`), not a number, in this form:\n"
        "<id>: PASS or FAIL — <one-line reason>\n\n"
        f"CRITERIA:\n{lines}\n\nOutput one line per criterion id, nothing else.")


def _complete(backend, model, system, user, timeout=300):
    """Raw text completion for the criteria path (mirrors the holistic backends)."""
    if backend == "mimo":
        key = os.environ.get("MIMO_API_KEY")
        if not key:
            raise RuntimeError("MIMO_API_KEY not set (source .token-economy/secrets.env)")
        base = os.environ.get("MIMO_BASE_URL", "https://api.xiaomimimo.com/v1").rstrip("/")
        body = json.dumps({
            "model": model,
            "messages": [{"role": "system", "content": system},
                         {"role": "user", "content": user}],
            "max_tokens": 600, "temperature": 0.0,
        }).encode()
        req = urllib.request.Request(
            f"{base}/chat/completions", data=body,
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read())
        return data["choices"][0]["message"]["content"].strip()
    body = json.dumps({
        "model": model, "system": system, "prompt": user,
        "stream": False, "options": {"temperature": 0.0},
    }).encode()
    req = urllib.request.Request(OLLAMA_URL, data=body, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data = json.loads(resp.read())
    return data.get("response", "").strip()


def _score_criteria(criteria, verdicts):
    """verdicts: {id: (pass, reason)} -> (results, score_norm, blocking_criteria)."""
    results, total_w, won_w, blocking = [], 0.0, 0.0, []
    for c in criteria:
        cid, w, req = c["id"], c["weight"], c["required"]
        passed, reason = verdicts.get(cid, (False, "no verdict returned for this criterion"))
        results.append({"id": cid, "pass": passed, "score": 1.0 if passed else 0.0,
                        "weight": w, "required": req, "reason": reason})
        total_w += w
        won_w += w * (1.0 if passed else 0.0)
        if req and not passed:
            blocking.append(cid)
    # raw (unrounded) ratio — the gate compares this with _NORM_EPS; callers round only
    # for display. Rounding before the compare would let 0.6995 round up into a pass.
    norm = won_w / total_w if total_w > 0 else 0.0
    return results, norm, blocking


def run_judge_criteria(task, candidate, criteria, backend, model, stub_criteria=None):
    t0 = time.time()
    if stub_criteria is not None:
        verdicts = {cid: _coerce_verdict(v) for cid, v in stub_criteria.items()}
        latency = 0
    else:
        raw = _complete(backend, model, JUDGE_CRITERIA_SYSTEM,
                        _criteria_prompt(task, candidate, criteria))
        verdicts = _parse_criteria(raw, [c["id"] for c in criteria])
        latency = int((time.time() - t0) * 1000)
        if verdicts is None:
            return {"criteria": None, "score_norm": None,
                    "blocking_criteria": [], "latency_ms": latency}
    results, norm, blocking = _score_criteria(criteria, verdicts)
    return {"criteria": results, "score_norm": norm,
            "blocking_criteria": blocking, "latency_ms": latency}


def run_judge(task, candidate, rubric, backend, model, stub_score=None,
              criteria=None, stub_criteria=None):
    if criteria:
        return run_judge_criteria(task, candidate, criteria, backend, model, stub_criteria)
    if stub_score is not None:
        sv = int(stub_score)
        if not 0 <= sv <= 5:
            raise ValueError(f"--stub-score must be in 0-5, got {sv}")
        return {"score": sv, "reason": "stub", "latency_ms": 0}
    if backend == "mimo":
        return judge_mimo(model, task, candidate, rubric)
    return judge_ollama(model, task, candidate, rubric)


# -------------------------- verifier panel -----------------------------------

def _load_model_roster():
    """Lazy import so score without --panel keeps the historical dependency path."""
    global _MODEL_ROSTER
    if _MODEL_ROSTER is None:
        shared_dir = Path(__file__).resolve().parents[2] / "_shared"
        if str(shared_dir) not in sys.path:
            sys.path.insert(0, str(shared_dir))
        import model_roster  # type: ignore
        _MODEL_ROSTER = model_roster
    return _MODEL_ROSTER


def _panel_count(value):
    try:
        n = int(value)
    except ValueError:
        raise argparse.ArgumentTypeError("--panel must be an odd integer >= 3")
    if n < 3 or n % 2 == 0:
        raise argparse.ArgumentTypeError("--panel must be an odd integer >= 3")
    return n


def _one_line(text, limit=700):
    s = " ".join(str(text or "").split())
    return s if len(s) <= limit else s[:limit - 15].rstrip() + " ...[truncated]"


def _truncate_panel_text(text, limit=4000):
    s = str(text or "")
    return s if len(s) <= limit else s[:limit].rstrip() + "\n...[truncated]"


def _score_summary(res, verdict, criteria):
    if criteria:
        bits = [
            f"{c['id']}={'PASS' if c['pass'] else 'FAIL'}:{c['reason']}"
            for c in res.get("criteria", [])
        ]
        return _one_line(
            f"verdict={verdict} score_norm={round(res['score_norm'], 3)} "
            f"blocking_criteria={res.get('blocking_criteria', [])} criteria={'; '.join(bits)}"
        )
    return _one_line(
        f"score={res['score']}/5 score_norm={round(res['score'] / 5.0, 3)} "
        f"verdict={verdict} reason={res['reason']}"
    )


def _panel_result_from_dispatch(member, raw_result):
    result = dict(raw_result or {})
    holds = result.get("holds")
    if not isinstance(holds, bool):
        m = _HOLDS_RE.search(result.get("raw", "") or "")
        holds = (m.group(1).lower() == "true") if m else None
    return {
        "vendor": result.get("vendor") or getattr(member, "vendor", "unknown"),
        "lane": result.get("lane") or getattr(member, "lane", "unknown"),
        "ok": bool(result.get("ok")) and isinstance(holds, bool),
        "holds": holds,
        "findings": result.get("findings", ""),
        "error": result.get("error", "" if isinstance(holds, bool) else "missing holds: true|false"),
    }


def _print_panel_verdicts(results):
    print("eval-gate panel verdicts:", file=sys.stderr)
    for r in results:
        prefix = f"  [{r['lane']}] {r['vendor']}:"
        if r["ok"]:
            print(f"{prefix} holds={'true' if r['holds'] else 'false'}"
                  + (f" — {r['findings']}" if r["findings"] else ""), file=sys.stderr)
        else:
            print(f"{prefix} no verdict"
                  + (f" ({r['error']})" if r["error"] else ""), file=sys.stderr)


def _run_verifier_panel(n, threshold, rubric_txt, candidate, score_summary):
    roster_mod = _load_model_roster()
    roster = roster_mod.detect_roster()
    panel = roster_mod.pick_panel(roster, n)
    claim = f"This output meets the rubric at >= {threshold}: {score_summary}"
    brief = (
        f"RUBRIC:\n{_truncate_panel_text(rubric_txt)}\n\n"
        f"SCORED OUTPUT:\n{_truncate_panel_text(candidate)}"
    )
    results = []
    correlation_id = "run:" + uuid.uuid4().hex
    for member in panel:
        try:
            raw_result = roster_mod.run_dispatch(
                member, "verifier", claim, brief, correlation_id=correlation_id)
        except Exception as e:
            raw_result = {"ok": False, "error": f"dispatch raised: {e}"}
        results.append(_panel_result_from_dispatch(member, raw_result))
    responders = [r for r in results if r["ok"]]
    holds = sum(1 for r in responders if r["holds"] is True)
    refutes = sum(1 for r in responders if r["holds"] is False)
    return {
        "requested": n,
        "dispatched": len(panel),
        "responders": responders,
        "results": results,
        "majority_holds": holds > refutes,
    }


# -------------------------- io helpers ---------------------------------------

def _read_text(text, file):
    if text is not None:
        return text
    if file:
        return Path(file).read_text(encoding="utf-8")
    return sys.stdin.read()


def _rubric(args):
    if getattr(args, "rubric_text", None):
        return args.rubric_text
    if getattr(args, "rubric", None):
        return Path(args.rubric).read_text(encoding="utf-8")
    return DEFAULT_RUBRIC


_GROUNDING_RE = re.compile(
    r"\b(the input|the task|the source|the prompt|the brief\b|the original|"
    r"provided\b|given (?:input|data|source)|fabricat|hallucinat|grounded\b|"
    r"not (?:present |found |stated )?in the (?:input|source|task|prompt)|"
    r"against the (?:input|source|task|prompt)|present in the (?:input|source))",
    re.I)


def _rubric_needs_task(rubric_text: str) -> bool:
    """True if the rubric GROUNDS the candidate against its input (checks for
    fabrication / facts not in the source). Such a rubric is meaningless without
    --task: the judge has nothing to ground against and silently passes a fully
    fabricated candidate. ADVERSARIAL finding 2026-06-27 (PROMPTER opt run)."""
    return bool(_GROUNDING_RE.search(rubric_text or ""))


# LEARNING_CONTRACT §5: judge criteria must derive from the FULL spec + canon
# gates, never from the executor's claims or a rubric co-authored with the
# work. A dict-wrapped criteria payload may declare its provenance via
# "source"; anything outside this set (e.g. "executor-claims") names exactly
# the failure §5 exists to prevent and is rejected, not silently accepted.
_VALID_PROVENANCE = {"spec", "canon", "frozen-before-generation"}


def _check_provenance(raw, require: bool):
    """Validate a dict-wrapped criteria payload's declared "source" against
    LEARNING_CONTRACT §5. Raises ValueError (caller maps that to exit 2) when:
      - a declared source is present but not in _VALID_PROVENANCE (case-sensitive
        match — "SPEC" or "executor-claims" both reject),
      - --require-provenance was passed and no source is declared at all, or
      - --require-provenance was passed and the payload is a bare list (no dict
        wrapper at all): a bare list carries no "source" field to declare, so it
        would otherwise sail past the check below un-audited — the exact bypass
        of unwrapping a dict payload back to its bare "criteria" list to dodge
        --require-provenance. Without the flag, a bare list is untouched here
        (backward compatible)."""
    if not isinstance(raw, dict):
        if require:
            raise ValueError(
                "bare-list criteria carry no provenance; wrap in a dict with "
                "source per LEARNING_CONTRACT §5")
        return
    if "source" in raw and raw["source"] is None:
        raise ValueError(
            "provenance \"source\" is declared but null — a declared source "
            "must be a valid value (LEARNING_CONTRACT §5); omit the key "
            "entirely for legacy no-provenance payloads")
    source = raw.get("source")
    if source is None:
        if require:
            raise ValueError(
                "criteria payload declares no provenance \"source\" and "
                "--require-provenance was set (LEARNING_CONTRACT §5: judge "
                "criteria must derive from the spec/canon, never the "
                "executor's claims)")
        return
    if not isinstance(source, str):
        raise ValueError(
            f"provenance \"source\" must be a string, got {type(source).__name__} "
            f"({source!r}) — LEARNING_CONTRACT §5: judge criteria must derive "
            "from the spec/canon, never the executor's claims")
    if source not in _VALID_PROVENANCE:
        raise ValueError(
            f"invalid provenance source {source!r} — must be one of "
            f"{sorted(_VALID_PROVENANCE)} (LEARNING_CONTRACT §5: judge "
            "criteria must derive from the spec/canon, never the executor's "
            "claims)")


def _no_dup_keys_top(pairs):
    """object_pairs_hook: reject any JSON object with a repeated key. json.loads's
    default dict-building silently keeps the LAST value for a repeated key
    ({"source":"executor-claims","source":"spec"} parses to {"source":"spec"}) —
    laundering an invalid provenance value past _check_provenance, which only
    ever sees the winning last one. The top-level object of the criteria
    payload is where "source"/"criteria" are read (LEARNING_CONTRACT §5 checks
    raw.get("source") there), so catching it there is sufficient for the hole
    this closes; the hook fires on every nested object too (json.loads calls it
    for each), which is a strictly stricter — and harmless, since a duplicate
    key is never valid JSON either way — superset."""
    keys = [k for k, _ in pairs]
    dupes = {k for k in keys if keys.count(k) > 1}
    if dupes:
        raise ValueError(
            f"duplicate JSON key(s) {sorted(dupes)} in criteria payload — "
            "ambiguous/laundered provenance is rejected outright "
            "(LEARNING_CONTRACT §5)")
    return dict(pairs)


def _load_criteria(args):
    """Return a normalized criteria list, or None for holistic mode. Raises
    ValueError on a malformed criteria spec (caller maps that to exit 2)."""
    if getattr(args, "criteria_json", None):
        raw = json.loads(args.criteria_json, object_pairs_hook=_no_dup_keys_top)
    elif getattr(args, "criteria_file", None):
        raw = json.loads(Path(args.criteria_file).read_text(encoding="utf-8"),
                         object_pairs_hook=_no_dup_keys_top)
    else:
        return None
    _check_provenance(raw, bool(getattr(args, "require_provenance", False)))
    crit = raw.get("criteria") if isinstance(raw, dict) else raw
    if not isinstance(crit, list) or not crit:
        raise ValueError("criteria must be a non-empty list")
    seen, out = set(), []
    for c in crit:
        if not isinstance(c, dict) or "id" not in c or "description" not in c:
            raise ValueError("each criterion needs an id and a description")
        cid = str(c["id"])
        if cid in seen:
            raise ValueError(f"duplicate criterion id: {cid}")
        seen.add(cid)
        w = float(c.get("weight", 1.0))
        if not math.isfinite(w) or w <= 0:
            raise ValueError(f"criterion {cid}: weight must be a finite number > 0")
        out.append({"id": cid, "description": str(c["description"]),
                    "weight": w, "required": bool(c.get("required", False))})
    return out


def _load_stub_criteria(val):
    """--stub-criteria value: an existing file path, an @path, or inline JSON."""
    if val is None:
        return None
    if val.startswith("@"):
        return json.loads(Path(val[1:]).read_text(encoding="utf-8"))
    if Path(val).exists():
        return json.loads(Path(val).read_text(encoding="utf-8"))
    return json.loads(val)


def _load_cases(path: Path):
    cases = []
    for n, ln in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        s = ln.strip()
        if not s or s.startswith("#"):
            continue
        try:
            cases.append(json.loads(s))
        except json.JSONDecodeError as e:
            raise ValueError(f"{path} line {n}: bad JSON ({e.msg})")
    return cases


# -------------------------- commands -----------------------------------------

def cmd_score(args):
    candidate = _read_text(args.text, args.file)
    if not candidate.strip():
        print("eval-gate: empty candidate", file=sys.stderr)
        return 2
    try:
        criteria = _load_criteria(args)
        stub_crit = _load_stub_criteria(args.stub_criteria) if (criteria and args.stub_criteria) else None
    except (ValueError, OSError, json.JSONDecodeError) as e:
        print(f"eval-gate: bad criteria ({e})", file=sys.stderr)
        return 2
    rubric_txt = _rubric(args)
    # Fail-safe: a grounding rubric (one that checks the candidate against its
    # input for fabrication) is meaningless with an empty --task — the judge has
    # nothing to ground against and silently PASSES a fabricated candidate
    # (adversarial finding 2026-06-27). Refuse rather than wave it through. This
    # RAISES the bar; it never converts a fail into a pass.
    explicit_rubric = bool(getattr(args, "rubric", None) or getattr(args, "rubric_text", None))
    if (not criteria and explicit_rubric and not (getattr(args, "task", "") or "").strip()
            and _rubric_needs_task(rubric_txt)):
        print("eval-gate: REFUSED — this rubric grounds the candidate against its input "
              "(checks for fabrication / facts not in the source), but --task is empty, so "
              "nothing can be grounded and a fabricated candidate would pass silently. "
              "Pass --task with the input, or use a non-grounding rubric.", file=sys.stderr)
        return 2
    try:
        res = run_judge(args.task, candidate, rubric_txt, args.backend, args.model,
                        args.stub_score, criteria=criteria, stub_criteria=stub_crit)
    except Exception as e:
        print(f"eval-gate: judge unreachable ({args.backend}): {e}", file=sys.stderr)
        return 2
    if criteria:
        if res.get("score_norm") is None or res.get("criteria") is None:
            print("eval-gate: judge returned no parseable criteria verdicts", file=sys.stderr)
            return 2
        norm, blocking = res["score_norm"], res["blocking_criteria"]
        verdict = "fail" if (blocking or norm < args.threshold - _NORM_EPS) else "pass"
        output = {
            "verdict": verdict, "score_norm": round(norm, 3), "threshold": args.threshold,
            "blocking_criteria": blocking, "criteria": res["criteria"],
            "latency_ms": res["latency_ms"],
        }
        single_exit = 0 if verdict == "pass" else 1
        if args.panel is None:
            print(json.dumps(output, indent=2))
            return single_exit
        panel = _run_verifier_panel(
            args.panel, args.threshold, rubric_txt, candidate, _score_summary(res, verdict, criteria)
        )
        responders = panel["responders"]
        # <3 responders is a fabricated quorum — same rule as the plain-score
        # branch below (was <2: a half-fix caught by the 2026-07-05 review).
        if len(responders) < 3:
            print(f"panel degraded to single-judge (only {len(responders)} members reachable, need 3)",
                  file=sys.stderr)
            print(json.dumps(output, indent=2))
            return single_exit
        if single_exit != 0 or not panel["majority_holds"]:
            if not panel["majority_holds"]:
                output["verdict"] = "fail"
            _print_panel_verdicts(panel["results"])
            print(json.dumps(output, indent=2))
            return 1
        print(json.dumps(output, indent=2))
        return 0
    if res["score"] is None:
        print("eval-gate: judge returned no parseable score", file=sys.stderr)
        return 2
    norm = res["score"] / 5.0
    verdict = "pass" if norm >= args.threshold else "fail"
    output = {
        "score": res["score"], "score_norm": round(norm, 3),
        "threshold": args.threshold, "verdict": verdict,
        "reason": res["reason"], "latency_ms": res["latency_ms"],
    }
    single_exit = 0 if verdict == "pass" else 1
    if args.panel is None:
        print(json.dumps(output, indent=2))
        return single_exit
    panel = _run_verifier_panel(
        args.panel, args.threshold, rubric_txt, candidate, _score_summary(res, verdict, criteria)
    )
    responders = panel["responders"]
    # A 2-member "majority" is a fabricated quorum (2/2 or a tie) — a panel
    # verdict needs the full odd-N (>=3); anything less degrades loudly to the
    # single-judge result. (Cross-vendor review 2026-07-05.)
    if len(responders) < 3:
        print(f"panel degraded to single-judge (only {len(responders)} members reachable, need 3)",
              file=sys.stderr)
        print(json.dumps(output, indent=2))
        return single_exit
    if single_exit != 0 or not panel["majority_holds"]:
        if not panel["majority_holds"]:
            output["verdict"] = "fail"
        _print_panel_verdicts(panel["results"])
        print(json.dumps(output, indent=2))
        return 1
    print(json.dumps(output, indent=2))
    return 0


def cmd_suite(args):
    cases_path = Path(args.cases)
    if not cases_path.exists():
        print(f"eval-gate: no case-set at {cases_path}", file=sys.stderr)
        return 2
    try:
        cases = _load_cases(cases_path)
    except ValueError as e:
        print(f"eval-gate: {e}", file=sys.stderr)
        return 2
    if not cases:
        print("eval-gate: case-set is empty", file=sys.stderr)
        return 2
    rubric_default = _rubric(args)
    try:
        criteria = _load_criteria(args)
        args_stub_crit = _load_stub_criteria(args.stub_criteria) if (criteria and args.stub_criteria) else None
    except (ValueError, OSError, json.JSONDecodeError) as e:
        print(f"eval-gate: bad criteria ({e})", file=sys.stderr)
        return 2
    scored = []
    for i, c in enumerate(cases):
        cand = c.get("candidate")
        if cand is None and c.get("candidate_file"):
            cand = Path(c["candidate_file"]).read_text(encoding="utf-8")
        stub = c.get("stub_score", args.stub_score)
        stub_crit = None
        if criteria:
            sc = c.get("stub_criteria")
            if isinstance(sc, str):
                sc = _load_stub_criteria(sc)
            stub_crit = sc if sc is not None else args_stub_crit
        try:
            r = run_judge(c.get("task", ""), cand or "", c.get("rubric", rubric_default),
                          args.backend, args.model, stub, criteria=criteria, stub_criteria=stub_crit)
        except Exception as e:
            print(f"eval-gate: case {c.get('id', i)} judge error: {e}", file=sys.stderr)
            return 2
        if criteria:
            if r.get("score_norm") is None:
                print(f"eval-gate: case {c.get('id', i)} produced no criteria verdicts", file=sys.stderr)
                return 2
            norm, blocking = r["score_norm"], r["blocking_criteria"]
            passed = (not blocking) and norm >= args.threshold - _NORM_EPS
            scored.append({"id": c.get("id", i), "norm": round(norm, 3), "pass": passed,
                           "blocking": blocking,
                           "reason": "; ".join(f"{x['id']}:{'P' if x['pass'] else 'F'}" for x in r["criteria"])})
            continue
        if r["score"] is None:
            print(f"eval-gate: case {c.get('id', i)} produced no score", file=sys.stderr)
            return 2
        norm = r["score"] / 5.0
        scored.append({"id": c.get("id", i), "score": r["score"], "norm": round(norm, 3),
                       "pass": norm >= args.threshold, "reason": r["reason"]})
    mean_r = round(statistics.mean(s["norm"] for s in scored), 3)
    n_pass = sum(1 for s in scored if s["pass"])
    report = {
        "n": len(scored), "n_pass": n_pass, "pass_rate": round(n_pass / len(scored), 3),
        "mean_norm": mean_r, "threshold": args.threshold, "cases": scored,
    }
    regressed = False
    if args.baseline and Path(args.baseline).exists():
        base = json.loads(Path(args.baseline).read_text())
        base_mean = base.get("mean_norm", 0.0)
        # compare rounded-to-rounded so an identical re-run can't false-regress
        delta = round(mean_r - base_mean, 3)
        report["baseline_mean"] = base_mean
        report["delta_mean"] = delta
        if delta < -abs(args.max_drop):
            regressed = True
    if args.save_baseline:
        Path(args.save_baseline).write_text(json.dumps(
            {"mean_norm": mean_r, "pass_rate": report["pass_rate"], "n": len(scored)}, indent=2))
        report["saved_baseline"] = args.save_baseline
    print(json.dumps(report, indent=2))
    all_pass = n_pass == len(scored)
    return 0 if (all_pass and not regressed) else 1


def _ratchet_gate(reason: str):
    reason = (reason or "").strip()
    if len(reason) < 12:
        return False, "reason too thin (<12 chars) — say WHY it's bad or what good looks like"
    if not any(w in reason.lower() for w in WHY_TOKENS):
        return False, "reason needs a why/expectation clause (because / so that / expected / should …)"
    return True, "ok"


def cmd_add_case(args):
    candidate = _read_text(args.text, args.file)
    if not candidate.strip():
        print("eval-gate: empty candidate", file=sys.stderr)
        return 2
    ok, why = _ratchet_gate(args.reason)
    if not ok and not args.force:
        print(f"eval-gate: case rejected — {why}", file=sys.stderr)
        print("  revise --reason, or pass --force to add anyway", file=sys.stderr)
        return 1
    cases_path = Path(args.cases)
    try:
        existing = _load_cases(cases_path) if cases_path.exists() else []
    except ValueError as e:
        print(f"eval-gate: {e}", file=sys.stderr)
        return 2
    case = {
        "id": args.id or f"case-{len(existing) + 1:03d}",
        "task": args.task,
        "candidate": candidate,
        "reason": args.reason,
        "added_iso": time.strftime("%FT%TZ", time.gmtime()),
    }
    if args.rubric:
        case["rubric"] = Path(args.rubric).read_text(encoding="utf-8")
    cases_path.parent.mkdir(parents=True, exist_ok=True)
    with open(cases_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(case) + "\n")
    print(f"eval-gate: added {case['id']} to {cases_path}"
          + ("" if ok else "  [forced]"))
    return 0


# -------------------------- cli ----------------------------------------------

def _add_judge_args(p):
    p.add_argument("--backend", default=DEFAULT_BACKEND, choices=["ollama", "mimo"])
    p.add_argument("--model", default=DEFAULT_MODEL)
    p.add_argument("--threshold", type=float, default=DEFAULT_THRESHOLD,
                   help="0-1 line; score/5 below it = fail (default 0.7)")
    p.add_argument("--rubric", help="path to a rubric file")
    p.add_argument("--rubric-text", help="rubric inline")
    p.add_argument("--stub-score", type=int, default=None,
                   help="skip the model; force this 0-5 score (testing / CI)")
    p.add_argument("--criteria-file", help="JSON file: list of {id, description, weight?, "
                   "required?} -> per-criterion rubric mode")
    p.add_argument("--criteria-json", help="inline JSON criteria list (per-criterion mode)")
    p.add_argument("--require-provenance", action="store_true",
                   help="reject a dict-wrapped criteria payload with no declared "
                   "\"source\" (LEARNING_CONTRACT §5); bare-list criteria are "
                   "unaffected either way")
    p.add_argument("--stub-criteria", help="skip the model; per-criterion verdicts as inline "
                   "JSON, @path, or path: {id: \"pass\"|\"fail\"} (testing / CI)")


def _add_candidate_args(p):
    p.add_argument("--file", help="read candidate from this file")
    p.add_argument("--text", help="candidate inline (else stdin)")
    p.add_argument("--task", default="", help="the input/prompt that produced the candidate")


def main():
    ap = argparse.ArgumentParser(prog="eval_gate.py", description="LLM-as-judge quality gate")
    sub = ap.add_subparsers(dest="cmd", required=True)

    ps = sub.add_parser("score", help="judge one output against a rubric")
    _add_judge_args(ps)
    _add_candidate_args(ps)
    ps.add_argument("--panel", type=_panel_count, metavar="N",
                    help="run an odd-N verifier panel after the normal score")
    ps.set_defaults(fn=cmd_score)

    pu = sub.add_parser("suite", help="judge a saved case-set vs a baseline (regression gate)")
    _add_judge_args(pu)
    pu.add_argument("--cases", required=True, help="JSONL case-set")
    pu.add_argument("--baseline", help="baseline JSON to compare against")
    pu.add_argument("--save-baseline", help="write the current mean as the new baseline")
    pu.add_argument("--max-drop", type=float, default=0.0,
                    help="allowed mean drop vs baseline before exit 1 (default 0)")
    pu.set_defaults(fn=cmd_suite)

    pa = sub.add_parser("add-case", help="ratchet a flagged failure into the case-set")
    _add_candidate_args(pa)
    pa.add_argument("--cases", required=True, help="JSONL case-set to append to")
    pa.add_argument("--reason", required=True, help="WHY it's bad / what good looks like")
    pa.add_argument("--rubric", help="optional per-case rubric file")
    pa.add_argument("--id", help="case id (default: auto case-NNN)")
    pa.add_argument("--force", action="store_true", help="add even if the reason fails the gate")
    pa.set_defaults(fn=cmd_add_case)

    args = ap.parse_args()
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
