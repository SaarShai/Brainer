#!/usr/bin/env python3
"""verify_artifact — make the verdict discipline MECHANICAL.

SKILL.md steps 1-5 (cold verification · rubric-at-start · per-criterion verdict ·
vision verification) are prose. This tool turns them into an enforced flow:

  - You write the RUBRIC FILE *at task start* — one checkable criterion per line,
    each naming the evidence token that would prove it. (rubric-at-start)
  - At done-time you pass the EVIDENCE: the actual tool-result lines you ran
    (a file, or stdin). The tool builds a per-criterion verdict table by
    matching each criterion's required token against those lines. (per-criterion)
  - A criterion with no backing evidence line is DONE? = NO — never assumed
    (the two-pass / hallucination-signature rule: a claim with no evidence is
    a refuted claim, not a pass).
  - `[vision]` criteria additionally require a screenshot / render reference in
    the evidence (a path ending .png/.jpg/.svg/.pdf… or a render: / screenshot:
    marker) — text-only checking of a visual artifact fails. (--vision)
  - Any NOT-DONE row -> exit 1, so a done-claim cannot ship past it.

It does NOT re-score quality 0-5 — that holistic LLM-judge already exists in
skills/eval-gate (eval_gate.py). This tool is the deterministic *evidence gate*
that runs first; for a criterion that genuinely needs semantic judgment, tag it
`[judge]` and the tool defers to eval_gate (imported read-only, no key needed
with --stub-score) instead of duplicating its scorer.

RUBRIC FILE format — blank lines and `#` comments ignored; one criterion / line:

    # marker      criterion text                       -> evidence the line needs
    [evidence: 7 passed] all unit tests pass
    [evidence: exit 0]   build is clean
    [vision]             chart renders without overlap
    [judge]              the summary reads coherently   (defers to eval_gate)

If a criterion has no explicit `[evidence: …]` token, the whole criterion text
is treated as the token to find in the evidence (loose, case-insensitive).
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

# Reuse eval-gate read-only for [judge] criteria — do NOT reimplement its scorer.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "eval-gate" / "tools"))

VISION_EXT = (".png", ".jpg", ".jpeg", ".gif", ".svg", ".pdf", ".webp", ".bmp", ".tiff")
VISION_MARKERS = ("screenshot", "render:", "rendered", "viewed image", "looked at")

_MARKER = re.compile(r"^\s*\[(?P<kind>evidence|vision|judge)(?::\s*(?P<token>.*?))?\]\s*(?P<text>.*)$",
                     re.IGNORECASE)


def parse_rubric(text: str):
    """-> list of {kind, token, text}. kind in {evidence, vision, judge}."""
    crit = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        m = _MARKER.match(line)
        if m:
            kind = m.group("kind").lower()
            token = (m.group("token") or "").strip()
            ctext = m.group("text").strip()
            # bare [evidence]/[vision] with no token -> fall back to criterion text
            if kind in ("evidence", "vision") and not token:
                token = ctext
            crit.append({"kind": kind, "token": token, "text": ctext or token})
        else:
            # untagged line: treat the whole line as an evidence criterion
            crit.append({"kind": "evidence", "token": line, "text": line})
    return crit


def has_vision_evidence(evidence: str) -> bool:
    low = evidence.lower()
    if any(marker in low for marker in VISION_MARKERS):
        return True
    return any(ext in low for ext in VISION_EXT)


def find_token(token: str, evidence_lines) -> str | None:
    """Return the first evidence line containing token (case-insensitive), else None."""
    t = token.lower().strip()
    if not t:
        return None
    for ln in evidence_lines:
        if t in ln.lower():
            return ln.strip()
    return None


def judge_criterion(crit, evidence, backend, model, stub_score, threshold):
    """Defer a [judge] criterion to eval_gate's scorer. Returns (done, detail)."""
    try:
        import eval_gate
    except Exception as e:  # pragma: no cover - import guard
        return False, f"eval_gate unavailable: {e}"
    try:
        res = eval_gate.run_judge(crit["text"], evidence, eval_gate.DEFAULT_RUBRIC,
                                  backend, model, stub_score)
    except Exception as e:
        return False, f"judge unreachable: {e}"
    score = res.get("score")
    if score is None:
        return False, "judge returned no parseable score"
    norm = score / 5.0
    return norm >= threshold, f"eval_gate score {score}/5 (>= {threshold * 5:.0f} ? )"


