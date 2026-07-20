# Skill-effectiveness verification

This directory turns the 2026-07 sibling audit into repeatable evidence. The
transcript analysis remains explicitly observational; outcome claims require
the paired harness.

## Fire-vs-value

```bash
python3 eval/skills_effectiveness/fire_value.py \
  path/to/one.jsonl path/to/two.jsonl \
  --json-out eval/results/fire-value.json \
  --markdown-out eval/results/fire-value.md
```

Optional labels are JSONL records containing only `event_id`, `label`,
`rationale`, and `reviewer`. Labels are one of `ACTED`, `ALREADY_COMPLIANT`,
`IGNORED`, or `UNCLEAR`. Transcript content is rejected. Event IDs join the
label to a source SHA-256 and JSONL line index.

The old sibling total of 176,507 called Python string length “bytes.” The tool
preserves that as `legacy_codepoint_count` while separately reporting exact
UTF-8 bytes. For the named transcript those are 176,507 code points and 178,092
UTF-8 bytes across the same 80 genuine reminders.

Compaction re-injects the prior transcript into the rebuilt context, so the
same canary system-reminder block can recur byte-identically many times in one
raw session log. Each per-source and totals block now reports
`distinct_reminder_events` (unique normalized-block SHA-256 count) and
`duplicate_occurrences` (`reminder_events` minus that count) alongside the raw
`reminder_events` total, and both the JSON events (`block_sha`) and the
markdown carry the same numbers. Use raw `reminder_events`/`injected_utf8_bytes`
for injection-cost claims — that is what gets paid for and re-sent every time
context is rebuilt — and use `distinct_reminder_events` when the claim is about
independent behavioral samples (e.g. fire-rate or label counts), since repeated
re-injections of one block are not independent observations.

## Frozen trigger gate

`cases.py` deterministically defines 862 cases (483 hard negatives / 379
semantic positives), grown by frozen-prefix generations: the original 500
(400 neg / 100 pos), +100 notification morphologies (600), +75 deferred-fire/
timer/provenance shapes (675), +175 adversarial audit fault shapes (850),
+12 subsequent additions (862; see git history of `cases.py`).
Every earlier prefix stays byte-identical (digest-pinned in
`test_skills_effectiveness.py`). NOTE: templated repetition means the 475
negatives collapse to ~11 distinct shapes — treat results as a clustered
regression floor, never as N independent Bernoulli observations for
inferential precision claims.
Score a JSONL file containing `{ "id": ..., "fired": true|false }`:

```bash
python3 eval/skills_effectiveness/run_trigger_cases.py \
  --profile frontier --out /tmp/frontier-trigger-results.jsonl
python3 eval/skills_effectiveness/trigger_gate.py \
  /tmp/frontier-trigger-results.jsonl --profile frontier --json
```

The runner invokes the current canonical canary hook for every case in isolated
session state. All 100 semantic positives remain in the corpus; frontier's
scored emission expectation is mechanism-specific, so intentionally suppressed
correction and error-loop cases are expected silent. Verification variants
cover no evidence, failed evidence, stale/pre-mutation evidence, wrong evidence
class, incidental keywords, and successful fresh post-mutation suppression.

Historical record (2026-07-16, three-profile world): the corpus measured
frontier and shadow at TP=50/FP=0/FN=0, with shadow telemetry/output
equivalence passing; legacy measured TP=85/FP=250/FN=15 and failed all
precision/FIR gates, and the failure was retained rather than weakening
labels. Exact result files were ephemeral `/tmp` artifacts, reproducible at
the time with `--profile shadow` / `--profile legacy`. The `shadow` and
`legacy` profiles were retired 2026-07-19 (PROFILES is now `{frontier, off}`
in `skills/compliance-canary/tools/hook.py`); `--profile` only accepts
`frontier` or `off` today.

The gate requires reviewed precision at least 95%, false injection below 1%,
and a one-sided 95% Wilson upper bound below 1%. With 400 negatives, zero false
injections has an upper bound below 1%.

## Paired production harness

Inspect the complete 8,300-run preregistration without calling a model:

```bash
python3 eval/skills_effectiveness/ab_harness.py --plan > /tmp/skills-matrix.json
```

The number is a planned-invocation count, never a completed-run claim. Each
candidate has its own 50-case corpus and deterministic digest. The 15 trivial,
20 normal, and 15 compound cases use 50 distinct task families (arithmetic,
string, sequence, mapping, parsing, interval, graph, and artifact workflows),
not numeric repetitions of one ceiling task.

