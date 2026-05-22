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
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


REPO_URL = "https://github.com/SaarShai/token-economy.git"
BRANCH = "restructure/skill-catalog-v1"

OUT_DIR = Path("/kaggle/working/eval-results")
OUT_DIR.mkdir(exist_ok=True)


def get_secret(name: str) -> str:
    # Kaggle Secrets API
    try:
        from kaggle_secrets import UserSecretsClient
        return UserSecretsClient().get_secret(name)
    except Exception:
        # Fallback: environment variable
        v = os.environ.get(name)
        if not v:
            raise RuntimeError(f"missing secret {name}")
        return v


def run(cmd: list[str], cwd: str | None = None) -> str:
    return subprocess.check_output(cmd, cwd=cwd, text=True)


def main() -> int:
    # 1. Clone the repo
    repo_dir = "/kaggle/working/token-economy"
    if not Path(repo_dir).exists():
        run(["git", "clone", "--depth", "1", "--branch", BRANCH, REPO_URL, repo_dir])
    print("repo at:", repo_dir)

    # 2. Install runtime deps
    run([sys.executable, "-m", "pip", "install", "--quiet", "PyYAML"])

    # 3. Inject the MiMo key
    os.environ["MIMO_API_KEY"] = get_secret("MIMO_API_KEY")
    print("MIMO_API_KEY loaded:", "yes" if os.environ.get("MIMO_API_KEY") else "no")

    # 4. Iterate tasks + combos at N=50
    targets: list[tuple[str, str]] = []
    for t in sorted(Path(f"{repo_dir}/eval/tasks").glob("*.yaml")):
        targets.append(("--task", str(t)))
    for c in sorted(Path(f"{repo_dir}/eval/combos").glob("*.yaml")):
        targets.append(("--combo", str(c)))

    for flag, path in targets:
        print(f"running {flag} {path} ...")
        try:
            out = run([
                sys.executable, f"{repo_dir}/eval/runner.py",
                flag, path,
                "--n", "50",
                "--backend", "mimo",
                "--model", "mimo-v2-flash",
            ])
            print(out)
        except subprocess.CalledProcessError as e:
            print(f"FAILED on {path}: {e}", file=sys.stderr)

    # 5. Copy results into the notebook output dir
    src = Path(f"{repo_dir}/eval/results")
    for f in src.glob("*.json"):
        (OUT_DIR / f.name).write_bytes(f.read_bytes())

    # 6. Summarize
    summary = {}
    for f in OUT_DIR.glob("*.json"):
        try:
            d = json.loads(f.read_text())
            if "summary" in d:
                summary[d["task_id"]] = d["summary"]
        except Exception:
            pass
    (OUT_DIR / "summary.json").write_text(json.dumps(summary, indent=2))
    print("\n=== summary ===")
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