def verify(rubric_text, evidence_text, vision_mode, backend, model, stub_score, threshold):
    criteria = parse_rubric(rubric_text)
    if not criteria:
        return {"error": "rubric has no criteria"}, 2
    evidence_lines = [ln for ln in evidence_text.splitlines() if ln.strip()]
    rows = []
    all_done = True
    for c in criteria:
        kind = c["kind"]
        # --vision flag promotes EVERY criterion to require visual evidence too
        # (artifact-level signal that the whole output is visual).
        treat_vision = kind == "vision" or (vision_mode and kind != "judge")
        if kind == "judge":
            done, detail = judge_criterion(c, evidence_text, backend, model, stub_score, threshold)
            ev = detail if done else None
        else:
            ev = find_token(c["token"], evidence_lines)
            done = ev is not None
            detail = ev or f"no evidence line matched token: {c['token']!r}"
            if done and treat_vision and not has_vision_evidence(evidence_text):
                # visual criterion: backing line exists but no screenshot/render ref
                done = False
                detail = ("text evidence found but NO screenshot/render reference — "
                          "a visual artifact must be looked at, not text-checked")
        rows.append({"criterion": c["text"], "kind": "vision" if treat_vision and kind != "judge" else kind,
                     "done": done, "evidence": detail})
        all_done = all_done and done
    return {"all_done": all_done, "n": len(rows),
            "n_done": sum(1 for r in rows if r["done"]), "criteria": rows}, (0 if all_done else 1)


def render_table(report) -> str:
    lines = ["criterion                                          | kind     | DONE? | evidence",
             "-" * 100]
    for r in report["criteria"]:
        mark = "YES" if r["done"] else "NO "
        lines.append(f"{r['criterion'][:50]:<50} | {r['kind']:<8} | {mark}   | {r['evidence'][:60]}")
    lines.append("-" * 100)
    lines.append(f"{report['n_done']}/{report['n']} criteria DONE — "
                 + ("ALL DONE" if report["all_done"] else "NOT DONE (gate blocks the done-claim)"))
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser(
        prog="verify_artifact.py",
        description="Mechanical per-criterion verdict gate for verify-before-completion.")
    ap.add_argument("--rubric", required=True, help="rubric file written AT TASK START (one criterion/line)")
    ap.add_argument("--evidence", help="file of tool-result lines (default: stdin)")
    ap.add_argument("--evidence-text", help="evidence inline (else --evidence / stdin)")
    ap.add_argument("--vision", action="store_true",
                    help="artifact is visual: every criterion also needs a screenshot/render reference")
    ap.add_argument("--json", action="store_true", help="emit JSON instead of the table")
    # [judge]-criterion plumbing, passed straight through to eval_gate
    ap.add_argument("--backend", default="ollama", choices=["ollama", "mimo"])
    ap.add_argument("--model", default="qwen2.5:7b-instruct")
    ap.add_argument("--stub-score", type=int, default=None, help="force eval_gate score (testing/CI)")
    ap.add_argument("--threshold", type=float, default=0.7)
    args = ap.parse_args()

    rubric_text = Path(args.rubric).read_text(encoding="utf-8")
    if args.evidence_text is not None:
        evidence_text = args.evidence_text
    elif args.evidence:
        evidence_text = Path(args.evidence).read_text(encoding="utf-8")
    else:
        evidence_text = sys.stdin.read()

    report, code = verify(rubric_text, evidence_text, args.vision,
                          args.backend, args.model, args.stub_score, args.threshold)
    if "error" in report:
        print(f"verify_artifact: {report['error']}", file=sys.stderr)
        return 2
    print(json.dumps(report, indent=2) if args.json else render_table(report))
    return code


if __name__ == "__main__":
    sys.exit(main())
