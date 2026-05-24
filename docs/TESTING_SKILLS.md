# Testing a skill — the rigorous pattern

The lesson from the v1.4.0 build: **unit tests are insufficient.** Three skills
shipped with passing unit tests; an independent reviewer + an external-project
agent + a simulation battery found 12 real bugs (3 critical, 6 high) that the
unit tests didn't catch.

Two of those bugs (compound decay over weekly cron, CRLF/BOM frontmatter
silently skipped) were design-level — they only manifest across multiple runs
or on files the author's OS doesn't produce. Unit tests literally couldn't
have caught them.

This doc is the standing protocol so the next skill doesn't repeat the
mistake.

## Five layers in increasing order of cost

| Layer | What it checks | Tool |
|---|---|---|
| 0. lint | SKILL.md schema | `scripts/lint_skill_md.py` |
| 1. unit | happy-path correctness | `tools/test_*.py` |
| 2. corpus / calibration | classifier accuracy on labeled set | `eval/sims/<skill>_corpus.py` |
| 3. fuzz | crash rate on malformed input | `eval/sims/<skill>_fuzz.py` |
| 4. scale | per-item time stays linear | `eval/sims/<skill>_scale.py` |
| 5. integration | composes with adjacent skills | `eval/sims/<skill>_pipeline.py` |
| 6. cold review | independent human/agent eyes | `scripts/test_skill.sh --emit-prompts` |
| 7. external validation | works on someone else's project | agent dispatched to clone + run real repos |

Not every skill needs every layer:
- **Prose-only skills** (caveman-ultra, lean-execution, plan-first-execute,
  verify-before-completion, index-first): layers 0 + the existing judge-scored
  eval. Skip 2-5.
- **Classifier skills** (write-gate, prompt-triage, compliance-canary): need
  layer 2 (calibration corpus) at minimum.
- **Parser / file-handling skills** (cache-lint, memory-decay, wiki-memory,
  context-keeper): need layer 3 (fuzz) at minimum.
- **Batch / scale-sensitive skills** (memory-decay, semantic-diff): need
  layer 4 (scale sweep).
- **Skills that change wiki / CLAUDE.md / persistent state**: need layer 5
  (integration with downstream readers).
- **Every skill**: layer 6 (cold review) before shipping a `v*.0.0`. Cheap to
  run, finds class-of-bug issues fresh eyes catch and authors don't.
- **Skills that audit external projects** (cache-lint): need layer 7.

## The one-command happy path

```bash
scripts/test_skill.sh <skill-name>
```

Runs lint → unit tests → matching sims, then prints reviewer-agent prompts
you can paste into a fresh agent session.

```bash
scripts/test_skill.sh <skill-name> --skip-sims      # quick check, lint + unit only
scripts/test_skill.sh <skill-name> --emit-prompts   # just the review prompts
```

For all sims at once (regression check after any change):

```bash
python3 eval/sims/run_all.py                    # all sims, prints summary
python3 eval/sims/run_all.py --skill write-gate # filter by skill
python3 eval/sims/run_all.py --only fuzz        # filter by shape
python3 eval/sims/run_all.py --json             # CI mode
```

## Building a new sim

Templates live in `eval/sims/`:

- `TEMPLATE_calibration.py` — for classifier-style skills (write-gate pattern)
- `TEMPLATE_fuzz.py` — for parser / file-handling skills (cache-lint pattern)
- (Scale + integration: model after `memory_decay_scale.py` and
  `integration_pipeline.py` directly — they don't need a template yet.)

Copy → rename to `eval/sims/<skill>_<shape>.py` → fill in the marked sections.

Shared utilities in `eval/sims/_lib.py`:

- `repo_root()`, `import_skill_module(skill, module)` — clean path-handling
- `Report`, `write_report()`, `print_report()` — consistent JSON + console output
- `calibration_metrics(rows)` — accuracy/precision/recall/F1 in one call
- `common_fuzz_payloads()` — 12 generally-evil inputs every file-handling sim
  should ride on (BOM, CRLF, binary garbage, 1MB, RTL, null bytes, etc)
- `assert_linear_scaling(times, threshold=5.0)` — sanity check for scale sims

## Dispatching reviewer agents

The pattern that worked best in v1.4.0: **two parallel cold-eyes agents per
skill**, each given a self-contained prompt with no access to this conversation.

The prompts emitted by `scripts/test_skill.sh --emit-prompts <skill>` are
self-contained and copy/pastable. Two reviewers per skill:

1. **Cold code review** — read the .py + tests, find what tests miss.
   Calibrated against the recurring bug shapes we keep finding in this codebase
   (quoted YAML, CRLF, fallback parsers, etc).
2. **External validation** — clone 2-3 real GitHub projects the skill
   plausibly applies to, run the CLI, judge each finding TP/FP/ambiguous.

Both dispatched as background `Agent` calls; aggregate findings into a fix
batch when both return.

## Specific bug classes to test for (calibrated against past findings)

A skill that handles files, YAML, or persistent state should explicitly test:

- [ ] **Quoted YAML scalars** — `confidence: "0.8"` parses but does a rewrite
      regex match it? (memory-decay had this)
- [ ] **CRLF line endings** — `\r\n` instead of `\n`. (memory-decay)
- [ ] **UTF-8 BOM prefix** — first three bytes `\xef\xbb\xbf`. (memory-decay)
- [ ] **Non-UTF-8 file content** — latin-1, binary garbage, mixed encodings.
      `Path.read_text()` raises `UnicodeDecodeError` without `errors=`. (write-gate)
- [ ] **PyYAML missing** — does the fallback corrupt nested values into strings,
      or skip them safely with a warning? (write-gate + memory-decay)
- [ ] **Markdown code fences and inline backticks** — does regex match dynamic-
      looking syntax inside them? (cache-lint, write-gate)
- [ ] **O(n²) on adversarial input** — `list.count` per element; per-match
      `text.splitlines()`. (write-gate, cache-lint)
- [ ] **Discovery globs** — does the skill find the standard nested plugin
      layout (`**/hooks.json`, `.claude-plugin/`, nested `CLAUDE.md`)? Does it
      skip `node_modules/`, `.git/`, `.venv/`? (cache-lint)
- [ ] **Read vs write distinction** — does a pattern that flags writes also
      flag reads? (cache-lint Rule 6)
- [ ] **Compounding effects** — does a hook / batch process compound between
      runs because it doesn't track its own previous-run state? (memory-decay's
      worst bug)

When you write a new sim, scan this list and write the tests that apply.

## Exit codes

All sims follow:
- `0` — passed
- `1` — at least one correctness check / accuracy target failed
- `2` — usage / discovery error

`scripts/test_skill.sh` exits with the worst exit code of any of its phases.
`run_all.py` exits 0 only if every sim returned 0.

## CI integration (when ready)

```yaml
- name: Skill regression
  run: python3 eval/sims/run_all.py --json > sims.json
- name: Upload sim results
  uses: actions/upload-artifact@v4
  with: { name: sim-results, path: sims.json }
```

Total runtime for the current 4 sims: ~4 seconds. Adding more sims should keep
the full sweep under 30 seconds — over that, split into a fast tier (unit +
lint) for pre-commit and a slow tier (sims) for CI.