Run exactly one arm/case (live execution is deliberately explicit):

```bash
python3 eval/skills_effectiveness/ab_harness.py --execute \
  --candidate verify-before-completion --arm FULL \
  --lane codex-default --case-id coding-00 \
  --out eval/results/skills-effectiveness/verify-full-coding-00.json
```

Run or resume the full campaign, optionally capped for a smoke pass:

```bash
python3 eval/skills_effectiveness/ab_harness.py --execute \
  --campaign-dir eval/results/skills-effectiveness/campaign-2026-07 \
  --lane-filter codex-default \
  --max-runs 10
```

The campaign writes one atomic outcome per run. Resume skips only a record with
matching manifest/case run hash, `record_status=completed`, a valid observed
arm, and a successful transport. Transport errors, missing skill loading, and
malformed partial records go under `blockers/` and are never counted as task
outcomes. Re-running retries blockers.

The default mixed-host campaign currently aborts before any model call because
Claude's unrestricted Bash can bypass WebFetch/WebSearch restrictions. Use the
Codex lane filter above; Codex tool subprocesses run with workspace sandbox
network disabled. Claude stays a recorded NO-LAUNCH blocker until command-level
Bash egress isolation is proven. Child processes receive an allowlisted
environment, isolated empty HOME, no API secret variables, and a leak tripwire.
Auth material is never copied into a fixture; an auth failure is a blocker.

After a campaign, pair valid outcomes and apply the preregistered McNemar,
sign-test, bootstrap, scope, and token-overhead gates:

```bash
python3 eval/skills_effectiveness/analyze_campaign.py \
  eval/results/skills-effectiveness/campaign-2026-07 \
  --out eval/results/skills-effectiveness/campaign-2026-07-analysis.json
```

Incomplete pairs produce `NO_VERDICT_INCOMPLETE`; transport and loading
blockers never masquerade as observed task outcomes, but do enter exclusion and
worst-case sensitivity analysis. Safety exceptions and subjective P0/P1 labels
remain separate blinded evidence rather than inferred from pass rates.

Blockers are not silently discarded: reports include per-arm exclusion rates,
an ITT worst-case sensitivity (treatment blocker=failure, control blocker=pass),
and complete-case results only as a secondary analysis. Primary comparisons are
FULL vs OFF on deterministic task pass; Holm correction is applied across
candidates within each host family. Discordant-pair counts and a low-power flag
make N=50 limitations explicit.

Codex uses `exec --ephemeral --ignore-user-config`; Claude uses `-p --bare
--no-session-persistence --model opus`. Each invocation creates a fresh git
fixture and deletes it afterward. Full, compact, placebo, and off arms are
loaded through the lane's native project skill directory. Configure the
additional compact mid-tier lane with `--mid-tier-model` or
`BRAINER_EVAL_MID_TIER_MODEL`; the harness does not guess a moving model alias.

FULL uses an arm-controlled project instruction carrier (`AGENTS.md` for Codex,
`CLAUDE.md` for Claude) containing the exact candidate body, so experimental
`disable-model-invocation` metadata cannot silently invalidate the arm. Compact
and placebo carriers contain their corresponding bodies; OFF has no carrier.
The user task bytes are identical across arms, and reports include body/carrier
SHA-256 proof instead of relying on a candidate name appearing in final prose.
This is explicitly an exact-body **carrier ablation**, not proof of native lazy
skill loading. Run the separate native host check (a paid call, not run here):

```bash
python3 eval/skills_effectiveness/native_activation.py --execute \
  --lane codex-default --out /tmp/codex-native-activation.json
```

FULL and PLACEBO use the same carrier position, header, UTF-8 byte count, and
newline shape. PLACEBO remains only length/shape matched; semantic neutrality
cannot be guaranteed and is labeled in every record.

For executable prompt-hook candidates, FULL also installs an isolated native
host hook configuration and invokes the exact copied hook with the frozen
UserPromptSubmit payload before the model. The record distinguishes configured,
invoked, fired, and received context; OFF has neither skill nor hook state.
Single-turn cases are not a causal test of longitudinal canary/drift mechanisms.
The estimands are kept separate: `BODY_CARRIER` may receive a static-body
ablation verdict, while `PROBE_HOOK` receives `NO_VERDICT_PROTOCOL` until T1
creates a real mutation/claim and T2 resumes the same isolated within-run
session. `STACK_RESIDENT_CONTEXT` excludes the stack's longitudinal hook effect.
Ephemeral Codex and bare/nonpersistent Claude cannot currently satisfy that
resume contract, so the harness records a protocol blocker and does not pretend
same-turn manual injection is causal.

