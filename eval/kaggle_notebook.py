#!/usr/bin/env python3
"""Kaggle notebook driver — runs the full A/B eval at N>=50 on free T4.

Upload to Kaggle as a notebook (NOT a script). Add the MIMO_API_KEY as a
Kaggle Secret (Settings → Add-ons → Secrets) so it is exposed to the kernel.

To submit via the kaggle CLI:
    kaggle kernels push --token <token>

Add `--enable-internet` and the `Add Secret: MIMO_API_KEY` step in the
notebook's metadata.

The output directory ends up under /kaggle/working/eval-results, which Kaggle
attaches to the notebook output for download.

Runners executed (covers every >=20% claim in eval/FINDINGS.md):
  - runner.py             on each task/combo YAML at N=50      (caveman, lean,
                                                                plan, verify,
                                                                triage corpus,
                                                                combos)
  - runner_compress.py    --max-samples 50                     (mechanical)
  - runner_compress_quality.py --n 50                          (SQuAD A/B
                                                                with MiMo
                                                                target+judge)
  - runner_wiki.py        --n 50                                (wiki-memory)
  - runner_triage.py      --corpus prompt-triage-corpus.yaml --n 50
  - runner_semdiff.py                                           (fixtures)
  - runner_filter.py                                            (fixtures)
  - runner_keeper.py      sample-transcript.jsonl               (fixture)
  - runner_handoff.py                                           (integration)
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


REPO_URL = "https://github.com/SaarShai/token-economy.git"
BRANCH = "main"

OUT_DIR = Path("/kaggle/working/eval-results")
OUT_DIR.mkdir(exist_ok=True)


def get_secret(name: str) -> str:
    try:
        from kaggle_secrets import UserSecretsClient
        return UserSecretsClient().get_secret(name)
    except Exception:
        v = os.environ.get(name)
        if not v:
            raise RuntimeError(f"missing secret {name}")
        return v


def run(cmd: list[str], cwd: str | None = None) -> str:
    return subprocess.check_output(cmd, cwd=cwd, text=True, stderr=subprocess.STDOUT)


def run_step(label: str, cmd: list[str]) -> None:
    print(f"\n=== {label} ===")
    print("  $", " ".join(cmd))
    try:
        out = run(cmd)
        # truncate to last ~40 lines so the notebook log stays readable
        tail = "\n".join(out.splitlines()[-40:])
        print(tail)
    except subprocess.CalledProcessError as e:
        print(f"FAILED {label}: {e.output[-2000:] if e.output else e}", file=sys.stderr)


def main() -> int:
    repo_dir = "/kaggle/working/token-economy"
    if not Path(repo_dir).exists():
        run(["git", "clone", "--depth", "1", "--branch", BRANCH, REPO_URL, repo_dir])
    print("repo at:", repo_dir)

    print("\n=== install deps ===")
    run([sys.executable, "-m", "pip", "install", "--quiet",
         "PyYAML", "datasets", "tiktoken"])

    os.environ["MIMO_API_KEY"] = get_secret("MIMO_API_KEY")
    print("MIMO_API_KEY loaded:", "yes" if os.environ.get("MIMO_API_KEY") else "no")

    PY = sys.executable
    N = "50"

    # 1) Generic A/B runner — covers caveman, lean, plan, verify, and combos.
    for t in sorted(Path(f"{repo_dir}/eval/tasks").glob("*.yaml")):
        # prompt-triage corpus is handled by runner_triage.py below; skip here.
        if "prompt-triage" in t.name:
            continue
        run_step(f"runner.py --task {t.name}", [
            PY, f"{repo_dir}/eval/runner.py",
            "--task", str(t),
            "--n", N, "--backend", "mimo", "--model", "mimo-v2-flash",
        ])
    for c in sorted(Path(f"{repo_dir}/eval/combos").glob("*.yaml")) \
             if Path(f"{repo_dir}/eval/combos").exists() else []:
        run_step(f"runner.py --combo {c.name}", [
            PY, f"{repo_dir}/eval/runner.py",
            "--combo", str(c),
            "--n", N, "--backend", "mimo", "--model", "mimo-v2-flash",
        ])

    # 2) Specialty runners — each measures a different surface.
    run_step("runner_compress.py mechanical (N=50)", [
        PY, f"{repo_dir}/eval/runner_compress.py",
        "--max-samples", N, "--rate", "0.5",
    ])
    run_step("runner_compress_quality.py SQuAD A/B (N=50, MiMo judge)", [
        PY, f"{repo_dir}/eval/runner_compress_quality.py",
        "--n", N, "--rate", "0.5",
        "--target", "mimo-v2-flash", "--judge", "mimo-v2-flash",
    ])
    run_step("runner_wiki.py (N=50)", [
        PY, f"{repo_dir}/eval/runner_wiki.py",
        "--n", N, "--model", "mimo-v2-flash",
    ])
    run_step("runner_triage.py corpus (N=50)", [
        PY, f"{repo_dir}/eval/runner_triage.py",
        "--corpus", f"{repo_dir}/eval/tasks/prompt-triage-corpus.yaml",
        "--cheap", "mimo-v2-flash", "--expensive", "mimo-v2.5-pro",
        "--n", N, "--no-ollama",
    ])
    run_step("runner_semdiff.py fixtures", [
        PY, f"{repo_dir}/eval/runner_semdiff.py",
    ])
    run_step("runner_filter.py fixtures", [
        PY, f"{repo_dir}/eval/runner_filter.py",
    ])
    run_step("runner_handoff.py integration", [
        PY, f"{repo_dir}/eval/runner_handoff.py",
    ])
    # keeper needs a transcript; try a couple of likely locations and skip if absent.
    for candidate in [
        f"{repo_dir}/.token-economy/checkpoints/sample.jsonl",
        f"{repo_dir}/eval/fixtures/transcript.jsonl",
    ]:
        if Path(candidate).exists():
            run_step(f"runner_keeper.py {candidate}", [
                PY, f"{repo_dir}/eval/runner_keeper.py", candidate,
            ])
            break
    else:
        print("\nskip runner_keeper.py — no transcript fixture available")

    # 3) Refresh static cost (cheap, deterministic).
    run_step("static_cost.py", [
        PY, f"{repo_dir}/eval/static_cost.py", "--json",
    ])

    # 4) Copy results out for download.
    src = Path(f"{repo_dir}/eval/results")
    for f in src.glob("*.json"):
        (OUT_DIR / f.name).write_bytes(f.read_bytes())

    # 5) One-line per-skill summary.
    summary: dict[str, dict] = {}
    for f in OUT_DIR.glob("*.json"):
        try:
            d = json.loads(f.read_text())
            key = d.get("task_id") or d.get("harness") or f.stem
            if "summary" in d:
                summary[key] = d["summary"]
            else:
                # Pull the high-level fields a few runners emit at top level.
                summary[key] = {
                    k: d[k] for k in (
                        "mean_savings_pct", "delta_score",
                        "mean_score_full", "mean_score_compressed",
                        "n_scored", "n_samples", "n_attempted",
                    ) if k in d
                }
        except Exception:
            pass
    (OUT_DIR / "summary.json").write_text(json.dumps(summary, indent=2))
    print("\n=== summary ===")
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
