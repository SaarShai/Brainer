# Simulations & extended testing — write-gate · cache-lint

> **Note:** `memory-decay` was **cut at v1.6.0** — a verified no-op (retrieval ranking never read its decayed `confidence`; only lint did). Its simulation results below (throughput, closed-form correctness, bugs found) are retained as a historical record, not a live skill.

Extends the unit-test suite under each skill's `tools/test_*.py` with:

1. **Corpus calibration** — labeled adversarial corpus + the project's real wiki
2. **Fuzz battery** — malformed / huge / adversarial inputs (no crashes allowed)
3. **Scale + correctness** — N=10, 100, 1k, 10k pages; closed-form decay check; 52-week trajectory
4. **End-to-end integration** — candidate → write-gate → wiki → 52w decay → cache-lint
5. **Independent code review** (parallel sub-agent)
6. **External Claude Code projects** (parallel sub-agent)

Harnesses live in [`eval/sims/`](sims/). Raw outputs (`eval/sims/results/*.json`, cited as "Source" below) are **regenerated locally** by `python3 eval/sims/run_all.py` — not committed, since they carry per-run timing that would churn every suite run (see `.gitignore`).

## Headline numbers

| Dimension | Number | Source |
|---|---:|---|
| Unit tests total (3 skills) | **37 passing** (was 24) | `tools/test_*.py` |
| write-gate accuracy on labeled corpus | **100% (29/29)** | `eval/sims/results/write_gate_corpus.json` |
| write-gate precision · recall · F1 | 100% · 100% · 100% | same |
| write-gate real-wiki acceptance | 75% (172 pages) | same |
| cache-lint fuzz crashes | **0 / 19 cases** | `eval/sims/results/cache_lint_fuzz.json` |
| cache-lint DoS resistance | 7.4s → **0.09s** (80×) after per-rule cap | same |
| memory-decay throughput | **~57μs/page** (linear to 10k) | `eval/sims/results/memory_decay_scale.json` |
| memory-decay closed-form correctness | **4/4 pages match exp(-λd) exactly** | same |
| 52-week trajectory: unprotected | 0.85 → 0.37 (decays) | `eval/sims/results/integration_pipeline.json` |
| 52-week trajectory: protected | 0.85 → 0.85 (flat) | same |
| End-to-end integration | **6/6 gates · 4/4 trajectories · 0 cache-lint FAILs** | same |
| Independent code review findings | 3 critical + 5 high → **all fixed** | parallel sub-agent |
| External projects tested | **4 real Claude Code repos** | parallel sub-agent |

## What changed because of testing

Testing surfaced **9 real bugs** (3 critical, 6 high-severity) the original unit tests didn't catch. All fixed; all have regression tests:

### Critical (would silently break in production)

| Bug | Where | Symptom | Fix |
|---|---|---|---|
| **Quoted YAML scalars** broke `--apply` | `memory-decay/tools/decay.py:51` | `confidence: "0.8"` parsed correctly but rewrite returned None → exit 1, file unchanged | Tolerant regex + quote preservation |
| **CRLF / BOM frontmatter** silently skipped | same | Windows-authored or BOM-prefixed pages excluded entirely from decay | Frontmatter regex tolerant of `\r\n` + `BOM` |
| **Compound decay** on weekly cron | same | After 52 weekly runs, 0.9 → 0.01 (intended: 0.9 → 0.48) | `--apply` now bumps `verified:` to today so next run measures delta only |
| **Fallback YAML parser** corrupted nested dicts | both write-gate & memory-decay | No-PyYAML environment: list/dict values stringified, `set()` iterated char-by-char → protection class effectively disabled | Stderr-warn + skip nested keys (treat as default) |

### High

| Bug | Where | Symptom | Fix |
|---|---|---|---|
| **`entity_overlap` O(n²)** | `write-gate/tools/write_gate.py:134` | `list.count` per element → 7.4s on 20k tokens; trivial DoS | `Counter` (O(n)) |
| **Why-clause** matched inside code fences | same | `\`\`\`# because reasons\`\`\`` bypassed the central "reasonless decisions rejected" guarantee | Strip fenced blocks before why scan |
| **"since"** counted as causal | same | Temporal "since yesterday" → false-positive on reasonless decisions | Removed from `WHY_CLAUSES` |
| **Non-UTF-8 file** crashed CLI | same | Uncaught `UnicodeDecodeError` | `errors="replace"` |
| **cache-lint Rule 6** flagged reads as writes | `cache-lint/tools/cache_lint.py:214` | `grep CLAUDE.md` reported as FAIL | Require write-verb AND prefix-file on same site |
| **cache-lint discovery** too narrow | `cache-lint/tools/cache_lint.py:67` | Missed `**/hooks.json`, `.claude-plugin/*.json`, nested CLAUDE.md → 0 findings on real plugin projects | Added globs + `SKIP_DIRS` for `node_modules`/`.git`/etc |
| **cache-lint Rule 6** didn't follow scripts | same | `python3 scripts/foo.py` JSON had no prefix-file mention; check passed even when foo.py wrote CLAUDE.md | Open invoked scripts, scan for write+file patterns |
| **cache-lint regex DoS** | same | 5000 `$(date)` matches → 7.4s, no cap on findings | 5-per-(rule, file) cap + bisect for fence-position lookup |

