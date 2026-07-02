#!/usr/bin/env python3
"""trigger_suite — adherence layer 1/2: does a NAIVE agent pick the right skill?

For each corpus case, a cold subject model is shown ONLY the resident catalog
(the 24 skill names + descriptions — exactly what a real session holds) plus
the user prompt, and must answer `SKILL: <name>` or `SKILL: none`. Scoring:

  expect=fire   → PASS iff the subject named the corpus's target skill
  expect=silent → PASS iff the subject did NOT name the target skill
                  (naming a different, legitimately-applicable skill is fine)

Two firing paths are measured separately (the house lesson: model
self-invocation is weak; canary prompt_intent probes are the reliable path):

  --mode model   subject-model choice against the catalog (default)
  --mode probe   mechanical: the target skill's drift_probes.json prompt_intent
                 regexes against the raw prompt (no model; skills without a
                 prompt_intent probe report as NO-PROBE — itself a finding)

Subjects: --backend ollama (local, free; default) and/or --backend glm
(z.ai via model_roster._run_glm). Unreachable backend → loud skip, never faked.

  python3 eval/adherence/trigger_suite.py                      # probe + ollama
  python3 eval/adherence/trigger_suite.py --backend glm --backend ollama
  python3 eval/adherence/trigger_suite.py --mode probe         # mechanical only

Report-only baseline (no gating exit code yet — first measure, then ratchet).
Stdlib only; reuses model_roster helpers for GLM/ollama detection.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
CORPORA = Path(__file__).resolve().parent / "corpora"
sys.path.insert(0, str(REPO / "skills" / "_shared"))
try:
    import model_roster as _mr  # type: ignore
except Exception:
    _mr = None

_PULSE_CAP = 24


def catalog() -> str:
    """The resident surface: name + description frontmatter of every skill."""
    rows = []
    for sk in sorted((REPO / "skills").iterdir()):
        f = sk / "SKILL.md"
        if not f.is_file():
            continue
        desc = ""
        for line in f.read_text(errors="replace").splitlines()[:30]:
            if line.startswith("description:"):
                desc = line.split(":", 1)[1].strip().strip('"')
                break
        if desc:
            rows.append(f"- {sk.name}: {desc}")
    return "\n".join(rows[:_PULSE_CAP * 2])


SUBJECT_TMPL = """You are a coding agent. You have this skill catalog (each loads full \
instructions when invoked):

{catalog}

For the USER PROMPT below decide which ONE skill (if any) you would invoke FIRST, \
before doing the work. Respond with exactly one line and nothing else:
SKILL: <name>   or   SKILL: none

