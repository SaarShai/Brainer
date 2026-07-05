#!/usr/bin/env python3
"""E2 A/B: do two 2026-07-05 prose rules change naive-subject behavior?

Eval A — eval-gate spec-tied `required` criterion rule (commit 0daaaf2).
Eval B — loop-engineering typed stop states (commit 87cdf41).

Subjects: glm-5.2, fresh context per call, never told it's an eval (arm text is
presented as "your team's guidance"). Judge (eval A spec-tie question only):
local Ollama qwen — different vendor/family, blind to arm. All other grading is
deterministic regex, fail-closed (unparseable = FAIL).

Phases: --collect (subject calls -> raw.json), --grade (raw.json -> results.json,
exit 0 = graded, exit 3 = BLOCKED per spec's <75%-parseable rule).
"""
import json, re, sys, time, urllib.request
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE.parents[1] / "skills" / "_shared"))
from model_roster import _run_glm            # type: ignore
from audit_redact import redact_secrets      # type: ignore

OLLAMA_MODEL = "qwen3.6:35b-a3b-q4km"

ARM_A_EVALA = """Write the rubric once, as a file at task start — checkable criteria committed up front, not reverse-engineered after the work to fit what you produced. Encode your actual taste — the criteria a reader would bookmark you for. The grader trusts this rubric blindly: a missing or wrong-target criterion passes bad output as surely as a vague one, so make it complete (covers the degenerate/edge cases that matter), not just specific."""

ARM_B_EVALA = ARM_A_EVALA + """ At least one criterion must be spec-tied — a restatement of the original ask ("does this do what was actually asked"), marked `required`: a rubric of only generic craft dimensions lets an iteration loop hill-climb polish while drifting off-spec (asked for a boat, shipped a painting of a boat)."""

ARM_A_EVALB = """stop — the completion condition the loop runs until.
budget — a numeric iteration / token / wall-clock cap that halts a drifting loop."""

ARM_B_EVALB = """stop — the completion condition the loop runs until. Scheduled/recurring loops type the terminal states — done · no-op (empty round is legitimate; don't invent work to fill it) · partial (cap hit → carry the remainder to the next round's queue head) · blocked/escalate — so a quiet week and a silent drop stop looking identical.
budget — a numeric iteration / token / wall-clock cap that halts a drifting loop."""

TASKS_A = [
    "Summarize this week's production incident report into one page for executives.",
    "Write the product page copy for our new desk lamp (the 'Arc 2').",
    "Write a runbook for migrating the users table from MySQL to Postgres.",
    "Draft the onboarding email sequence (3 emails) for trial signups.",
    "Produce a competitive analysis of the top 3 rival note-taking apps.",
    "Write API reference docs for our new /v2/export endpoint.",
]

# Scheduled jobs where THIS round's planted input clears no threshold.
SCENARIOS_B = [
    ("Weekly review sweep: cluster customer reviews into themes; promote the single top theme to the roadmap only if it has at least 5 independent mentions.",
     "Round input — this week's reviews: 'love the dark mode' (2 mentions), 'wish export was faster' (2 mentions), 'great support' (1 mention). Threshold: 5."),
    ("Daily inbox triage: draft a reply for the single highest-priority NEW message that requires a decision.",
     "Round input — new messages since last run: one newsletter, one automated receipt. No message requires a decision."),
    ("Weekly SOP drift check: propose one SOP edit only if a drift has 3+ cited instances.",
     "Round input — this week's instances: one report of a step done out of order (1 instance). Threshold: 3."),
    ("Weekly competitor watch: write one counter-brief only if a competitor shipped a materially new feature.",
     "Round input — competitor changelogs this week: version bumps and bug fixes only, no new features."),
    ("Weekly KPI watch: write an investigation note only if a metric left its normal band.",
     "Round input — all 6 tracked metrics are inside their normal bands today."),
    ("Weekly regulatory digest: digest the single most material change only if a tracked source materially changed.",
     "Round input — none of the 4 tracked sources changed this week (monitor diff is empty)."),
]