### Medium

- cache-lint sizing thresholds (`<256`/`>8000`) drifted from documented (`<1K`/`>4K`). **Reconciled to docs.**
- memory-decay module-level lambda (`E731`). **Renamed to `def`.**
- memory-decay `protected_dirs` name-match could match nested files. Now requires the dir name to be at `rel.parts[0]` OR `rel.name == d`. Acceptable scope.

## Per-skill calibration

### write-gate

Labeled corpus: **29 hand-crafted cases** at `eval/sims/write_gate_corpus.py` covering:

- Decisions with/without why-clauses (5 pos + 4 neg)
- Facts: arch+code+numbers, concrete failure, pipeline description (5 pos)
- Facts: filler, speculation, trivial recap, meta only (5 neg)
- Adversarial: "decision words" without substance, "arch words" with speculation (2 neg)
- Adversarial: terse-but-concrete (2 pos)
- Edge cases: high-signal traps, low-signal traps (3)

Final: **100% accuracy, 100% precision, 100% recall.**

Real wiki corpus: 172 pages, 75% acceptance. The 25% rejection rate is mostly thin pages without why-clauses, which is the correct behavior — flagging existing content as quality-improvement candidates.

### cache-lint

Fuzz cases at `eval/sims/cache_lint_fuzz.py`: empty files, whitespace-only, BOM, CRLF, binary garbage, latin-1/CJK/RTL Unicode, 1MB files, malformed JSON, wrong-type hooks, deep hooks, 50 SKILL.md files, 5000 `$(date)` substrings, nested plugin layouts, node_modules exclusion, `$RANDOM` injection.

Results:
- 0 crashes / 19 cases
- All 7 explicit correctness checks pass
- DoS resistance: 7.4s → 0.09s after the per-(rule, file) cap
- Discovery skips `node_modules`, `.git`, `.venv`, etc.
- Recursive discovery finds nested plugin `hooks.json`

External validation by parallel sub-agent against 4 real Claude Code projects (`disler/claude-code-hooks-mastery`, `BayramAnnakov/claude-reflect`, `anthropics/claude-code-action`, `wshobson/agents`) drove the **discovery + Rule-6 script-following + sizing-threshold fixes.** Synthetic positive control confirmed the regex patterns are sound.

### memory-decay

Scale at `eval/sims/memory_decay_scale.py`:

| N pages | dry-run | apply | μs/page (dry) |
|---:|---:|---:|---:|
| 10 | 2 ms | 1 ms | 207 |
| 100 | 5 ms | 11 ms | 56 |
| 1,000 | 53 ms | 109 ms | 53 |
| 10,000 | 567 ms | 1,176 ms | 57 |

Per-page time converges to ~57μs above N=100 (small-N is fs-cache-bound). Per-page ratio across all sizes: **3.82×** — comfortably linear.

Correctness: **exact match** with closed-form `confidence × exp(-λ × days_idle)` on 4 pages over 2 years.

Trajectory (52 weekly passes, before the compound-decay fix → after):
- Unprotected fact: **0.9 → 0.01 → 0.40** (matches intended math after fix)
- Protected error (type): **0.9 → 0.9** unchanged
- Protected cited (`evidence_count=5`): **0.9 → 0.9** unchanged

## End-to-end integration

`eval/sims/integration_pipeline.py` runs the full happy path:

```
candidate text
    ↓ write-gate (score + why-check)
    ↓ if pass → wiki page (with frontmatter)
    ↓ 52 weekly memory-decay --apply runs
    ↓ cache-lint audit
verdicts on each phase
```

Verdict: **PASSED**.
- All 6 candidates routed correctly (3 pass, 2 reject, 1 protected pass)
- All 4 written pages behave as expected (protected stay at 0.85; unprotected decay to ~0.37)
- cache-lint reports 0 FAILs on the resulting project

## Anti-falsifications

- **If write-gate accuracy drops below 95% on the labeled corpus**, the marker lists or threshold need re-tuning. Current calibration is on a small (n=29) hand-crafted set — accuracy on a larger blind set is unmeasured.
- **If real wiki acceptance falls below 40%**, the gate is suppressing too much. Either lower threshold to 2.5 or expand markers.
- **If memory-decay per-page time grows non-linearly**, suspect a regression in protection-class detection (currently O(1) per page).
- **If cache-lint finds a FAIL on a project shown to be clean by hand-audit, file under false-positive** and tighten the matching regex or add another inline-typography exemption.
- **The script-following heuristic in Rule 6 is whole-file**: it produces TPs on the common cross-line pattern but can produce FPs if a file mentions CLAUDE.md *and* has an unrelated `.write_text()` call. Mitigation: the report cites the prefix-file line so a human can verify in seconds.

## Reproducing

```bash
# All unit tests
python3 skills/write-gate/tools/test_write_gate.py     # 11 tests
python3 skills/cache-lint/tools/test_cache_lint.py     # 14 tests
python3 skills/memory-decay/tools/test_decay.py        # 12 tests

# All simulations
python3 eval/sims/write_gate_corpus.py
python3 eval/sims/cache_lint_fuzz.py
python3 eval/sims/memory_decay_scale.py
python3 eval/sims/integration_pipeline.py
```

All four sims exit 0 on a clean run; non-zero exit indicates a calibration regression.
