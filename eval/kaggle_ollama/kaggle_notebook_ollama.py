#!/usr/bin/env python3
"""Kaggle T4 notebook driver — Ollama-backed A/B eval at N>=50, NO MiMo API.

Why this exists (vs eval/kaggle_notebook.py):
  - eval/kaggle_notebook.py is MiMo-API-gated (--backend mimo) and clones `main`
    from GitHub. We have NO MIMO_API_KEY, and the consolidated code under test is
    on an UNCOMMITTED/UNPUSHED branch (feat/wiki-compound-grafts). So we cannot
    use that notebook.
  - This driver instead: (1) reads the eval code from a Kaggle *Dataset* mounted at
    /kaggle/input/<DATASET_SLUG>/ (the working tree, not a git clone), and
    (2) runs everything against a local Ollama server on the T4 GPU.

What it runs (all generation + judging local, no external API):
  - runner.py  --backend ollama  on each eval/tasks/*.yaml discipline task
    (caveman-ultra, lean-execution, plan-first-execute, verify-before-completion)
    at --n 50. runner.py measures token deltas only.
  - judge.py   --backend ollama  on each result JSON to add LLM-judged quality
    scores (with vs without skill).
  - runner_ollama_triage.py (sibling file, Ollama port of runner_triage.py) on
    eval/tasks/prompt-triage-corpus.yaml at --n 50. The tracked runner_triage.py
    is MiMo-hardcoded and cannot run on Ollama, so we ship an Ollama port here
    rather than editing tracked repo files.

Model selection (single T4, 16GB):
  - GEN_MODEL  = qwen2.5:7b-instruct  (generator under A/B; ~5GB q4)
  - JUDGE_MODEL = qwen2.5:7b-instruct (same model judges; keeps VRAM low,
    avoids a second large load). gemma2:9b (~6GB) is a viable alt judge if you
    want judge independence and confirm both fit — see USE_SEPARATE_JUDGE below.

Setup as a Kaggle NOTEBOOK kernel (kernel-metadata.json in this dir):
  - enable_gpu: true, enable_internet: true (ollama install + model pull need net)
  - dataset_sources: ["saarshai/<DATASET_SLUG>"]
Outputs land in /kaggle/working/eval-results/ (auto-attached for download).
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
GEN_MODEL = "qwen2.5:7b-instruct"
JUDGE_MODEL = "qwen2.5:7b-instruct"
USE_SEPARATE_JUDGE = False  # set True + JUDGE_MODEL="gemma2:9b" for judge independence
N = "50"
OLLAMA_URL = "http://127.0.0.1:11434/api/generate"

OUT_DIR = Path("/kaggle/working/eval-results")
OUT_DIR.mkdir(parents=True, exist_ok=True)


def _find_input_root() -> Path:
    """Locate the mounted dataset tree that contains eval/runner.py.

    Robust to: arbitrary mount nesting (rglob, not a fixed 2-level walk), and to
    `-r zip` uploads that leave skills.zip / eval.zip unextracted (we extract any
    *.zip and retry). Prints the actual /kaggle/input tree so a mount quirk can't
    fail silently again.
    """
    import zipfile

    base = Path("/kaggle/input")
    if not base.exists():
        # local dry-run fallback: repo two levels up from this file
        here = Path(__file__).resolve()
        return here.parents[2]

    # diagnostic — what actually mounted (capped)
    print("=== /kaggle/input tree (first 100) ===", flush=True)
    for p in sorted(base.rglob("*"))[:100]:
        print("   ", p, flush=True)

    # 1) direct: eval/runner.py anywhere under the mount
    hits = list(base.rglob("eval/runner.py"))
    if hits:
        return hits[0].parents[1]

    # 2) payload may be zipped (-r zip) and not auto-extracted: extract + retry
    zips = list(base.rglob("*.zip"))
    if zips:
        dest = Path("/kaggle/working/staged")
        dest.mkdir(parents=True, exist_ok=True)
        for z in zips:
            try:
                with zipfile.ZipFile(z) as zf:
                    zf.extractall(dest)
                print(f"extracted {z} -> {dest}", flush=True)
            except Exception as e:  # noqa: BLE001
                print(f"extract failed {z}: {e}", flush=True)
        hits = list(dest.rglob("eval/runner.py"))
        if hits:
            root = hits[0].parents[1]
            # skills/ must be a sibling of eval/ (separate zips may land apart)
            if not (root / "skills").exists():
                sk = list(dest.rglob("skills/*/SKILL.md"))
                if sk:
                    skills_dir = sk[0].parents[1]  # .../skills
                    if skills_dir != root / "skills":
                        try:
                            (root / "skills").symlink_to(skills_dir)
                        except Exception:  # noqa: BLE001
                            import shutil
                            shutil.copytree(skills_dir, root / "skills")
            return root

    raise RuntimeError(
        f"could not find eval/runner.py under {base}; "
        f"contents={[p.name for p in base.iterdir()]}"
    )


def run(cmd: list[str], **kw) -> str:
    return subprocess.check_output(cmd, text=True, stderr=subprocess.STDOUT, **kw)


def run_step(label: str, cmd: list[str], env: dict | None = None) -> None:
    print(f"\n=== {label} ===", flush=True)
    print("  $", " ".join(cmd), flush=True)
    t0 = time.time()
    try:
        out = subprocess.check_output(cmd, text=True, stderr=subprocess.STDOUT, env=env)
        tail = "\n".join(out.splitlines()[-40:])
        print(tail, flush=True)
    except subprocess.CalledProcessError as e:
        print(f"FAILED {label}: {e.output[-2000:] if e.output else e}", file=sys.stderr, flush=True)
    print(f"  [{label} took {time.time()-t0:.0f}s]", flush=True)


def install_ollama() -> None:
    print("\n=== install ollama ===", flush=True)
    # Kaggle's base image lacks zstd, which ollama's installer needs to unpack
    # its bundle (it errors with "install zstd"). Install it first.
    subprocess.run(
        ["bash", "-c", "(apt-get update -y && apt-get install -y zstd) >/tmp/apt.log 2>&1 || true"],
    )
    r = subprocess.run(
        ["bash", "-c", "curl -fsSL https://ollama.com/install.sh | sh"],
        text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
    )
    print((r.stdout or "")[-1500:], flush=True)
    have = subprocess.run(["bash", "-c", "command -v ollama"], stdout=subprocess.DEVNULL).returncode == 0
    if not have:
        print("installer did not yield an ollama binary; direct-tarball fallback", flush=True)
        rc = subprocess.run(
            ["bash", "-c",
             "set -e; "
             "curl -fsSL https://ollama.com/download/ollama-linux-amd64.tgz -o /tmp/ol.tgz; "
             "mkdir -p /usr/local; tar -xzf /tmp/ol.tgz -C /usr/local; "
             "ln -sf /usr/local/bin/ollama /usr/bin/ollama; ollama --version"],
            text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        )
        print((rc.stdout or "")[-1500:], flush=True)
        if rc.returncode != 0:
            raise RuntimeError("ollama install failed (installer + direct tarball)")


def serve_ollama() -> subprocess.Popen:
    print("\n=== start ollama serve ===", flush=True)
    env = os.environ.copy()
    env.setdefault("OLLAMA_HOST", "127.0.0.1:11434")
    proc = subprocess.Popen(
        ["ollama", "serve"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=env,
    )
    # wait for the server to answer
    deadline = time.time() + 120
    while time.time() < deadline:
        try:
            with urllib.request.urlopen("http://127.0.0.1:11434/api/tags", timeout=3) as r:
                if r.status == 200:
                    print("  ollama serve up", flush=True)
                    return proc
        except Exception:
            time.sleep(2)
    raise RuntimeError("ollama serve did not become ready within 120s")


def pull(model: str) -> None:
    print(f"\n=== ollama pull {model} ===", flush=True)
    run(["ollama", "pull", model])
    print(f"  pulled {model}", flush=True)


def warmup(model: str) -> None:
    """First generate loads weights into VRAM; do it once so timings are clean."""
    body = json.dumps({"model": model, "prompt": "ok", "stream": False}).encode()
    req = urllib.request.Request(OLLAMA_URL, data=body, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=300) as resp:
            json.loads(resp.read())
        print(f"  warmed {model}", flush=True)
    except Exception as e:
        print(f"  warmup {model} failed (continuing): {e}", flush=True)


def main() -> int:
    t_start = time.time()
    root = _find_input_root()
    eval_dir = root / "eval"
    print("input root:", root, flush=True)
    print("eval dir:", eval_dir, "exists:", eval_dir.exists(), flush=True)
    print("skills dir exists:", (root / "skills").exists(), flush=True)

    PY = sys.executable
    run([PY, "-m", "pip", "install", "--quiet", "PyYAML"])

    install_ollama()
    proc = serve_ollama()
    try:
        pull(GEN_MODEL)
        if USE_SEPARATE_JUDGE and JUDGE_MODEL != GEN_MODEL:
            pull(JUDGE_MODEL)
        warmup(GEN_MODEL)

        # runner.py / judge.py compute repo_root as Path(__file__).parents[1],
        # i.e. <root>. load_skill_body reads <root>/skills/<name>/SKILL.md, so the
        # dataset MUST contain skills/. Confirmed by inspecting runner.py.

        # 1) Discipline tasks: A/B token deltas, then judge quality.
        task_dir = eval_dir / "tasks"
        for t in sorted(task_dir.glob("*.yaml")):
            if "prompt-triage" in t.name:
                continue  # handled by the ollama triage runner below
            out_json = OUT_DIR / f"{t.stem}.json"
            run_step(f"runner.py --task {t.name}", [
                PY, str(eval_dir / "runner.py"),
                "--task", str(t),
                "--n", N, "--backend", "ollama", "--model", GEN_MODEL,
                "--out", str(out_json),
            ])
            if out_json.exists():
                run_step(f"judge.py {out_json.name}", [
                    PY, str(eval_dir / "judge.py"), str(out_json),
                    "--backend", "ollama", "--model", JUDGE_MODEL,
                ])

        # 2) Prompt-triage corpus via the Ollama port (sibling file).
        triage_runner = Path(__file__).resolve().parent / "runner_ollama_triage.py"
        if not triage_runner.exists():
            # the dataset ships this file under eval/kaggle_ollama/
            cand = eval_dir / "kaggle_ollama" / "runner_ollama_triage.py"
            triage_runner = cand if cand.exists() else triage_runner
        corpus = task_dir / "prompt-triage-corpus.yaml"
        if triage_runner.exists() and corpus.exists():
            run_step("runner_ollama_triage.py corpus (N=50)", [
                PY, str(triage_runner),
                "--corpus", str(corpus),
                "--classify", str(root / "skills" / "prompt-triage" / "tools" / "classify.py"),
                "--cheap", GEN_MODEL, "--expensive", GEN_MODEL,
                "--n", N,
                "--out", str(OUT_DIR / "prompt-triage.json"),
            ])
        else:
            print(f"\nskip triage — runner={triage_runner.exists()} corpus={corpus.exists()}", flush=True)

    finally:
        proc.terminate()

    # 3) One-line per-result summary, plus judged scores when present.
    summary: dict[str, dict] = {}
    for f in sorted(OUT_DIR.glob("*.json")):
        if f.name == "summary.json":
            continue
        try:
            d = json.loads(f.read_text())
            key = d.get("task_id") or d.get("corpus") or f.stem
            entry = {}
            if "summary" in d:
                entry["summary"] = d["summary"]
            # judge.py writes a sibling <name>.judged.json
            judged = f.with_suffix(".judged.json")
            if judged.exists():
                try:
                    entry["judge_summary"] = json.loads(judged.read_text()).get("judge_summary")
                except Exception:
                    pass
            summary[key] = entry
        except Exception as e:
            summary[f.stem] = {"error": str(e)}

    summary["_meta"] = {
        "gen_model": GEN_MODEL,
        "judge_model": JUDGE_MODEL,
        "n": N,
        "backend": "ollama",
        "wall_seconds": round(time.time() - t_start, 1),
        "input_root": str(root),
    }
    (OUT_DIR / "summary.json").write_text(json.dumps(summary, indent=2))
    print("\n=== summary ===", flush=True)
    print(json.dumps(summary, indent=2), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