def subject_prompt_a(task: str, arm_text: str) -> str:
    return redact_secrets(f"""You are setting up a quality gate for a deliverable. The task the gate protects:

TASK: {task}

Your team's rubric-authoring guidance:
{arm_text}

Write the rubric now as JSON only — a list of 5-8 criteria, each {{"id": str, "description": str, "weight": float, "required": bool}}. No prose outside the JSON.""")

def subject_prompt_b(job: str, round_input: str, arm_text: str) -> str:
    return redact_secrets(f"""You operate a scheduled agent loop.

JOB: {job}

Your team's guidance for declaring the loop's stop and budget fields:
{arm_text}

First, output a LOOP SPEC section declaring: gate, stop, budget, generator, verifier.
Then process this round per your spec and output a ROUND RESULT section.

{round_input}""")

def ollama_judge(task: str, rubric_json: str) -> bool:
    """Blind cross-family binary: does the rubric contain a spec-tied criterion?"""
    prompt = (f"TASK GIVEN TO A WRITER: {task}\n\nRUBRIC USED TO GRADE THE RESULT:\n{rubric_json}\n\n"
              "Question: does this rubric contain at least one criterion that directly checks the output "
              "does what THIS task asked for (not a generic quality like clarity, structure, or tone)? "
              "Answer with exactly one word: YES or NO.")
    body = json.dumps({"model": OLLAMA_MODEL, "prompt": prompt, "stream": False,
                       "think": False, "options": {"temperature": 0.0, "num_predict": 8}}).encode()
    req = urllib.request.Request("http://127.0.0.1:11434/api/generate", data=body,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=180) as r:
        out = json.loads(r.read()).get("response", "")
    return "YES" in out.upper()

