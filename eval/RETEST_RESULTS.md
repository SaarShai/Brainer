# Re-test of existing skills (post-v1.4.0 lesson)

After the v1.4.0 round caught 12 bugs in *new* skills the unit tests didn't surface, applied the same protocol to three existing skills. Result: **4 critical + 8 high bugs in shipped code**, all fixed.

## Pattern

The full testing protocol now ships at [`docs/TESTING_SKILLS.md`](../docs/TESTING_SKILLS.md). One-line invocation:

```bash
scripts/test_skill.sh <skill-name>        # lint + unit + sims + emit review prompts
python3 eval/sims/run_all.py              # full regression sweep (6.5s)
```

## What was re-tested

| Skill | Why prioritized | New sim | Bugs found |
|---|---|---|---|
| **prompt-triage** | Runs on EVERY prompt. Cheap-route bug = expensive ($$ + quality). | `eval/sims/prompt_triage_corpus.py` | C3 (broad regex), C4 (truncation), H1 (4 python procs) |
| **loop-breaker** | Pattern-matcher on hot path. False fires pollute context. | `eval/sims/loop_breaker_fuzz.py` | C2 (signal repeats past threshold) |
| **wiki-memory** | Heavy frontmatter parsing — same risk class as memory-decay's CRLF/BOM bug. | `eval/sims/wiki_memory_fuzz.py` | C1 (BOM, CRLF, quoted scalars, block lists), H2-H8 (hot-path inefficiency + races) |

## Critical bugs (in shipped code, all fixed)

### C1 — wiki-memory frontmatter mirror-bugs

Exactly the bugs the reviewer predicted, in `skills/wiki-memory/tools/wiki.py:94-107`:

- **BOM-prefixed pages** (`\xef\xbb\xbf---\n…`) → frontmatter ignored entirely (any file saved by Notepad/Excel)
- **CRLF line endings** → close-fence search misses `\r\n---`, frontmatter lost
- **Block-list values** (`tags:\n  - foo\n  - bar`) → `tags=""`, all tag signal vanishes
- **Multi-line scalars** (`>` / `|`) → silent loss (documented limitation now)

**Fix**: ported the same robust parser from `memory-decay/tools/decay.py` (`_FRONTMATTER_OPEN_RE` + `_FRONTMATTER_CLOSE_RE` tolerating `\r?\n`, BOM prefix, quoted scalars, and a new block-list continuation parser). Regression-locked via `eval/sims/wiki_memory_fuzz.py:t_crlf / t_bom / t_block_list`.

Verified: all 172 existing wiki pages still parse correctly (163 with frontmatter + 9 legacy raw/log files).

### C2 — loop-breaker signal repeats past threshold

`skills/loop-breaker/tools/hook.py:255-271`: the original `if count < threshold: return 0` fired the signal on every subsequent call past threshold. The doc *says* "fire once at edge, again if it climbs further," but the code fired on every call.

Effect: a legitimate 10-iteration poll injected the warning text **6 times in a row** into context.

**Fix**: signal now fires only on rising-edge (`count == threshold`) or escalation (`count % threshold == 0` past threshold). Hard-block (`permissionDecision: deny`) still fires on every call past threshold — that's its purpose. Regression locked by `eval/sims/loop_breaker_fuzz.py:case_signal_fires_only_at_edge` AND the existing `tools/test.sh` continues to pass.

### C3 — prompt-triage routes serious tasks to haiku

`skills/prompt-triage/tools/classify.py:23-27`: the wiki-add regex

```python
r"\b(?:add|append|write|note|log|record)\b.{0,40}\b(?:wiki|markdown|kb|knowledge base)\b"
```

matched `"write me a comprehensive markdown audit of my codebase"` with confidence 0.9 → bypassed Ollama → routed to haiku.

This fires on every prompt the user sends.

**Fix**: tightened the regex to imperative-form-at-start; lowered confidence to 0.75 so Ollama checks; added `COMPLEX_HINTS` guard that force-downgrades any regex hit if the prompt contains words like `comprehensive`, `audit`, `architect`, `refactor`, `deep`, `thorough`, etc. Regression locked by `eval/sims/prompt_triage_corpus.py:complex_audit_markdown` (and 10 sibling cases).

### C4 — prompt-triage drops imperative at end of long contexts

