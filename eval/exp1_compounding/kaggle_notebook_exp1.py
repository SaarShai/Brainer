#!/usr/bin/env python3
"""Kaggle T4 driver for exp1_compounding — compounding-memory A/B on local Ollama.

Reuses the hardened helpers from eval/kaggle_ollama/kaggle_notebook_ollama.py
(_find_input_root, install_ollama, serve_ollama, pull, warmup) rather than
re-deriving them. The eval code under test is read from a Kaggle *Dataset* mounted
at /kaggle/input/<slug>/ (the working tree), and all generation runs against a
local Ollama server on the T4 GPU. No external API.

What it runs:
  python3 eval/exp1_compounding/run_compounding.py
      --backend ollama --model qwen2.5:7b-instruct
      --arms cold,memory,poisoned
  over the 12-task sequential corpus (eval/exp1_compounding/tasks.yaml).

Output: /kaggle/working/eval-results/exp1-summary.json (auto-attached for download).

Kernel config (kernel-metadata.json in this dir):
  enable_gpu: true, enable_internet: true (ollama install + model pull need net)
  dataset_sources: ["saarshai/brainer-eval-consolidated"]
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

GEN_MODEL = "qwen2.5:7b-instruct"
OUT_DIR = Path("/kaggle/working/eval-results")


def _import_harness(root: Path):
    """Import the hardened ollama helpers from the mounted dataset tree."""
    harness = root / "eval" / "kaggle_ollama"
    if str(harness) not in sys.path:
        sys.path.insert(0, str(harness))
    import kaggle_notebook_ollama as h  # noqa: E402
    return h


def main() -> int:
    t_start = time.time()
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    # Bootstrap: find the dataset root, then reuse the harness helpers verbatim.
    # _find_input_root lives in the harness module, but we need the root to FIND
    # the module — so do a minimal local copy of its primary path first.
    base = Path("/kaggle/input")
    root = None
    if base.exists():
        hits = list(base.rglob("eval/runner.py"))
        if hits:
            root = hits[0].parents[1]
    if root is None:
        # local dry-run fallback: repo two levels up from this file
        root = Path(__file__).resolve().parents[2]
    print("input root:", root, flush=True)

    h = _import_harness(root)
    # Prefer the harness's robust resolver (handles zip mounts) now that it's importable.
    try:
        root = h._find_input_root()
    except Exception as e:  # noqa: BLE001
        print(f"_find_input_root fallback ({e}); using {root}", flush=True)

    eval_dir = root / "eval"
    exp_dir = eval_dir / "exp1_compounding"
    runner = exp_dir / "run_compounding.py"
    print("exp dir:", exp_dir, "exists:", exp_dir.exists(), flush=True)
    print("skills dir exists:", (root / "skills").exists(), flush=True)
    print("runner exists:", runner.exists(), flush=True)

    PY = sys.executable
    h.run([PY, "-m", "pip", "install", "--quiet", "PyYAML"])

    h.install_ollama()
    proc = h.serve_ollama()
    try:
        h.pull(GEN_MODEL)
        h.warmup(GEN_MODEL)

        out_json = OUT_DIR / "exp1-summary.json"
        h.run_step("run_compounding.py (cold,memory,poisoned)", [
            PY, str(runner),
            "--backend", "ollama",
            "--model", GEN_MODEL,
            "--arms", "cold,memory,poisoned",
            "--out", str(out_json),
        ])
    finally:
        proc.terminate()

    # Echo the summary so it lands in the notebook log too.
    out_json = OUT_DIR / "exp1-summary.json"
    if out_json.exists():
        summary = json.loads(out_json.read_text())
        summary.setdefault("_meta", {})
        summary["_meta"].update({
            "gen_model": GEN_MODEL,
            "backend": "ollama",
            "wall_seconds": round(time.time() - t_start, 1),
            "input_root": str(root),
        })
        out_json.write_text(json.dumps(summary, indent=2))
        print("\n=== exp1 summary ===", flush=True)
        print(json.dumps(summary.get("verdict", {}), indent=2), flush=True)
        for arm, d in summary.get("per_arm", {}).items():
            print(f"  {arm}: total_acc={d['accuracy_total']} "
                  f"dep_acc={d['accuracy_dependent']} curve={d['success_curve']}", flush=True)
    else:
        print("WARN: exp1-summary.json not produced", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