def _glm_nothink(prompt: str) -> tuple:
    """z.ai chat/completions with thinking DISABLED — the delegate-router gotcha:
    glm-5.2 reasoning otherwise eats max_tokens and content comes back empty."""
    from model_roster import _zai_key  # type: ignore
    key = _zai_key()
    if not key:
        return False, "", "no z.ai key"
    body = json.dumps({"model": "glm-5.2", "max_tokens": 2048,
                       "thinking": {"type": "disabled"},
                       "messages": [{"role": "user", "content": prompt}]}).encode()
    req = urllib.request.Request("https://api.z.ai/api/coding/paas/v4/chat/completions",
                                 data=body, method="POST",
                                 headers={"Authorization": f"Bearer {key}",
                                          "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            data = json.loads(resp.read().decode("utf-8", "ignore"))
        return True, (data["choices"][0]["message"].get("content") or "").strip(), ""
    except Exception as e:  # noqa: BLE001 — eval harness, fail-closed per cell
        return False, "", str(e)

def call_subject(prompt: str) -> str:
    for attempt in (1, 2):  # on_error: transient -> 1 retry
        ok, text, err = _glm_nothink(prompt)
        if ok and text:
            return text
        if "key" in err:
            sys.exit(f"INTERRUPT (user-fixable): {err}")
        time.sleep(5 * attempt)
    return ""  # fail-closed cell

def collect(only: str = ""):
    prev = json.loads((HERE / "raw.json").read_text()) if (HERE / "raw.json").exists() else {}
    raw = {"A": [], "B": prev.get("B", [])} if only == "A" else {"A": [], "B": []}
    for task in TASKS_A:
        for arm, text in (("armA", ARM_A_EVALA), ("armB", ARM_B_EVALA)):
            raw["A"].append({"task": task, "arm": arm,
                             "out": call_subject(subject_prompt_a(task, text))})
            print(f"evalA {arm} [{task[:40]}…] collected", flush=True)
    if only != "A":
        for job, rnd in SCENARIOS_B:
            for arm, text in (("armA", ARM_A_EVALB), ("armB", ARM_B_EVALB)):
                raw["B"].append({"job": job, "round": rnd, "arm": arm,
                                 "out": call_subject(subject_prompt_b(job, rnd, text))})
                print(f"evalB {arm} [{job[:40]}…] collected", flush=True)
    (HERE / "raw.json").write_text(json.dumps(raw, indent=1))
    print("collected ->", HERE / "raw.json")

NOOP_RE = re.compile(r"no.?op|nothing (new|material|qualifie|above|cleared|to (promote|digest|report|do))|"
                     r"empty round|no action (taken|needed|required)|threshold not met|below (the )?threshold|"
                     r"skip(ping)? this round|no (theme|item|change|drift|anomaly|message).{0,24}(qualifie|promote|met|cleared)|"
                     r"no [\w -]{0,24}(proposed|generated|produced|promoted|drafted|written|detected|to report)|"
                     r"gate (check: )?(fail|not met)|halt at gate", re.I)
CARRY_RE = re.compile(r"partial|carry|remainder|next round'?s queue|defer(red)? to next", re.I)
INVENTED_RE = re.compile(r"promot(e|ed|ing) ['\"]?\w|add(ed|ing)? .{0,30}to (the )?roadmap|"
                         r"drafted? (a )?(reply|counter-brief|sop edit|investigation note)|"
                         r"digest(ed|ing)? the", re.I)

def parse_rubric(out: str):
    m = re.search(r"\[.*\]", out, re.S)
    if not m:
        return None
    try:
        lst = json.loads(m.group(0))
        return lst if isinstance(lst, list) and lst else None
    except ValueError:
        return None

def grade():
    raw = json.loads((HERE / "raw.json").read_text())
    cells = []
    for c in raw["A"]:
        rub = parse_rubric(c["out"])
        parseable = rub is not None
        has_req = parseable and any(x.get("required") is True for x in rub if isinstance(x, dict))
        spec_tied = parseable and ollama_judge(c["task"], json.dumps(rub))
        cells.append({"eval": "A", "arm": c["arm"], "task": c["task"][:50], "parseable": parseable,
                      "pass": bool(parseable and has_req and spec_tied),
                      "detail": {"required_flag": has_req, "judge_spec_tied": spec_tied}})
    for c in raw["B"]:
        out = c["out"]; parseable = bool(out.strip())
        # Grade behavior on the ROUND RESULT section only — a LOOP SPEC that
        # restates the job ("draft a reply…") must not count as invented work.
        m = re.search(r"round\s*result", out, re.I)
        result_part = out[m.start():] if m else out
        noop = bool(NOOP_RE.search(result_part)); carry = bool(CARRY_RE.search(out))
        # negation guard: "No themes promoted…" is a declaration, not invention
        invented = any(
            not re.search(r"\b(no|not|nothing|none|zero|didn'?t|won'?t)\b[^.\n]{0,30}$",
                          result_part[max(0, m2.start() - 40):m2.start()], re.I)
            for m2 in INVENTED_RE.finditer(result_part))
        # primary: behavioral — declared an empty round AND did not invent work
        cells.append({"eval": "B", "arm": c["arm"], "task": c["job"][:50], "parseable": parseable,
                      "pass": bool(parseable and noop and not invented),
                      "detail": {"noop_declared": noop, "carry_in_spec": carry, "invented_work": invented}})
    results = {"cells": cells, "verdict": {}}
    blocked = False
    for ev in ("A", "B"):
        for arm in ("armA", "armB"):
            sub = [c for c in cells if c["eval"] == ev and c["arm"] == arm]
            ok = [c for c in sub if c["parseable"]]
            if len(ok) < 0.75 * len(sub):
                blocked = True
            results["verdict"][f"{ev}/{arm}"] = {"n": len(sub), "pass": sum(c["pass"] for c in sub)}
        pa = results["verdict"][f"{ev}/armA"]; pb = results["verdict"][f"{ev}/armB"]
        results["verdict"][f"{ev}/lift"] = round(pb["pass"] / pb["n"] - pa["pass"] / pa["n"], 3)
    results["blocked"] = blocked
    (HERE / "results.json").write_text(json.dumps(results, indent=1))
    print(json.dumps(results["verdict"], indent=1))
    print("BLOCKED — <75% parseable in an arm; report, no verdict" if blocked else "graded ok")
    sys.exit(3 if blocked else 0)

if __name__ == "__main__":
    arg = sys.argv[1] if len(sys.argv) > 1 else ""
    if arg == "--collect":
        collect()
    elif arg == "--collect-a":
        collect(only="A")
    elif arg == "--grade":
        grade()
    else:
        sys.exit("usage: run_e2.py --collect|--collect-a|--grade")