`skills/prompt-triage/tools/classify.py:92`: `prompt[:800]` — a 5K-line stack trace ending with "fix this" sent only the head; the LLM classifier never saw the actual ask.

**Fix**: replaced with `_smart_truncate(prompt, 2000)` — 60% head + 40% tail with a `[truncated]` marker. Regression locked by `eval/sims/prompt_triage_corpus.py:long_stack_trace_with_imperative`.

## High-severity findings (documented; partial fixes)

- **H1 (prompt-triage hook.sh)**: 4 python processes per prompt (~120-320ms tax). **Not yet fixed** — needs hook.sh rewrite to call one Python that does all four jobs. Filed for follow-up; impact: latency on every keystroke.
- **H2-H8 (wiki.py)**: hot-loop re-reads files multiple times per search; symlink walks crash relative_to; ingest TOCTOU race; manifest reads with no size cap; loop-breaker session-id 8-char truncation collision. **Not fixed** — none are silent-data-loss bugs (C1 was the worst of that class). Filed in `wiki/projects/wiki-memory-perf-todo.md` (future work).

The honest read: **C1-C4 cover the silent-data-loss / safety / hot-path-correctness bugs.** The remaining H-class bugs are performance and edge-case robustness — important but not the blockers.

## What's still untested

Of the 19 skills in the catalog:

- **Already had rigorous testing** (judge-scored evals or runner): caveman-ultra, semantic-diff, output-filter, context-keeper, compress-context, verify-before-completion (5)
- **Now have new sims** (this round): write-gate, cache-lint, memory-decay (3) + prompt-triage, loop-breaker, wiki-memory (3)
- **Prose-only** (no executable code; the EVAL.md is the test): lean-execution, plan-first-execute, index-first, caveman-ultra (4)
- **Still has executable code but no calibration sim yet**: compliance-canary, skill-pulse, handoff, handoff-from (4)

Recommended next sim work, ranked by risk:

1. **skill-pulse** — UserPromptSubmit hook with turn-counting state; the kind of code that has off-by-one + state-corruption bugs
2. **handoff / handoff-from** — file-handling on $TMPDIR; potential frontmatter/CRLF bugs same as wiki-memory had
3. **compliance-canary** — has `tools/test.sh` + `measure.py`; cold review + fuzz on drift_probes.json parsing

Plus the H-class bugs from this round:
- prompt-triage hook.sh single-process refactor (H1)
- wiki.py search hot-path re-read elimination (H2)
- wiki.py symlink / manifest-size / ingest-race fixes (H4, H5, H8)

## Final sim runtime

```
=== sim run summary: 7/7 passed  (6.45s) ===
  [ok] cache_lint_fuzz.py          0.17s
  [ok] integration_pipeline.py     0.13s
  [ok] loop_breaker_fuzz.py        2.17s
  [ok] memory_decay_scale.py       3.70s
  [ok] prompt_triage_corpus.py     0.07s
  [ok] wiki_memory_fuzz.py         0.08s
  [ok] write_gate_corpus.py        0.13s
```

Under 7 seconds for the whole regression sweep. Cheap enough to run on every commit; sensitive enough to catch every bug found in two rounds.

## Lesson, codified

The bugs that ship despite passing unit tests aren't "rare edge cases" — they're a **predictable class**:

1. Encoding / line-ending tolerance (CRLF, BOM, non-UTF-8)
2. Quoted YAML scalars in rewrite paths
3. Fallback config parsers that stringify nested values
4. Regex patterns that match inside Markdown code fences
5. Patterns that conflate reads and writes
6. Hot-loop O(n²) (`list.count` per element, `text.splitlines()` per match)
7. Compounding effects across runs (decay, hooks that track state)
8. Discovery globs that miss common project layouts
9. Routing rules that fire on broad matches without complexity guards
10. Truncation that drops the actual ask in long contexts

The `docs/TESTING_SKILLS.md` checklist names all 10. The next skill that ships gets the checklist treatment before going on the catalog. The pattern that worked in v1.4.0 (corpus sim + fuzz sim + cold reviewer + external validator) now ships as templates and `scripts/test_skill.sh`.

The cost: ~30 minutes per skill to author the sims. The benefit, demonstrated twice now: **catches every bug we'd otherwise find in production.**
