# Running eval on Kaggle T4

Use Kaggle's free T4 (30h/week) to scale `eval/runner.py` from N=3 smoke to N≥50 production. The same `--backend mimo` is used; the only difference is sample size and the Kaggle wrapper.

## One-time setup

1. Have a Kaggle account; create a notebook (Code → New Notebook).
2. Add your MiMo key as a Kaggle Secret:
   - Notebook → Add-ons → Secrets → "Add a secret"
   - Label: `MIMO_API_KEY`
   - Value: your key (the one in `.brainer/secrets.env`)
3. Enable Internet access in the notebook settings.
4. Pick "GPU T4 x2" as accelerator (we don't use the GPU for MiMo, but it gets you better CPU/RAM too).

## Run

Copy the contents of `eval/kaggle_notebook.py` into the first notebook cell. Click "Save & Run All". The driver:

1. Clones this repo (current branch: `main`).
2. Installs `PyYAML`.
3. Reads `MIMO_API_KEY` from Kaggle Secrets.
4. Runs `eval/runner.py` for each task + combo at N=50 with `--backend mimo`.
5. Writes all `*.json` results to `/kaggle/working/eval-results/` (download from the notebook output panel).

Wall clock estimate: ~50 min per task at N=50 × 5 prompts × 2 conditions = 500 MiMo calls × ~5 s/call = ~42 min. 8 targets ≈ 5–6 hours; comfortably under the 9-hour Kaggle session limit.

## After

Download `eval-results/` from the notebook and copy back into `eval/results/`. Then re-run:

```bash
python3 eval/populate_eval_md.py     # refresh EVAL.md per skill with measured numbers
```
