#!/usr/bin/env python3
"""Deterministic P/R gate for standing-orders' two prompt_intent probes.

Invokes the REAL compliance-canary hook (not a regex re-implementation) the
same way eval/behavior/e1_probe_pr.py does: a fresh temp transcript + a fresh
session id per case, COMPLIANCE_CANARY_SKILLS_ROOT pointed at this repo's
skills/, and a fire is detected by the unique message-signature substring
"[standing-orders] ORCH" / "[standing-orders] DEEP" appearing in the hook's
stdout (that text is embedded verbatim in each probe's `message` field in
drift_probes.json, so a substring match is unambiguous and immune to the
"- <skill> [<kind>]: " prefix format.py prepends).

Corpus: tools/corpus_tuning.jsonl (committed fixture — a copy of the
orchestrator-supplied tuning corpus; the live scratchpad path is
session-transient and not available to a fresh test run). If
tools/corpus_holdout.jsonl exists next to it (delivered by a separate lane),
it is evaluated too under the SAME floors; its absence is not a failure. The
holdout corpus is deliberately adversarial — vocabulary disjoint from the
tuning set, plus "no subagents" / "don't" / "keep going" red herrings on
known-bad (should-NOT-fire) rows — so a pattern that merely memorizes the
tuning corpus's own wording gets caught here.

`known_bad_prompt_regression()` below pins one specific known-bad case
directly (independent of either corpus file, so it survives a corpus edit
that accidentally drops the row it exercises).

Floors (per row label):
  ORCH recall >= 0.85 over expect in {orchestrate, both}
  DEEP recall >= 0.85 over expect in {deep, both}
  zero fires (either probe) on expect == none
  each probe fires at most once per prompt (hook contract; asserted directly)

Run:
  python3 skills/standing-orders/tools/test_standing_orders.py
  python3 skills/standing-orders/tools/test_standing_orders.py -v   # print misses/FPs
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
SKILLS = REPO / "skills"
HOOK = SKILLS / "compliance-canary" / "tools" / "hook.py"
HERE = Path(__file__).resolve().parent

ORCH_SIG = "[standing-orders] ORCH"
DEEP_SIG = "[standing-orders] DEEP"

ORCH_FLOOR = 0.85
DEEP_FLOOR = 0.85


def load_corpus(path: Path) -> list[dict]:
    rows = []
    if not path.exists():
        return rows
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        rows.append(json.loads(line))
    return rows


def run_hook(prompt: str, sid: str) -> str:
    """Invoke the real compliance-canary hook on one prompt, fresh session,
    fresh state dir — mirrors eval/behavior/e1_probe_pr.py's `fire()`."""
    with tempfile.TemporaryDirectory() as td:
        tx = Path(td) / "t.jsonl"
        # A minimal assistant turn so the hook has a non-empty transcript to
        # read; prompt_intent only inspects `prompt`, not this text.
        tx.write_text(
            json.dumps(
                {
                    "type": "assistant",
                    "message": {"role": "assistant", "content": [{"type": "text", "text": "ok"}]},
                }
            )
            + "\n"
        )
        payload = json.dumps(
            {"session_id": sid, "transcript_path": str(tx), "prompt": prompt}
        )
        env = {
            **os.environ,
            "COMPLIANCE_CANARY_STATE_DIR": str(Path(td) / "st"),
            "COMPLIANCE_CANARY_SKILLS_ROOT": str(SKILLS),
            "COMPLIANCE_CANARY_PULSE_EVERY": "0",
        }
        r = subprocess.run(
            [sys.executable, str(HOOK)],
            input=payload,
            capture_output=True,
            text=True,
            env=env,
            timeout=30,
        )
        return r.stdout


