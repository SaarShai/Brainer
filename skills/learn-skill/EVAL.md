# learn-skill — EVAL

**Posture: opt-in (`auto-install: false`).** Ships symlinked + listed but wires no hook.
No measured A/B yet; promotion to default needs N≥50 like every other Brainer skill.

## What it is
Brainer's port of Hermes' `/learn`: ingest a pointed-at source (dir / URL / described
workflow / pasted notes) into a `proposed` skill. Prompt-only over existing tools; the
only write-path gate is `write-gate`'s rule scorer.

## What to measure (when N is available)
- **Trigger P/R** — does the description fire on "/learn", "turn this into a skill",
  "make a skill from these docs", and NOT on unrelated asks. Build an adversarial corpus
  (behavioral test, per `behavioral-skill-testing-method`), not presence checks.
- **Did-it-help** — does a learned skill, once promoted, actually reduce tokens/turns on
  the task it captures vs naive re-derivation? A/B with cold naive subjects.
- **Dedup precision** — on a labelled set of near-dup vs orthogonal candidates, does
  `dedup` flag the dups (recall) without crying PATCH on every new skill (precision)?

## The self-improvement mechanisms (all built — v1.13)
1. **Telemetry** (`telemetry.py`) — `record` an explicit hit/abort, or `scan` a transcript
   to infer outcomes from `Skill` tool_use + next-turn correction. `stats` / `flag`
   aggregate; a `checkpoint` record clean-slates the count on refinement.
2. **Counted promotion** (`learn.py promote` / `demote`) — telemetry-gated: ≥N consecutive
   hits, zero trailing abort, lints clean → `proposed → trusted`. A closed gate (verifier
   ≠ generator); spec in `LOOPS.md`, lints clean.
3. **Nomination** (`workflow_nomination` detector in compliance-canary + this skill's
   `drift_probes.json`) — nudges `/learn` at a non-trivial wrap-up; never writes.
4. **Staleness** (`learn.py staleness`) — git-truth for repo sources, age-flag for URLs;
   `--apply` marks drifted skills `stale`.
5. **Refinement** (`learn.py refine` / `patch`) — patch a failing skill (gated: write-gate
   rationale + lint, else revert), reset to `proposed`, checkpoint telemetry. Improve before
   retiring. Loop spec #5 (generator = agent; verifier = `patch`; advisor on stuck).
6. **Conditional activation** (`requires_tools:` + `learn.py check-tools`) — surface a skill
   whose external CLI deps are absent here (advisory; Claude Code has no native tool-hiding).
   Ported from Hermes `requires_tools` / `fallback_for_toolsets`.

Sessions hooks (opt-in `install.sh`): SessionEnd `scan` (append-only); SessionStart nudge
(promote-ready / failing→refine / missing-tools / stale). Mutating steps stay agent-run.

## Known limits (documented, not bugs)
- **Inferred outcomes are heuristic.** `scan` marks a skill `abort` only when the *next user
  turn* matches a correction regex — it can't see a silently-bad result the user didn't call
  out, and it can't see a slash-literal invocation that never surfaced as a `Skill` tool_use.
  Inferred records carry `source: inferred`; a strict operator promotes on `--manual-only`.
- **Dedup is lexical, not semantic.** Token-overlap on descriptions + exact code-line match
  on bodies. Catches obvious dups and reused commands; misses paraphrased-but-equivalent
  procedures. An *advisory* abort, not a hard guarantee.
- **Nomination is conservative by design.** Fires only at a completion-claim turn past a
  tool-call floor on non-trivial work — it will miss a capturable workflow that didn't end
  on a completion phrase (false negatives preferred over alert fatigue). It can also be
  *ignored* — a nudge the user skips is silent non-adoption, by design (nominate, not force).
- **Hand-written skills are not in the lifecycle.** Only skills born from `/learn` (they
  carry a `learned_at` stamp) are scanned by the session hooks / promotion gate. A
  pre-existing hand-authored skill is silently skipped — to bring one in, re-`/learn` it.

## Hardening (adversarial review, turn 4)
A 5-agent read-only refuter workflow attacked each feature; it found and we fixed:
- **HIGH** telemetry undercount — dedup key `(skill, ts)` collapsed distinct invocations
  when transcript events had no timestamp. Now keyed by `(skill, ts, idx)`.
- **HIGH** streak miscount — trailing hit/abort was computed by file/append order, so a
  late scan of an older transcript could mask a recent abort and wrongly clear the gate.
  Now sorted by event time before the streak walk.
- **MED** CRLF flattening — `_rewrite_frontmatter` stripped `\r` (and `read_text` did too).
  Now reads/writes with `newline=''` and rejoins with the file's own EOL.
- **MED** stale-promotion — promote accepted `status: stale`; now `proposed`-only (stale
  must be re-`/learn`ed first), matching the doctrine in SKILL.md.
- **MED** staleness honesty — a failed `git log` was reported as authoritative "fresh";
  now returns "unknown".
- **LOW** triviality/abort regexes — env-var/`sudo` prefixes and benign "no problem" /
  missed "didn't work" tightened.
Each fix ships a regression test reproducing the exact scenario the passing tests missed
(learn 20 · telemetry 11 · nomination 7 · hooks 5 = 43).

## Provenance
Design = two doc sweeps of the Hermes skills page + two GLM-5.2 review rounds (design, then
this build plan). GLM edits folded: promote cut, body-aware dedup, PATCH=abort-not-merge,
holes documented, 5-step flow. `description ≤60` kept advisory (Brainer uses long trigger
descriptions) with stated reason.
