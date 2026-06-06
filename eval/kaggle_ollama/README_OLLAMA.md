# Kaggle T4 Ollama eval (N>=50) — consolidated branch

Runs the LLM-judged A/B eval at N>=50 on a free Kaggle T4 GPU using a **local
Ollama** server (no MiMo / Anthropic API key required), against the
**consolidated** code (branch `feat/wiki-compound-grafts`) shipped as a Kaggle
**Dataset** rather than a `git clone` of `main`.

## Why this exists
- `eval/kaggle_notebook.py` is MiMo-API-gated (`--backend mimo`) and there is no
  `MIMO_API_KEY` available — it cannot run.
- That notebook also clones `main`, but the code under test is uncommitted on
  `feat/wiki-compound-grafts`. So the eval tree is uploaded as a Dataset and read
  from `/kaggle/input/...` instead of cloned.

## Files
- `kaggle_notebook_ollama.py` — the kernel driver. Installs Ollama, serves it,
  pulls `qwen2.5:7b-instruct`, runs `runner.py --backend ollama --n 50` over the
  4 discipline tasks, runs `judge.py --backend ollama` for quality, runs the
  triage corpus via the Ollama port, writes `summary.json` +
  results to `/kaggle/working/eval-results/`.
- `runner_ollama_triage.py` — Ollama port of `eval/runner_triage.py` (which is
  MiMo-hardcoded and cannot run on Ollama). Reuses `classify.py` (regex
  fast-path) for routing; generates via Ollama.
- `build_dataset.sh` — stages the minimal dataset payload to `/tmp/te-kaggle-dataset`.
- `dataset-metadata.json` — Kaggle Dataset metadata (`saarshai/token-economy-eval-consolidated`).
- `kernel-metadata.json` — Kaggle kernel metadata (GPU + internet on, dataset attached).

## What the dataset must contain (and why)
`eval/runner.py` `load_skill_body()` reads `skills/<name>/SKILL.md` at runtime —
the task YAMLs do NOT inline skill bodies. So the dataset needs `skills/*/SKILL.md`,
not just `eval/`. `build_dataset.sh` includes all SKILL.md bodies plus
`skills/prompt-triage/tools/` (for `classify.py`), excluding all `.venv`,
`__pycache__`, `*.sqlite3`, `eval/results/`, `eval/sims/results/`, and `wiki/`.
Staged size: ~600 KB.

## BLOCKER (2026-06-06): write-scoped Kaggle auth returns 401
Read endpoints authenticate (`kaggle datasets list -m` returns "No datasets
found"; public search works; `config view` shows username `saarshai`). But every
WRITE endpoint returns `401 {"code":401,"message":"Unauthenticated"}`:
- `kaggle datasets create -p ... -r zip` -> begins upload, then
  `401 Client Error: Unauthorized for url: https://www.kaggle.com/api/v1/blobs/upload`
- direct probe of `/api/v1/datasets/status/...` -> `401 Unauthenticated`

The token (`~/.kaggle/kaggle.json`, user `saarshai`, 37-char key) is effectively
read-only. Most likely cause: the Kaggle account needs **phone verification**
before any dataset/kernel write, or the API token must be **regenerated** with
write scope (Account -> Settings -> API -> "Create New Token").

## Manual steps once write auth is fixed
```bash
export PATH="$HOME/.local/bin:$PATH"
# (CLI has no console script on this box; if `kaggle` isn't found, use:
#  alias kaggle='python3 -c "import sys;sys.argv=[\"kaggle\"]+sys.argv[1:];from kaggle.cli import main;main()"' )

# 1) stage + push the dataset
bash eval/kaggle_ollama/build_dataset.sh           # -> /tmp/te-kaggle-dataset
kaggle datasets create -p /tmp/te-kaggle-dataset -r zip
#   (for later updates: kaggle datasets version -p /tmp/te-kaggle-dataset -r zip -m "rerun")

# 2) push the kernel (metadata already attaches the dataset, GPU + internet on)
kaggle kernels push -p eval/kaggle_ollama

# 3) poll status
kaggle kernels status saarshai/token-economy-eval-ollama-t4

# 4) pull output when complete
kaggle kernels output saarshai/token-economy-eval-ollama-t4 -p eval/kaggle_ollama/output
```

If you prefer the web UI: create a Dataset from `/tmp/te-kaggle-dataset`, then a
new Notebook, paste `kaggle_notebook_ollama.py`, enable GPU T4 + Internet, attach
the dataset, and Run All.

## Model notes (single T4, 16 GB)
- `qwen2.5:7b-instruct` (~5 GB q4) is generator and judge by default.
- For judge independence, set `USE_SEPARATE_JUDGE=True` and
  `JUDGE_MODEL="gemma2:9b"` (~6 GB) in `kaggle_notebook_ollama.py` — both fit, but
  expect more swap/load churn.
- Triage savings on a single model are ~0 by construction (cheap==expensive);
  the meaningful triage signals there are classification accuracy + routing
  decisions. Pass two distinct local models to measure token savings.
