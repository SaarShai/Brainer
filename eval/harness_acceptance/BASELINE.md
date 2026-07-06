# harness_acceptance — day-one baseline

Date: 2026-07-05 (original scaffold); revised 2026-07-06 after a cold-verifier
NEEDS-FIXES pass on 4 check defects (H3a false-PASS, H2a under-scoped
population, H1b token-gesture marker, H2b presence-not-enforcement — see
"Round 2 fixes" below). This is the honest FAIL baseline the acceptance suite
exists to certify — see SPEC.md's acceptance-test manifest for what each row
means and `.brainer/plans/10x-harness/SPEC.md` for the build loop this gates.

`python3 eval/harness_acceptance/run.py --report`, verbatim, post-fix:

```
id | axis | verdict | reason
---|---|---|---
H1a | token | FAIL | resident block 7990B vs budget 4794B (60% of 7990B baseline)
H1b | token | FAIL | 8 oversized without a real split: compliance-canary (15544B, no split-justified marker), eval-gate (13287B, no split-justified marker), learn-skill (12978B, no split-justified marker), loop-engineering (39161B, no split-justified marker), security-oversight (14234B, no split-justified marker), task-retrospective (17152B, no split-justified marker), wiki-memory (24614B, no split-justified marker), wiki-refresh (14436B, no split-justified marker)
H1c | token | FAIL | skills/=26; README.md=22; marketplace.json=26; SKILLS_INDEX.md=26
H2a | reliability | PASS | 21 default-on (auto-install != false) skills all have hook/probe/test/measured-evidence (or named exception)
H2b | reliability | PASS | behavioral probe: low-signal/reasonless `new` REFUSED (exit 1) — write-gate is enforced, not merely wired
H2c | reliability | FAIL | loop_lint exit=1 (2=FAIL expected); not FAIL-severity (see WARN/exit-code judgment call)
H3a | portability | FAIL | cross-host references (missing on a single-host install): .codex/hooks.json:.claude/skills/context-keeper/tools/hook.sh (not under .codex/skills/), .codex/hooks.json:.claude/skills/context-keeper/tools/codex_archive.sh (not under .codex/skills/), .codex/hooks.json:.claude/skills/prompt-triage/tools/hook.sh (not under .codex/skills/), .gemini/settings.json:.claude/skills/index-first/tools/augment.py (not under .gemini/skills/), .gemini/settings.json:.claude/skills/prompt-triage/tools/hook.sh (not under .gemini/skills/), .gemini/settings.json:.claude/skills/compliance-canary/tools/hook.sh (not under .gemini/skills/), .gemini/settings.json:.claude/skills/learn-skill/tools/hook_session_start.sh (not under .gemini/skills/), .gemini/settings.json:.claude/skills/context-keeper/tools/archive.sh (not under .gemini/skills/), .gemini/settings.json:.claude/skills/learn-skill/tools/hook_session_end.sh (not under .gemini/skills/), .gemini/settings.json:.claude/skills/context-keeper/tools/hook.sh (not under .gemini/skills/)
H3b | portability | PASS | scripts/check_carrier_sync.py=exit0; scripts/check_generated_files.py=exit0
H4a | memory | PASS | no dangling supersede chains
H4b | memory | FAIL | usage.json exists=True, wiki-refresh consumes usage/read-count=False
H4c | memory | FAIL | no covered-verdicts index page found under wiki/
H5a | efficiency | FAIL | orchestration_trace.py declares source/provenance=False, lanes.jsonl carries it=False
H5b | efficiency | FAIL | no shared activation/usage recorder in skills/_shared/ or compliance-canary/tools/ (learn-skill's telemetry.py is skill-scoped only)
H6a | quality | FAIL | 6/13 mismatched: brainer-audit (claimed 69.0KB, actual 123.4KB), output-filter (claimed 53.1KB, actual 33.9KB), prompt-triage (claimed 81.2KB, actual 103.6KB), task-retrospective (claimed 30.3KB, actual 38.6KB), verify-before-completion (claimed 0.1KB, actual 12.0KB), wiki-refresh (claimed 0.0KB, actual 25.7KB)
H6b | quality | FAIL | no conflict entry covers the team-lead + prompt-triage pair
H7 | orchestration | PASS | digest-cap rule present=True, test_brief_header.py has 7 test functions (>= 7 required)

5/16 PASS, 11 FAIL
```

`--gate` exit code on this baseline: **1** (nonzero — 11 FAILs present, as expected). Full run (`--report`) completes in well under 1 second.

## Round 2 fixes (cold-verifier NEEDS-FIXES, applied 2026-07-06)

A cold-context verifier reviewed round 1 and passed runner mechanics + the
surgical-diff bar, but flagged 4 check defects before this suite could serve
as the build gate. All 4 are applied; verdict deltas vs round 1 below.

1. **H3a (HIGH, false PASS) — fixed, verdict flipped PASS → FAIL.** The
   round-1 check tested `(REPO/rel).exists()`, which is a tautology in this
   dev checkout (`.claude/skills/`, `.codex/skills/`, and `.gemini/skills/`
   all happen to coexist here). The real SPEC defect is about a CODEX-ONLY
   install: `install_codex()` (install.sh ~L504-514) creates only
   `.codex/skills/`, never `.claude/skills/` — yet `.codex/hooks.json`
   references 3 paths under `.claude/skills/`
   (`context-keeper/tools/hook.sh`, `context-keeper/tools/codex_archive.sh`,
   `prompt-triage/tools/hook.sh`) that a codex-only machine would never have.
   The check now models per-host installs: every skills-dir path referenced
   by a host's own generated config must resolve under THAT host's own
   `skills/` prefix (`.codex/hooks.json` → `.codex/skills/...`,
   `.gemini/settings.json` → `.gemini/skills/...`); any reference into
   another host's dir is flagged as a cross-host bug regardless of whether
   this particular checkout has every host installed side by side. Applying
   the same principle to `.gemini/settings.json` surfaced 7 more cross-host
   references there (`.claude/skills/...`) that round 1 also missed —
   `install_gemini()` (install.sh) creates only `.gemini/skills/`.
   **Correction to the original claim in this file:** round 1 said
   "install.sh appears to have been fixed since the discovery lanes ran" —
   that was wrong. install.sh was never fixed; the round-1 check was blind to
   the codex-only/gemini-only case because every host happens to be installed
   in this working tree.

