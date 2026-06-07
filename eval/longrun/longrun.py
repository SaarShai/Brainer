#!/usr/bin/env python3
"""Long-running cross-model replication driver (token-economy).

Built to run for HOURS on a single node against its LOCAL ollama, accumulating
repeated trials of the model-backed experiments so we get variance (reliability),
token cost (efficiency), and accuracy/adherence (quality) over a long window —
on a model FAMILY distinct from the original qwen2.5 runs.

Per rep it subprocesses:
  - exp9_drift     (skill-pulse / compliance-canary anti-drift, 4 arms)
  - exp1_compounding (wiki-memory cold vs memory vs poisoned, 3 arms)
and appends one JSON line (with both verdicts + wall-time) to
results/longrun_<node>.jsonl. Loops until --hours elapses. Robust: a failed
rep is logged and the loop continues.

Usage (on the node):
  nohup python3 eval/longrun/longrun.py --model gemma2:9b --node M2 --hours 6 \
        > eval/longrun/results/longrun_M2.log 2>&1 &
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
RESULTS = HERE / "results"


def now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def run_one(cmd: list[str], timeout: int) -> dict:
    t = time.time()
    try:
        p = subprocess.run(cmd, cwd=str(REPO), capture_output=True, text=True, timeout=timeout)
        return {"ok": p.returncode == 0, "secs": round(time.time() - t, 1),
                "rc": p.returncode, "stderr_tail": p.stderr[-400:] if p.returncode else ""}
    except subprocess.TimeoutExpired:
        return {"ok": False, "secs": round(time.time() - t, 1), "rc": "timeout"}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "secs": round(time.time() - t, 1), "rc": f"exc:{e}"}


def load_verdict(path: Path) -> dict | None:
    try:
        return json.loads(path.read_text()).get("verdict")
    except Exception:  # noqa: BLE001
        return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True)
    ap.add_argument("--node", required=True)
    ap.add_argument("--hours", type=float, default=6.0)
    ap.add_argument("--exps", default="drift,compound")
    ap.add_argument("--per-exp-timeout", type=int, default=5400)  # 90 min hard cap / exp
    args = ap.parse_args()

    RESULTS.mkdir(parents=True, exist_ok=True)
    master = RESULTS / f"longrun_{args.node}.jsonl"
    exps = [e.strip() for e in args.exps.split(",") if e.strip()]
    start = time.time()
    deadline = start + args.hours * 3600
    print(f"longrun node={args.node} model={args.model} hours={args.hours} exps={exps} start={now()}", flush=True)

    rep = 0
    while time.time() < deadline:
        rep += 1
        rec: dict = {"rep": rep, "node": args.node, "model": args.model, "started": now()}

        if "drift" in exps:
            so = RESULTS / f"drift_{args.node}_r{rep}.json"
            rec["drift"] = run_one([sys.executable, "eval/exp9_drift/run_drift.py",
                                    "--model", args.model, "--out", str(so)], args.per_exp_timeout)
            rec["drift_verdict"] = load_verdict(so) if rec["drift"]["ok"] else None

        if "compound" in exps:
            so = RESULTS / f"compound_{args.node}_r{rep}.json"
            rec["compound"] = run_one([sys.executable, "eval/exp1_compounding/run_compounding.py",
                                       "--model", args.model, "--out", str(so)], args.per_exp_timeout)
            rec["compound_verdict"] = load_verdict(so) if rec["compound"]["ok"] else None

        rec["finished"] = now()
        with master.open("a") as f:
            f.write(json.dumps(rec) + "\n")
        elapsed_min = round((time.time() - start) / 60)
        dv = rec.get("drift_verdict") or {}
        cv = rec.get("compound_verdict") or {}
        print(f"[rep {rep} +{elapsed_min}min] "
              f"drift_ok={rec.get('drift', {}).get('ok')} canary_uplift={dv.get('canary_uplift')} "
              f"compound_ok={rec.get('compound', {}).get('ok')} lift={cv.get('dependent_acc_lift')}", flush=True)

    print(f"DONE node={args.node} reps={rep} elapsed_min={round((time.time()-start)/60)} end={now()}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