Input, output, and cache tokens are stored separately with missingness. USD cost
is recorded only when `pricing.json` has a dated authoritative price for the
served model; otherwise cost is missing, never assumed zero. Campaign analysis
reports known cost and missingness per attempted and per valid run.

## Optional independent reviewer

`kimi_reviewer.py` is opt-in and never part of the prompt stack or campaign.
It supports pre-launch adversarial architecture review and post-run blind review
of subjective criteria only. It refuses to judge deterministic pass/scope/write
gates and refuses same-model self-review. Configuration is environment-only:

```bash
MOONSHOT_API_KEY=... MOONSHOT_BASE_URL=... MOONSHOT_MODEL=... \
python3 eval/skills_effectiveness/kimi_reviewer.py --execute \
  --role architecture --input redacted-manifest.json --out review-metadata.json \
  --timeout 300
```

Keys are never stored. Inputs and likely secret fields are scrubbed; results
record reviewer identity/version when returned, prompt/source/response hashes,
latency, usage, and a scrubbed structured review. Tests use an offline mock and
make no network calls.
Transport failures and reasoning-only/empty responses are recorded as blocked
reviews, never accepted as empty findings. Timeout is bounded to 30–600 seconds.

## Quarantine classification and native-delivery smoke

Validate the hash-pinned classification of the 14 experimental/manual bodies
and regenerate its human-readable report:

```bash
python3 eval/skills_effectiveness/quarantine_classification.py \
  --markdown-out eval/results/skills-effectiveness/quarantine-classification.md \
  --json
```

The classification separates explanatory prose from retained deterministic
tools. A changed `SKILL.md` hash invalidates the verdict and forces re-review.
No classification authorizes propagation outside canonical Brainer.

Before any paid outcome campaign, run the four-call carrier-free feasibility
smoke. It installs a nonce-bearing project skill only in `FRONTIER`, uses the
same nonce-free prompt in `OFF`, and creates a fresh git fixture for every call:

```bash
python3 eval/skills_effectiveness/native_delivery_smoke.py --execute \
  --out eval/results/skills-effectiveness/native-delivery-smoke.json
```

Codex runs read-only with workspace network disabled and user configuration
ignored; shell commands inherit no host environment. Claude runs with only its
native `Skill` loader, an empty strict MCP surface, and project settings. Host
authentication stores are inherited by the CLIs, but API-key environment
variables are excluded and credentials are never copied into fixtures. A run
is invalid if the host reports any tool call. Use this only with the controlled
nonce skill, never an untrusted skill body. This proves only native skill
delivery and a clean OFF control; it is explicitly not a task-outcome verdict.

The manifest preregisters candidates, strata, measures, stack comparison,
paired statistics, and decision gates. Subjective criteria may use a blind
cross-family judge; deterministic acceptance and scope checks remain primary.

## Focused native pilot

The full matrix is preserved but frozen. The completed focused v2 protocol uses
19 frozen cases, native loading of the same skill name in both arms, fresh
single-use fixtures, and separate Codex-default and Claude-opus-alias lanes:

```bash
python3 eval/skills_effectiveness/focused_pilot.py --plan
python3 eval/skills_effectiveness/focused_pilot.py --analyze \
  --campaign-dir eval/results/skills-effectiveness/focused-pilot-v2-2026-07-16 \
  --out eval/results/skills-effectiveness/focused-pilot-v2-analysis.json
```

The 76 valid v2 outcomes plus four excluded transport-preflight calls exhaust
the approved 80-call cap. Do not rerun the campaign merely to remove the
ceiling effect. The result is a static compact-body estimand; it does not test
longitudinal hook behavior. See
`eval/results/skills-effectiveness/focused-pilot-v2-analysis.md`.

## Tests

```bash
python3 -m unittest discover -s eval/skills_effectiveness -p 'test_*.py'
```

## Model-upgrade re-test

When a host adopts a new frontier model tier for main-loop work, re-run this
harness against it rather than assuming prior verdicts still hold — see
`docs/MODEL_UPGRADE_RETEST.md` for the standing ritual (which commands to
re-run, in what order, against which preregistered thresholds).
