# compliance-canary — eval status

**Status:** v1.10.0 — **skill-pulse folded in** (2026-06-16): one `UserPromptSubmit` hook now runs both mechanisms — symptomatic per-skill probes *and* the periodic skill-rule re-anchor. Hook correctness verified by [tools/test.sh](tools/test.sh) (56 cases — probes + re-anchor cadence/yield/floor/alias/BOM/allowlist + adversarial hardening: malformed payload, non-str session_id, ReDoS time-budget, reminder cap); offline probe baselining via [tools/measure.py](tools/measure.py); canary p99 latency 41 ms on a 400-line synthetic transcript.

## Why merged (one reactive hook instead of two)

`skill-pulse` and `compliance-canary` were separate skills on the **same** `UserPromptSubmit` event — duplicating ~150 lines of state/lock/gc/transcript infra, costing two catalog entries, firing two python processes per turn, and (the user-visible cost) able to emit **two consecutive** `<system-reminder>` blocks on a turn that was both a pulse-cadence turn and a symptom turn. skill-pulse's own EVAL flagged the fix: *"fold the rule-re-anchoring into compliance-canary … one reactive hook instead of two — the reactive hook is the better-shaped anti-drift bet."* This merge does exactly that. Net effect: −1 catalog entry (~70 resident tokens), −1 process/transcript-read per turn, −1 state file, and a **single global anti-nag budget** — the re-anchor yields to a fired probe, which two uncoordinated hooks could not do. Both measured mechanisms are preserved (symptomatic +0.44, periodic +0.27 — cross-model longrun, two model families), now under one default-on skill.

## Periodic re-anchor — empirical basis (absorbed from skill-pulse; published, not our measurement)