def evaluate(rows: list[dict], label: str, verbose: bool) -> bool:
    """Returns True iff this corpus clears all floors. Prints a P/R table."""
    if not rows:
        print(f"=== {label}: no rows (skipped) ===\n")
        return True

    tp_orch = fn_orch = tp_deep = fn_deep = 0
    none_fires = 0
    orch_misses: list[str] = []
    deep_misses: list[str] = []
    none_fp: list[str] = []
    double_fire: list[str] = []

    for i, row in enumerate(rows):
        prompt = row["prompt"]
        expect = row["expect"]
        out = run_hook(prompt, sid=f"{label}-{i}")

        orch_fired = ORCH_SIG in out
        deep_fired = DEEP_SIG in out
        # "at most once per prompt": the signature is a fixed literal string
        # inside one probe's `message`; more than one occurrence in stdout
        # would mean the same probe fired twice in one hook invocation.
        if out.count(ORCH_SIG) > 1 or out.count(DEEP_SIG) > 1:
            double_fire.append(prompt)

        if expect in ("orchestrate", "both"):
            if orch_fired:
                tp_orch += 1
            else:
                fn_orch += 1
                orch_misses.append(prompt)
        if expect in ("deep", "both"):
            if deep_fired:
                tp_deep += 1
            else:
                fn_deep += 1
                deep_misses.append(prompt)
        if expect == "none":
            if orch_fired or deep_fired:
                none_fires += 1
                none_fp.append(prompt)

    n_orch = sum(1 for r in rows if r["expect"] in ("orchestrate", "both"))
    n_deep = sum(1 for r in rows if r["expect"] in ("deep", "both"))
    n_none = sum(1 for r in rows if r["expect"] == "none")

    orch_recall = tp_orch / n_orch if n_orch else 1.0
    deep_recall = tp_deep / n_deep if n_deep else 1.0

    print(f"=== {label} ({len(rows)} prompts) ===")
    print(f"ORCH recall: {tp_orch}/{n_orch} = {orch_recall:.2%}  (floor {ORCH_FLOOR:.0%})")
    print(f"DEEP recall: {tp_deep}/{n_deep} = {deep_recall:.2%}  (floor {DEEP_FLOOR:.0%})")
    print(f"none false-fires: {none_fires}/{n_none}  (floor 0)")
    print(f"double-fires (same probe >1x in one prompt): {len(double_fire)}")

    if verbose:
        for m in orch_misses:
            print(f"    ORCH MISS: {m}")
        for m in deep_misses:
            print(f"    DEEP MISS: {m}")
        for m in none_fp:
            print(f"    NONE FALSE-FIRE: {m}")
        for m in double_fire:
            print(f"    DOUBLE-FIRE: {m}")
    print()

    ok = (
        orch_recall >= ORCH_FLOOR
        and deep_recall >= DEEP_FLOOR
        and none_fires == 0
        and not double_fire
    )
    return ok


def known_bad_prompt_regression() -> bool:
    """Pin a single known-bad (should-NOT-fire) prompt directly, independent
    of the corpus files: "keep going, add another test case for the plus
    operator" is a deliberate adversarial trap (bare 'keep going' must NOT be
    read as an ORCH decomposable-work signal — see SKILL.md's Honest
    limitations). Also pins one known-good case so a pattern that regressed
    to matching nothing wouldn't silently pass by failing to fire on both."""
    bad_prompt = "keep going, add another test case for the plus operator"
    good_prompt = "migrate the database from mongodb to postgres"

    out_bad = run_hook(bad_prompt, sid="known-bad-regression")
    out_good = run_hook(good_prompt, sid="known-good-regression")

    assert ORCH_SIG not in out_bad, f"REGRESSION: ORCH false-fired on known-bad prompt: {bad_prompt!r}"
    assert DEEP_SIG not in out_bad, f"REGRESSION: DEEP false-fired on known-bad prompt: {bad_prompt!r}"
    assert ORCH_SIG in out_good, f"REGRESSION: ORCH failed to fire on known-good prompt: {good_prompt!r}"
    return True


def main() -> int:
    verbose = "-v" in sys.argv

    if not HOOK.exists():
        print(f"FAIL: hook not found at {HOOK}")
        return 1

    known_bad_prompt_regression()

    tuning_path = HERE / "corpus_tuning.jsonl"
    holdout_path = HERE / "corpus_holdout.jsonl"

    tuning_rows = load_corpus(tuning_path)
    if not tuning_rows:
        print(f"FAIL: {tuning_path} missing or empty — the primary tuning corpus is required")
        return 1

    holdout_rows = load_corpus(holdout_path)

    print("standing-orders — real-hook P/R gate\n")
    ok_tuning = evaluate(tuning_rows, "tuning corpus", verbose)
    ok_holdout = True
    if holdout_rows:
        ok_holdout = evaluate(holdout_rows, "holdout corpus", verbose)
    else:
        print(f"(no holdout fixture at {holdout_path} — skipped, not a failure)\n")

    if ok_tuning and ok_holdout:
        print("PASS: all floors cleared.")
        return 0
    print("FAIL: one or more floors missed. Re-run with -v for misses/false-fires.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
