# Codex handoff packet — long-horizon FRONTIER-vs-OFF experiment

Prepared 2026-07-18. Reader: a `codex exec` agent (recommended model
`gpt-5.6-sol`, reasoning effort `xhigh`) running in the Brainer project
(`/Users/za/Documents/Brainer`), acting as **orchestrator** for the rest of
this experiment. This is a handoff of ownership, not a status report — verify
every fact below yourself before acting on it; do not trust this document as
current truth once time has passed.

## 0. What this experiment is

A preregistered pilot testing whether compliance-canary's `FRONTIER` profile
improves long-session reliability vs `OFF`, using scripted 44-turn scenario
sessions run twice (once per arm) and graded blind by GLM-5.2. Full design:
`eval/skills_effectiveness/longhorizon_preregistration_draft.md`. Read it
before doing anything paid — it is the source of truth for the protocol; this
packet is only an operational summary.

## 1. Ground truth — verify these yourself, do not assume they still hold

Run these checks before touching anything:

```bash
cd /Users/za/Documents/Brainer
git rev-parse HEAD                                    # expect 8e6e28d... or later on main
git status --porcelain                                # expect empty
cat eval/results/skills-effectiveness/longhorizon-freeze-bundle.json
git diff <freeze_commit> HEAD -- skills/ hooks/ install.sh --stat   # expect EMPTY diff
ls eval/results/skills-effectiveness/longhorizon-main/ | grep -v artifact
python3 -c "
import json
for s in ['scenario-02-off','scenario-02-frontier','scenario-06-off','scenario-06-frontier']:
    m = json.load(open(f'eval/results/skills-effectiveness/longhorizon-main/{s}/manifest.json'))
    turns = m.get('turns', [])
    print(s, len(turns), all(t['codex_exit_code']==0 for t in turns))
"
grep -n "SESSION_CONFIGS = {" -A2 eval/skills_effectiveness/longhorizon_score_counted.py
```

State as of this writing (RE-VERIFY, do not trust):

- **Freeze commit**: `b6fa8ae695ee0b9ec0bdba7410b30209602e23fd`. Freeze bundle
  recorded at commit `f1479f4`. Freeze bundle hashes `grader_model_id:
  "glm-5.2"`, `kappa_threshold: 0.7`, and all six `scenario-0N.md` scripts —
  **including 01/03/04/05, which were hashed at freeze time but never run.**
- **Guard content** (`skills/`, `hooks/`, `install.sh`) is byte-identical
  between the freeze commit and current `main` — confirmed by an empty
  `git diff --stat`. One eval-only deviation was accepted mid-run: commit
  `54f20b2` (scoring-harness code, not guard code) landed after the freeze.
  If you make ANY new commits before this run is fully scored, that breaks
  the freeze lock again — the owner accepted one such deviation once and said
  "no more." Do not commit to `main` while a counted session is in flight.
- **Data collected so far**: exactly 4 counted sessions — `scenario-02-off`,
  `scenario-02-frontier`, `scenario-06-off`, `scenario-06-frontier` — each
  44/44 turns, exit 0. This was an owner-directed condensation from the
  originally-designed 12-session (6-scenario × 2-arm) GPT stratum. **Not yet
  scored.**
- **Scoring is only wired for scenario-02 and scenario-06.**
  `longhorizon_score_counted.py`'s `SESSION_CONFIGS` / `SNAPSHOT_BUILDERS`
  dicts have exactly two entries. Scenarios 01/03/04/05 have scripts and
  answer keys in `eval/skills_effectiveness/scenarios/scenario-0{1,3,4,5}.md`
  and are hashed into the freeze bundle, but **nothing can score sessions run
  against them today.** Running those sessions before building their scoring
  config would just spend money on unscoreable data.
- **Secrets**: `~/.config/brainer/secrets.env` (mode 600, never commit)
  sources `ZAI_API_KEY` (grader, glm-5.2 via z.ai) and
  `KIMI_API_KEY`/`KIMI_BASE_URL`/`MOONSHOT_MODEL` (unused by this stratum).
  `longhorizon_gate.py`'s `load_api_key()` bash-sources this file — do not
  reimplement a flat KEY=VALUE parser, it silently breaks on the
  `$(cat ...)` substitution inside the file (this bit us once already).
- **Venue**: `/Users/za/Documents/PROMPTER`. Its `.git` is currently
  mid-relocation by a tool called "CodexDriveRelief" and git commands there
  fail with `not a git repository`. This is **non-fatal** — the driver
  gracefully records `"venue_git_state": "unavailable: ..."` in the manifest
  rather than crashing (verified: all 4 completed sessions show this and
  still succeeded). Do not attempt to "fix" the venue's git state as a
  prerequisite; it isn't one.
- Other 3 strata (Fable-5, Kimi-K3) are out of scope for you — they use the
  claude-code host, not codex, and are paused. Do not touch
  `eval/results/skills-effectiveness/longhorizon-fable5/` or
  `-kimik3/`.

## 2. Your task, in order

### Step A — score what already exists (cheap, no new paid sessions)

This is the highest-value, lowest-cost next action and should happen first
regardless of what you decide about Step B.