arXiv [2510.07777](https://arxiv.org/html/2510.07777), "Drift No More?", tests reminder injections at turns 4 and 7 of 10-turn agent conversations:

| Model | KL drop | Judge score (5-pt) |
|---|---|---|
| LLaMA-3.1-8B | 5.827 → 5.392 (−7.5%) | 2.837 → 3.302 (+0.46) |
| Across models | 6.45 – 11.81% | +0.5 – 0.6 (+16 – 27%) |

The paper does NOT compare cadences (only turns 4 + 7), formats, or rotated phrasings — so the default cadence 4 / fixed text is the most paper-validated configuration. **Token economy:** the one-line re-anchor payload costs ~97% fewer tokens per 1000 turns (~76k) than re-injecting the 8 pulse skills' full `SKILL.md` bodies at the same cadence (~2.59M) — deterministic, computed from the real catalog. Posture note carried forward: vendor/practitioner consensus leans *reactive > periodic*, so the re-anchor is deliberately subordinate here (it yields to probes); a measured cadence sweep on this catalog is the gate before raising its weight.

## Verified — unit

See [tools/test.sh](tools/test.sh). Headline cases:

- Each detector kind triggers when it should and stays silent when it shouldn't
- Anti-spam cooldown suppresses repeat fires
- Custom regex + custom claim_pattern honored
- Bootstrap probes (`caveman-ultra` filler + word-creep, `verify-before-completion` unverified-done) fire on synthesized transcripts
- Malformed `drift_probes.json` → skill skipped, hook proceeds
- Empty / missing transcript → silent
- Two sessions interleaved → independent probe-history
- 10 parallel invocations → state-locked
- State GC at session-start

## Verified — live e2e

**Run 1 — canary detects and the model adapts.** `claude -p` haiku session, 2 turns:

- Turn 1 prompt induced "Certainly! ... I'd be happy to ... Sounds good ... Looking forward to collaborating" — 70 words of filler.
- Turn 2 (resume): hook fired, transcript records the corrective as `attachment.type="hook_success"` with the full `<system-reminder>` referencing `caveman-ultra [forbidden_regex]`.
- **Model response on turn 2: "Acked. I understand." (3 words.)** The corrective demonstrably changed behavior.

**Run 2 — multi-hook UserPromptSubmit chaining.** *(Historical, pre-merge: when re-anchor + probes were two separate hooks. Post-2026-06-16 they are one hook with a shared budget — the re-anchor now yields instead of co-firing, so this co-emission no longer occurs.)* Same project with BOTH `skill-pulse` and `compliance-canary` wired to UserPromptSubmit. Single user prompt where state was primed so both hooks should fire (skill-pulse at turn 4, canary fresh with prior filler in transcript):

| Hook | Fired | Bytes emitted | Attachment in transcript |
|---|---|---|---|
| skill-pulse | ✓ | 769 | ✓ |
| compliance-canary | ✓ | 541 | ✓ |

Canary's `probe_history` logged two probes firing simultaneously (`caveman-ultra:filler-phrases` + `verify-before-completion:claim-without-evidence`). Both hooks' stdout was captured by Claude Code; no clobbering.

## Verified — latency

n=100 invocations against a synthetic 400-line transcript with 2 active probes (forbidden_regex + word_count_per_message):

| min | p50 | p95 | p99 | max | mean |
|---|---|---|---|---|---|
| 34.0 ms | 36.2 ms | 39.5 ms | 40.9 ms | 41.9 ms | 36.7 ms |

Comparable to `skill-pulse`. Python cold-start dominates; transcript scan + regex are in the noise.

## Verified — measure.py paths

- Single file, human-readable output ✓
- Multi-file `--summary` (no per-fire details, totals only) ✓
- Glob expansion (`*.jsonl`) ✓
- `--json` produces parseable JSON ✓
- Nonexistent file gracefully skipped, others still processed ✓

## What this gives you that nothing else does

- [delta-hq/cc-canary](https://github.com/delta-hq/cc-canary) reads transcripts **offline** and reports drift after the fact. Useful for analysis, useless mid-session.
- Cursor `alwaysApply` re-injects the same rule every turn, regardless of whether the rule was followed — no symptom gate, no yield.

`compliance-canary` is the only piece that **detects drift in the running session and intervenes with a targeted, evidence-quoting reminder** — and, in the same hook, re-anchors fading rules on a paper-calibrated cadence that *yields* to those symptom correctives.

## Offline measurement (addresses out-of-scope item 2)

`tools/measure.py` runs the production detectors against any transcript JSONL with no side effects:

```bash
python3 tools/measure.py ~/.claude/projects/<proj>/<sid>.jsonl
python3 tools/measure.py ~/.claude/projects/*/*.jsonl --summary
```

Lets a user:

1. **Baseline before installing** — measure how much drift their existing sessions show
2. **Tune thresholds** — adjust `word_count_per_message.threshold` based on actual session distributions
3. **Validate new probes** — sanity-check a new regex against past transcripts before declaring it in `drift_probes.json`
4. **A/B compare** — run measure.py on sessions captured pre-install vs. post-install to quantify uplift

The data plan for in-the-wild measurement (paper-style):

1. Capture N=50+ long sessions (>20 turns) without the hook → baseline drift rates per probe
2. Install hook, capture N=50+ matched sessions → post-install drift rates
3. Compare trigger-rate distributions; expected outcome: probe trigger rates drop because the corrective text reduces repeat violations within a session

## Self-test

```bash
bash skills/compliance-canary/tools/test.sh
```

## Out of scope

- LLM-judge probes (semantic, not syntactic). Cleanest v2 add.
- Edit-vs-Write tool-choice drift detector. Easy v2 add.
- Cross-session drift trends (week-over-week regression in a project). Belongs in `wiki-memory` long-term, not here.

## Moved from SKILL.md (2026-06-12 SkillReducer-criteria audit)

_Provenance/rationale below is maintainer context, not runtime instruction — relocated so the lazy-loaded body stays actionable._

## Why it exists

Two halves of one problem, now one skill:

- **Prevention (re-anchor)** — re-states active skill rules every N turns so slow attention decay doesn't bury them. Spends a few tokens on compliant turns; that's the cost of not waiting for a symptom. Was `skill-pulse`.
- **Detection (probes)** — stays silent until measurable drift shows in the assistant's output, then pinpoints which rule broke and how, quoting the evidence.

The re-anchor yields to a fired probe, so on a shared turn you get detection (higher-signal), not both. Prevention for the quiet decay; detection for the loud break.

## Lineage

- [delta-hq/cc-canary](https://github.com/delta-hq/cc-canary) (65★) — direct forerunner of the probe half. Forensic JSONL drift detector with no in-loop intervention; this is "cc-canary's probes, but in-loop and per-skill-declared."
- arXiv [2510.07777 — "Drift No More?"](https://arxiv.org/html/2510.07777) — empirical basis of the **re-anchor** half (timed reminders cut KL divergence 6.45–11.81%, lift judge scores +0.5–0.6). Carried in from skill-pulse.
- [Cline Focus Chain](https://docs.cline.bot/features/focus-chain) — closest production analog of the re-anchor (re-injects every 6 messages) but pulses todos, not skill rules; documented UX backlash → lesson taken: pulse *stable* things (rules), not volatile ones (todos).
- [anthropics/claude-code#22421](https://github.com/anthropics/claude-code/issues/22421) — closed feature request documenting the periodic-refresh gap the re-anchor fills (reporter: ~50% compliance by tool call 40, near-zero by 60).
- arXiv [2512.10172 — Offscript](https://arxiv.org/abs/2512.10172) — auditor LLM identifies adherence failures in 86.4% of conversations. Validates that drift is widespread and worth detecting.
- [Michaelliv/pi-system-reminders](https://github.com/Michaelliv/pi-system-reminders) — reactive system-reminders SDK; same intervention shape as this hook's output.
