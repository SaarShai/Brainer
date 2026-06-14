---
schema_version: 2
title: Recurring defect classes in the skills suite (grep-first bug checklist)
type: concept
domain: framework
tier: semantic
confidence: high
created: 2026-06-13
updated: 2026-06-14
verified: 2026-06-14
sources: [skills/compliance-canary/tools/hook.py, skills/wiki-memory/tools/wiki.py, skills/context-keeper/tools/extract.py, skills/cache-lint/tools/cache_lint.py, skills/write-gate/tools/write_gate.py, scripts/run_all_tests.sh]
evidence_count: 6
supersedes: []
superseded-by:
tags: [bugs, regex, frontmatter, installer, tests, perf, hardening]
---

# Recurring defect classes in the skills suite

Bug-hunt round 5 (2026-06-13, multi-agent: 13 finders → adversarial verify) found
**46 confirmed + reproduced** defects. They collapse into a handful of *recurring
classes* that recur across unrelated skills. Treat this as a grep-first checklist
when writing or reviewing any skill tool — each class shipped in 2–4 separate files.

## 1. Substring match where a word-boundary match was meant
A gate that matches keywords/markers with bare Python `in` (or an unanchored
regex) over-fires on substrings of unrelated words, silently defeating the gate.
- write-gate `WHY_CLAUSES`: `"due to" in "overdue tomorrow"` → reasonless decision passes the why-gate.
- compliance-canary `verify_keywords`: `"ls" in "results"`, `"cat" in "category"` → a done-claim's drift warning wrongly suppressed.
- lint_skill_md DEPRECATED exemption: `desc.upper().startswith("DEPRECATED")` exempts a real "Deprecated-API scanner" skill.
- **Rule:** marker/keyword matching that drives a gate **must** use `\b…\b` word boundaries, never bare `in`/unanchored. Build `re.compile(r"\b(" + "|".join(map(re.escape, words)) + r")\b")`.

## 2. Regex surgery on raw whole-document text instead of the frontmatter span
Editing/parsing `^trust:…` (or any frontmatter key) over the *entire* file with
`re.M` corrupts body lines, mis-handles quoted values, and breaks idempotency.
- wiki `consolidate --apply`: rewrote `trust: asserted` anywhere (body docs about the trust system), prepended duplicate keys on quoted `trust: "asserted"`, no-op'd no-frontmatter pages → perpetual re-promotion + unbounded growth.
- cache-lint Rule 2 fence parity counted *inline* ``` runs, flipping FAIL→WARN for the rest of the file.
- **Rule:** scope frontmatter edits to the leading `---…---` span (parse it, edit the dict, re-serialize, or regex only within the span). Handle quoted, unquoted, body-collision, and no-frontmatter shapes; assert idempotency on all four.

## 3. O(n²) / ReDoS from nested quantifiers + weak leading lookbehind
A path/segment regex like `[\w\-]+(?:/[\w\-]+)+\.(ext)` backtracks
super-linearly when it can *start* a match at every interior segment.
- context-keeper `PATH_RE`: a rewrite to catch bare relative paths hit **39 s** on a 50 k-segment slash run / 3.2 s on a 40 KB paste — enough to blow [[projects/context-keeper]]'s 30 s PreCompact subprocess timeout and lose the whole snapshot. It also leaked `https://…/foo.py` URL fragments into `files_touched`.
- cache-lint typography skip: moving an O(line) per-match check before the cap made `'$(date) '*5000` take 7 s (the fuzz battery's `dos_under_2s` case caught it).
- **Rule:** a *strong leading negative-lookbehind* (`(?<![\w\-./~])`) limits match starts to token boundaries → linear even with the segment group. For per-match work inside a loop, precompute spans once (O(n)) and test membership with `bisect` (O(log n)), mirroring `_inside_fence_fast`. **Benchmark every new path/segment regex on an adversarial slash-run before committing.** This file has a documented 23 s incident in its history — the lesson keeps re-applying.

## 4. A defect fixed in one vendored/duplicated copy, not propagated to siblings
- prompt-triage's installer already aborted on a corrupt `.claude/settings.json` (codex review 2026-06-12, "silently erases the user's other hooks/permissions"), but skill-pulse, compliance-canary, and context-keeper installers still carried the unfixed `except json.JSONDecodeError: data = {}` + unconditional overwrite — **critical data-loss** on a bare `./install.sh` against a corrupt file.
- **Rule:** when fixing a defect in one installer/hook/copy, `grep` every sibling for the same pattern and fix all — the same propagation discipline that applies across vendored repos applies across sibling skills.

## 5. Test-vacuity: a passing test that survives the mutation it claims to guard
Four distinct shapes, all of which let the bug back in silently:
- **membership-not-cardinality**: `("a","b",1.0) in result` passes with arbitrarily many spurious extras (semdiff rename test missed the many-to-many false-match).
- **zero-positive-signal fixture**: a speculation/filler penalty test whose text scores 0 even with the penalty disabled (penalty not load-bearing).
- **fixture trips an earlier gate**: the length-gate test's prompt hit context-guard first (`"we built"`), so disabling the length-gate still passed.
- **untested boundary**: `evidence_count=5` can't distinguish `>=3` from `>3`; the `==threshold` case was never asserted.
- **Rule:** every regression test must **mutation-fail** — reintroduce the bug and confirm the test goes red. Assert exact sets/cardinality, use load-bearing fixtures, and cover the boundary value.

## 6. The single verdict gate must run every deterministic suite
`scripts/run_all_tests.sh` ("exit code is the verdict") never invoked
`eval/sims/run_all.py`, `skills/skill-pulse/tools/test.sh`, or a new output-filter test — so two
sims sat **dead** (stale `skills/memory-decay/tools` import path after the
memory-decay→wiki-memory consolidation) and green for weeks, and a shipping hook's
24-assertion suite was outside CI.
- **Rule:** wire every offline/deterministic suite into the one gate the CI runs. An orphan test is invisible coverage that reads as "covered". (Now wired: sims + hook:skill-pulse + test_output_filter.)

## Meta-lesson: a fix can ship a worse bug than it fixes
Two "passing" fixes this round introduced regressions their *scoped unit tests*
did not catch: cache-lint typography→DoS (class 3) and PATH_RE→ReDoS+URL-leak
(class 3). Both were caught only by an **adversarial diff-review pass that explicitly
probed for perf/ReDoS and edge-case regressions** (and the wired-in fuzz battery).
Scoped green tests are necessary but not sufficient — review the diff adversarially,
and benchmark anything touching a hot-path regex. See [[concepts/framework-hardening-adoption]].
