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
import os
import re
import statistics
import sys
import time
import urllib.request
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

# A reason for ratcheting a failure into the suite must say WHY it's bad or what
# good looks like — mirrors write-gate's why-clause rule so the suite teaches
# instead of just accumulating. (For heavier signal-scoring of the reason, pipe
# it through skills/write-gate first.)
WHY_TOKENS = (
    "because", "so that", "to avoid", "in order to", "due to", "should",
    "expected", "instead", "rather than", "missing", "wrong", "hallucinat",
)


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


def run_judge(task, candidate, rubric, backend, model, stub_score=None):
    if stub_score is not None:
        sv = int(stub_score)
        if not 0 <= sv <= 5:
            raise ValueError(f"--stub-score must be in 0-5, got {sv}")
        return {"score": sv, "reason": "stub", "latency_ms": 0}
    if backend == "mimo":
        return judge_mimo(model, task, candidate, rubric)
    return judge_ollama(model, task, candidate, rubric)


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
        res = run_judge(args.task, candidate, _rubric(args), args.backend, args.model, args.stub_score)
    except Exception as e:
        print(f"eval-gate: judge unreachable ({args.backend}): {e}", file=sys.stderr)
        return 2
    if res["score"] is None:
        print("eval-gate: judge returned no parseable score", file=sys.stderr)
        return 2
    norm = res["score"] / 5.0
    verdict = "pass" if norm >= args.threshold else "fail"
    print(json.dumps({
        "score": res["score"], "score_norm": round(norm, 3),
        "threshold": args.threshold, "verdict": verdict,
        "reason": res["reason"], "latency_ms": res["latency_ms"],
    }, indent=2))
    return 0 if verdict == "pass" else 1


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
    scored = []
    for i, c in enumerate(cases):
        cand = c.get("candidate")
        if cand is None and c.get("candidate_file"):
            cand = Path(c["candidate_file"]).read_text(encoding="utf-8")
        stub = c.get("stub_score", args.stub_score)
        try:
            r = run_judge(c.get("task", ""), cand or "", c.get("rubric", rubric_default),
                          args.backend, args.model, stub)
        except Exception as e:
            print(f"eval-gate: case {c.get('id', i)} judge error: {e}", file=sys.stderr)
            return 2
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