USER PROMPT: {prompt}"""

_ANSWER_RE = re.compile(r"SKILL:\s*([A-Za-z0-9_-]+|none)", re.I)


def ask_ollama(prompt: str, model: str, timeout: float = 120.0) -> tuple[bool, str, str]:
    body = json.dumps({"model": model, "prompt": prompt, "stream": False,
                       "options": {"temperature": 0}}).encode()
    req = urllib.request.Request("http://localhost:11434/api/generate", data=body,
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8", "ignore"))
        return True, str(data.get("response", "")), ""
    except Exception as e:  # noqa: BLE001 - report, never raise
        return False, "", f"ollama: {e}"


def ollama_model() -> str:
    if os.environ.get("ADHERENCE_OLLAMA_MODEL"):
        return os.environ["ADHERENCE_OLLAMA_MODEL"]
    try:
        with urllib.request.urlopen("http://localhost:11434/api/tags", timeout=5) as r:
            tags = [m["name"] for m in json.loads(r.read())["models"]]
        for pref in ("qwen", "llama", "gemma", "deepseek"):
            hit = sorted(t for t in tags if pref in t)
            if hit:
                return hit[-1]
        return tags[0] if tags else ""
    except Exception:  # noqa: BLE001
        return ""


def ask(backend: str, prompt: str) -> tuple[bool, str, str]:
    if backend == "glm":
        if _mr is None:
            return False, "", "model_roster import failed"
        return _mr._run_glm(prompt, timeout=90.0)
    if backend == "ollama":
        m = ollama_model()
        if not m:
            return False, "", "no ollama model resolvable"
        return ask_ollama(prompt, m)
    return False, "", f"unknown backend {backend}"


def parse_answer(text: str) -> str:
    m = _ANSWER_RE.search(text or "")
    return (m.group(1).lower() if m else "unparsed")


def probe_regexes(skill: str) -> list[re.Pattern] | None:
    f = REPO / "skills" / skill / "drift_probes.json"
    if not f.is_file():
        return None
    pats = [p["pattern"] for p in json.loads(f.read_text())
            if p.get("kind") == "prompt_intent"]
    return [re.compile(p) for p in pats] if pats else None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--backend", action="append", default=[],
                    help="subject backend(s): ollama, glm (repeatable)")
    ap.add_argument("--mode", choices=["model", "probe", "both"], default="both")
    ap.add_argument("--skill", action="append", default=[],
                    help="limit to specific corpus skill(s)")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()
    backends = args.backend or ["ollama"]

    cases = []
    for f in sorted(CORPORA.glob("*.jsonl")):
        skill = f.stem
        if args.skill and skill not in args.skill:
            continue
        for line in f.read_text().splitlines():
            if line.strip():
                c = json.loads(line)
                c["skill"] = skill
                cases.append(c)
    if not cases:
        print("no corpus cases found", file=sys.stderr)
        return 2

    cat = catalog()
    results = []

    if args.mode in ("probe", "both"):
        for c in cases:
            rx = probe_regexes(c["skill"])
            if rx is None:
                verdict = "NO-PROBE"
            else:
                fired = any(r.search(c["prompt"]) for r in rx)
                want = c["expect"] == "fire"
                verdict = "PASS" if fired == want else "FAIL"
            results.append({"path": "probe", "backend": "-", **c, "answer": "-",
                            "verdict": verdict})

    if args.mode in ("model", "both"):
        for backend in backends:
            ok, _, err = ask(backend, "reply with: SKILL: none")
            if not ok:
                print(f"[skip] backend {backend} unreachable: {err}", file=sys.stderr)
                continue
            for c in cases:
                ok, text, err = ask(backend, SUBJECT_TMPL.format(catalog=cat,
                                                                 prompt=c["prompt"]))
                answer = parse_answer(text) if ok else f"error:{err[:40]}"
                if not ok:
                    verdict = "ERROR"
                elif c["expect"] == "fire":
                    verdict = "PASS" if answer == c["skill"] else "FAIL"
                else:
                    verdict = "PASS" if answer != c["skill"] else "FAIL"
                results.append({"path": "model", "backend": backend, **c,
                                "answer": answer, "verdict": verdict})

    if args.json:
        print(json.dumps(results, indent=1))
        return 0

    # summary: per skill × path × backend
    def key(r):
        return (r["skill"], r["path"], r["backend"])
    agg: dict = {}
    for r in results:
        a = agg.setdefault(key(r), {"pass": 0, "fail": 0, "other": 0, "fails": []})
        if r["verdict"] == "PASS":
            a["pass"] += 1
        elif r["verdict"] == "FAIL":
            a["fail"] += 1
            a["fails"].append(f"{r['id']}→{r['answer']}")
        else:
            a["other"] += 1
    print(f"{'skill':<26}{'path':<7}{'backend':<9}{'pass':>5}{'fail':>5}{'n/a':>5}  failures")
    for (skill, path, backend), a in sorted(agg.items()):
        print(f"{skill:<26}{path:<7}{backend:<9}{a['pass']:>5}{a['fail']:>5}"
              f"{a['other']:>5}  {', '.join(a['fails'][:4])}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