2. **H2a (MEDIUM-HIGH, under-scoped population) — fixed, population widened
   5 → 21 skills, verdict stayed PASS.** Round 1 scoped to frontmatter
   `auto-install: true` literally (5 skills: compliance-canary, eval-gate,
   loop-engineering, propagate, requirements-ledger). SPEC's H2a axis text is
   "every default-on skill has hook/probe/test/measured-evidence" — and
   install.sh's own opt-in test (`skill_is_optin()`, greps for
   `auto-install: *false`) treats an ABSENT auto-install key as default-on,
   same as an explicit `true`. Rescoped to `auto-install != false` (21
   skills: every skill except the 5 explicitly opted out — baton,
   brainer-audit, impact-of-change, learn-skill, security-oversight).
   requirements-ledger's named-fiat exception is unchanged. Verdict is still
   PASS: all 21 default-on skills carry >=1 of {non-empty drift_probes.json,
   tools/*.py with an adjacent test, a hook file, an EVAL.md with a genuine
   measured number} — verified per-skill, not assumed (e.g. `plan-first-execute`
   passes on its EVAL.md's real `N=3 x 5 prompts` A/B table, not a stub).
   SPEC.md's illustrative axis text cites "FAIL (plan-first-execute…)" as an
   example from the original 8-lane discovery; that skill's EVAL.md now
   carries genuine (if stale-flagged-for-refresh) measured numbers, so it
   clears the bar under the brief's own literal criteria — noted here as a
   SPEC-illustration-vs-current-repo discrepancy, not a check defect.

3. **H1b (MEDIUM, token-gesture hole) — fixed, verdict unchanged (still
   FAIL, same 8 offenders).** A bare `<!-- split-justified -->` comment used
   to flip an oversized SKILL.md straight to PASS with zero evidence a real
   core+deep-dive split happened. The marker now only counts if the skill
   dir ALSO ships >=1 companion `*.md` file (other than SKILL.md/EVAL.md)
   that the SKILL.md body actually links to by relative path
   (`[...](FOO.md)` / `[...](./FOO.md)`) — real evidence of tiering, not an
   unenforced comment. Verified against synthetic fixtures in a tempdir
   (bare marker/no companion → FAIL; marker + linked companion → PASS;
   marker + unlinked companion → FAIL) before trusting the production result.
   None of the 8 currently-oversized skills (compliance-canary, eval-gate,
   learn-skill, loop-engineering, security-oversight, task-retrospective,
   wiki-memory, wiki-refresh) carry the marker at all today, so the
   tightening doesn't change today's verdict — it closes the future gaming
   path the verifier identified.

4. **H2b (LOW, presence-not-enforcement) — fixed, verdict unchanged (still
   PASS, now on behavioral evidence).** Round 1 grepped wiki.py's source for
   a write-gate import/call — presence, not proof the gate actually fires.
   Upgraded to a behavioral probe: `wiki.py init` a throwaway tempdir wiki
   root, then `wiki.py new --template page --title "..." --body "" --reason
   ""` (a deliberately low-signal/reasonless page) against it, and assert
   nonzero exit + a REFUSED message. Confirmed live: `REFUSED: REJECTED:
   signal score 0.00 < threshold 3.00`, exit 1. Stays fully offline (wiki.py
   imports only stdlib: json/re/sqlite3/dataclasses/datetime/math/pathlib/
   typing), writes confined to a `tempfile.TemporaryDirectory`, and both
   `init` + `new` complete in well under 0.2s combined — the whole 16-check
   `--report` run still finishes in well under 10s (measured ~0.3s).

## Discrepancies vs SPEC.md's "today" column

SPEC.md's acceptance-test manifest table lists an expected-today verdict per
H-check, produced during the 8-lane discovery phase. These no longer hold
against the repo as it stands today:

- **H2b** (`wiki.py new invokes write-gate`): SPEC says FAIL; this repo's
  `wiki.py new_page()` genuinely enforces write-gate (behaviorally verified,
  not just grepped) — measured **PASS**.
- **H1b** (oversized SKILL.md count): SPEC says "FAIL (4 skills)"; this repo
  measures **8** skills over 12,288 bytes with no split-justified marker.
  Still a FAIL, but the body-size drift is worse than SPEC's cited count.
- **H2a** (SPEC's illustrative "FAIL (plan-first-execute…)"): under the
  rescoped default-on population (21 skills, matching install.sh semantics),
  all 21 clear the bar today, including plan-first-execute (genuine `N=3 x 5`
  measured A/B table in its EVAL.md) — measured **PASS**. This is a
  population/evidence discrepancy, not a check defect (see Round 2 fix #2).

**H3a now correctly matches SPEC's "FAIL (codex)" expectation** — round 1's
false PASS here is corrected in Round 2 fix #1 above; this was the verifier's
highest-severity finding.

All other rows match SPEC.md's expected-today verdict.
