#!/usr/bin/env python3
"""Test the coherence_drift_meter: it must count REAL goal/constraint corrections,
ignore style nits + normal follow-ups, and NOT be fooled by the canary's own
hook-injected '<system-reminder>... the user corrected you ...' text."""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import coherence_drift_meter as m  # noqa: E402

fails = []


def check(name, ok, detail=""):
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f" :: {detail}" if not ok else ""))
    if not ok:
        fails.append(name)


def u(text):
    return {"type": "user", "message": {"role": "user", "content": text}}


def a(text):
    return {"type": "assistant", "message": {"role": "assistant", "content": [{"type": "text", "text": text}]}}


RECORDS = [
    u("that's not what I asked for"),                          # goal (1)
    u("I said don't touch the config file"),                   # constraint (1)
    u("make it shorter and more terse"),                       # style nit -> NOT counted
    u("now add tests for the new function"),                   # normal follow-up -> NOT counted
    # canary's own reminder text embedded in a user turn — MUST be stripped:
    u("ok\n<system-reminder>wiki-memory [user_correction]: the user corrected you. "
      "that's not what i asked — act on the correction.</system-reminder>"),  # -> NOT counted
    {"type": "user", "message": {"role": "user",
        "content": [{"type": "tool_result", "tool_use_id": "x", "content": "ok"}]}},  # tool result -> NOT counted
    a("Stepping back — the goal is the adoption review, not a rewrite."),       # self_correction (1)
    a("Here is the diff."),                                                      # neutral -> NOT counted
]


def write_session(records):
    d = tempfile.mkdtemp()
    p = Path(d) / "seed12345.jsonl"
    p.write_text("\n".join(json.dumps(r) for r in records), encoding="utf-8")
    return p


print("== seeded transcript: precision + reminder-stripping ==")
res = m.scan_session(write_session(RECORDS))
check("goal_correction counted (1)", res["goal_correction"] == 1, f"got {res['goal_correction']}")
check("constraint_reassert counted (1)", res["constraint_reassert"] == 1, f"got {res['constraint_reassert']}")
check("incidents == 2 (style nit + follow-up excluded)", res["incidents"] == 2, f"got {res['incidents']}")
check("self_correction counted (1)", res["self_correction"] == 1, f"got {res['self_correction']}")
check("system-reminder correction text NOT miscounted",
      res["incidents"] == 2,
      "the embedded '<system-reminder>... the user corrected you' must be stripped before matching")

print("== empty / no-drift session -> verdict stack-holds ==")
clean = [u("please refactor module X"), a("done"), u("looks good, thanks")]
res2 = m.scan_session(write_session(clean))
check("clean session: 0 incidents", res2["incidents"] == 0, f"got {res2['incidents']}")

print("== CLI runs + exits 0 (report, never a gate) ==")
import subprocess  # noqa: E402
seed = write_session(RECORDS)
proc = subprocess.run([sys.executable, str(Path(__file__).resolve().parent / "coherence_drift_meter.py"),
                       str(seed), "--json"], capture_output=True, text=True)
check("CLI exit 0", proc.returncode == 0, f"rc={proc.returncode} err={proc.stderr[:200]}")
try:
    out = json.loads(proc.stdout)
    check("CLI json has summary.verdict", "verdict" in out.get("summary", {}), proc.stdout[:200])
    check("avg over 1 drifty session triggers anchor-may-pay-off", out["summary"]["verdict"] == "anchor-may-pay-off",
          f"avg={out['summary']['avg_incidents_per_session']}")
except (ValueError, KeyError) as e:
    check("CLI json parses", False, str(e))

print()
if fails:
    print(f"test_coherence_drift_meter: {len(fails)} FAILED: {fails}")
    sys.exit(1)
print("test_coherence_drift_meter: ALL PASS")