1. Read `eval/skills_effectiveness/longhorizon_score_counted.py` end to end.
2. Hand-validate `snapshot_scenario_02` and `snapshot_scenario_06` (the
   mechanical completed-predicates) against the real recovered artifacts at
   `eval/results/skills-effectiveness/longhorizon-main/artifact-archives/`
   (read `artifact-archives/PROVENANCE.md` first — it explains why an
   archive exists separately from the venue and how each file was
   sha256-verified). Confirm the predicates actually match the answer-key
   tables in `scenario-02.md` / `scenario-06.md` (search `S02-R0` / `S06-R0`
   in those files) before trusting any verdict computed from them. This was
   flagged as **not yet validated** by whoever built the scorer — treat it as
   the single highest-risk item in the verdict path.
3. **Important**: `longhorizon_score_counted.py` currently reads final
   artifacts from `manifest["venue"] / manifest["fixture_root"]` (the shared,
   overwritten venue fixture dir), which for the OFF arm of each scenario no
   longer holds that arm's final state — the FRONTIER arm ran second and
   overwrote it. You must point scoring at the archived, hash-verified copies
   in `artifact-archives/<scenario>-<arm>/` instead, OR (better, if time
   allows) first run the *now-merged* fix from commit `286cd98` forward: newer
   sessions record `manifest["final_artifacts"]` with per-file sha256; that
   fix landed on `main` (`8e6e28d`) but the 4 already-completed probe
   sessions predate it and don't have a `final_artifacts` key — use the
   `artifact-archives/` copies for those 4, don't try to regenerate.
4. Run the scorer, get `verdict-report.json`. Report the decision
   (KILL / DEMOTE / would-promote-but-capped-at-n=2 / ambiguous) plainly.
   Remember: at n=2 scenarios, PROMOTE is statistically unreachable by design
   (owner-accepted condensation) — do not overstate a positive result as more
   than a signal probe.
5. Do not commit yet. See §3.

### Step B — decide whether to extend scope (requires owner confirmation)

The original design was 6 scenarios × 2 arms = 12 GPT-stratum sessions,
condensed by the owner to 2 scenarios for time. If Step A's verdict is
ambiguous or the owner wants more statistical power, extending to the
remaining 4 scenarios (01, 03, 04, 05) requires, **in this order**:

1. Building `SNAPSHOT_BUILDERS`/`SESSION_CONFIGS` entries for scenarios
   01/03/04/05 in `longhorizon_score_counted.py`, mirroring the pattern of
   `snapshot_scenario_02`/`snapshot_scenario_06` — each predicate must be
   transcribed from that scenario's own answer-key table (search `S0N-R0` in
   `scenario-0N.md`), not invented. Write tests against synthetic fixtures
   before trusting it, the same way the existing two were built.
2. Only then run the 8 remaining paid sessions:
   ```bash
   for i in 1 3 4 5; do
     id=$(printf "scenario-%02d" "$i")
     if [ $((i % 2)) -eq 1 ]; then arms="frontier off"; else arms="off frontier"; fi
     for arm in $arms; do
       out="eval/results/skills-effectiveness/longhorizon-main/$id-$arm"
       [ -f "$out/manifest.json" ] && { echo "SKIP $id/$arm"; continue; }
       python3 eval/skills_effectiveness/longhorizon_run_session.py \
         --scenario "eval/skills_effectiveness/scenarios/$id.md" --arm "$arm" \
         --venue /Users/za/Documents/PROMPTER --out-dir "$out"
     done
   done
   ```
   Each session takes ~20-30 min; running all 8 sequentially is ~3-4h. This
   is a **paid, multi-hour commitment the owner explicitly condensed away
   once already** ("consolidate and condense this to as few tests as
   strictly required, down to ~1h") and then explicitly chose to stop short
   of. **Do not start Step B without fresh, explicit confirmation from the
   human** — surface Step A's result first and ask.
3. Note: extending scope means the freeze bundle's scenario hashes are still
   valid (01/03/04/05 were hashed at freeze time and are untouched), but you
   will need to re-run `longhorizon_score_counted.py`'s validation against a
   larger `SESSION_CONFIGS`, and the final verdict-report should note the
   extension explicitly (it changes the n and the statistical framing in the
   preregistration amendment).

## 3. Hard constraints (do not violate)

- **No commits to `main` while any counted session is in flight or unscored
  results are pending review.** One deviation was already accepted; the
  owner said no more. When you do commit (after Step A's verdict is
  produced, or after Step B fully completes), it should be ONE commit
  containing the verdict-report, any newly-collected session data, and
  nothing else opportunistic.
- **Never re-run a session whose manifest already shows 44/44 turns, exit 0**
  — sessions are idempotent-by-manifest; check before running, always.
- **Never touch Fable-5/Kimi-K3 result directories or drivers.**
- **Grader model must be `glm-5.2`** (hardcoded requirement from the freeze
  bundle) — do not substitute another grader.
- **Kimi K3, not K2.7**, if you use `pi_agents` for any sub-task advisory
  work — this is a standing project rule, not specific to this experiment.
- If anything about the frozen bundle, the guard diff, or a manifest
  contradicts what's written above, **trust what you observe now**, not this
  document, and flag the discrepancy to the human before proceeding.

## 4. Suggested model/effort allocation for your own sub-work

You (gpt-5.6-sol, xhigh) should do the judgment calls: predicate validation
against answer keys, the Step A/B scope decision, verdict interpretation. Push
mechanical work — building the 4 new snapshot builders' boilerplate, writing
synthetic-fixture tests, transcribing answer-key tables — to a cheaper
sub-agent if your harness supports spawning one; don't spend xhigh reasoning
on typing out predicate dicts once the pattern is established from
scenario-02/06.
