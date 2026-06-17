---
name: compliance-canary
description: Use when a long session drifts — the single always-on drift watcher: one UserPromptSubmit hook combining a periodic skill-rule re-anchor (every N turns) with symptomatic per-skill drift probes (filler creep, word-count growth, unverified done-claims, looping tool errors, rule fade). Absorbs the former skill-pulse; the re-anchor yields to a fired probe so the two never double-nag. Tune/disable via COMPLIANCE_CANARY_* env vars (SKILL_PULSE_* honored as aliases).
model: haiku
effort: low
tools: [Bash, Read, Write]
auto-install: true
pulse_reminder: drift detectors are watching — your recent reply is scanned each user turn against the active skills' drift_probes.json files.
---

# compliance-canary — the drift watcher

The single, non-optional drift defense for long sessions. One `UserPromptSubmit`
hook runs **two orthogonal mechanisms** in one process (skill-pulse was folded
in here 2026-06-16 — the leaner "one reactive hook instead of two" the eval
notes had flagged):

| # | Mechanism | When it speaks | Covers |
|---|---|---|---|
| 1 | **Symptomatic probes** | only when a drift symptom appears | filler, verbosity creep, unverified done-claims, looping tool errors, error-rate spikes |
| 2 | **Periodic re-anchor** | every Nth turn, unconditionally | rules that *fade* before any symptom shows — incl. rules with no probe |

Both emit into **one** `<system-reminder>` with a shared budget. On a turn where
a probe fires, the re-anchor **yields** (symptom correction is higher-signal and
itself re-anchors attention) — so the two never stack into consecutive nags.

Emergency off-switch: `COMPLIANCE_CANARY_DISABLED=1` (kills both). This is a
safety valve, not an install option — the skill is default-on (`auto-install:
true`) and meant to stay wired.

## Mechanism 1 — symptomatic probes

Every UserPromptSubmit, reads the last few assistant messages and recent tool calls from the session transcript, then runs **per-skill drift probes** against them. When a probe fires, injects a targeted corrective naming the violated rule and quoting the specific evidence.

Probes are declared by each skill in `<.claude/skills>/<skill>/drift_probes.json`. The canary discovers them on every run — no central registry.

### Probe kinds (v1)

#### `forbidden_regex`

Pattern match on recent assistant text. Fires on first match in the message window.

```json
{
  "kind": "forbidden_regex",
  "id": "filler-phrases",
  "pattern": "(?i)\\b(certainly|absolutely|of course)\\b",
  "message": "filler/pleasantry phrase detected — drop hedges, soft closings",
  "severity": "warn"
}
```

Use for: style drift (caveman pleasantries, marketing fluff, "as an AI" hedges, emoji creep).

#### `word_count_per_message`

Average words per assistant message over a sliding window. Fires when average exceeds threshold.

```json
{
  "kind": "word_count_per_message",
  "id": "word-creep",
  "threshold": 120,
  "window": 3,
  "severity": "warn"
}
```

Use for: terseness drift (caveman-ultra creep, explanation bloat).

#### `claim_without_evidence`

Looks for claim words in the last assistant message AND checks that a verification-style tool call appears in the recent tool-use history. Fires when claim present but evidence absent.

```json
{
  "kind": "claim_without_evidence",
  "id": "unverified-done",
  "claim_pattern": "(?i)\\b(done|fixed|complete|passes|verified)\\b",
  "verify_tools": ["Bash"],
  "verify_keywords": ["test", "pytest", "make", "build", "check", "curl"],
  "lookback_tool_uses": 5,
  "severity": "warn"
}
```

Use for: verify-before-completion drift (claiming success without running a check).

#### `repeated_tool_error` *(v1.7)*

Scans recent `is_error` tool_results (user-type events — invisible to the message detectors) for a recurring error signature. Added after transcript mining found one signature ("File has not been read yet") was 15 of 18 tool errors across 5 sessions.

```json
{
  "kind": "repeated_tool_error",
  "id": "edit-without-read",
  "pattern": "File has not been read yet",
  "min_count": 2,
  "severity": "warn"
}
```

Use for: any tool error the agent keeps re-triggering after the native error message failed to break the habit.

#### `user_correction` *(v1.7)*

Matches the user's CURRENT prompt (not the transcript) against correction patterns ("no, use X", "that's wrong", "I said …"). Fires the harvest reflex at the exact turn the correction lands — corrections are the highest-value learning source (exp1: feedback lift +0.667) but the prose-only reflex under-fires. Lineage: BayramAnnakov/claude-reflect; ships in `wiki-memory/drift_probes.json`.

```json
{
  "kind": "user_correction",
  "id": "user-correction",
  "pattern": "(?i)(?:^\\s*no[,. ]|don'?t use\\b|i said\\b|that'?s wrong)",
  "severity": "warn"
}
```

Use for: routing corrections into write-gate → wiki-memory instead of losing them to the session.

#### `trajectory_drift` *(v1.8)*

Session-level tool-error RATE over the transcript tail (tool_use count vs `is_error` tool_results, same window). Catches error-loop drift that `repeated_tool_error` misses when each retry fails differently. Cheapest form of trajectory calibration (lineage: HTC, arXiv 2601.15778) — no model, no training. Ships default-on in `compliance-canary/drift_probes.json`.

```json
{
  "kind": "trajectory_drift",
  "id": "traj-error-rate",
  "min_tool_calls": 8,
  "max_error_rate": 0.25
}
```

Use for: stop-and-reassess when the agent is thrashing (retry loops, wrong-cwd cascades, schema-mismatch storms). `min_tool_calls` guards cold starts.

#### `prompt_intent` *(v1.11)*

Same mechanism as `user_correction` (matches the CURRENT user prompt) but for a PRE-TASK nudge rather than a correction: a skill fires the moment the prompt describes the situation it governs — e.g. `loop-engineering` on a "build a self-correcting automation" or "spawn parallel agents" prompt, or `eval-gate` on "is this good enough / would this pass". Measured rationale: spontaneous Skill-tool invocation is unreliable (blind agents don't auto-load a skill even with a strong description), so a mechanical trigger beats hoping the model remembers. Ships in `loop-engineering/drift_probes.json` (loop-build + fleet-orchestration intent) and `eval-gate/drift_probes.json`.

```json
{
  "kind": "prompt_intent",
  "id": "loop-build-intent",
  "pattern": "(?i)\\b(iterate|retry)\\b[^.?!]{0,30}\\buntil\\b",
  "severity": "warn"
}
```

#### `early_stop` *(v1.11)*

Fires when the agent's LAST turn ended on a forward-looking PROMISE ("I'll now implement…", "let me start…") with no completion claim, no question, and no tool call that turn — it narrated the next step instead of doing it. Suppressed when the closing turn called a tool (work happened), reported completion (a legit "next steps" note), or asked the user a question (a legitimate pause). The anti-early-stop reflex; ships in `verify-before-completion/drift_probes.json`. Overridable: `pattern` (the promise), `done_pattern` (suppress on completion), `question_pattern` (suppress on a question).

```json
{
  "kind": "early_stop",
  "id": "early-stop-on-promise",
  "severity": "warn"
}
```

#### `completion_without_closure` *(v1.11)*

The closure gate — mirror of `early_stop`. Fires when the agent's last turn makes a TERMINAL "whole task is finished" claim ("all done", "task is complete", "ready to ship") but does NOT ask the user to confirm closure — i.e. it self-closes. Suppressed when the message invites confirmation ("shall I close this?", "anything else?") or is only a mid-task milestone (the claim regex is tighter than `claim_without_evidence`'s, which fires on any sub-step "done"). Distinct from `claim_without_evidence` (that is about EVIDENCE; this fires even when verification ran, because a verified-done still must be offered to the user). Ships in `verify-before-completion/drift_probes.json`. Overridable: `claim_pattern` (terminal claim), `ask_pattern` (closure invite that suppresses).

```json
{
  "kind": "completion_without_closure",
  "id": "completion-without-closure",
  "severity": "warn"
}
```

## Mechanism 2 — periodic re-anchor

Every `COMPLIANCE_CANARY_PULSE_EVERY` turns (default **4**, paper-calibrated — arXiv [2510.07777](https://arxiv.org/html/2510.07777) tests injections at turns 4 + 7 of 10-turn convos), the hook unconditionally re-states the active skills' rules so they stay in effective attention. This is the *prevention* half: it catches rules that fade **before** any symptom shows, and rules that have no symptom probe at all.

A skill participates iff its `SKILL.md` frontmatter declares a `pulse_reminder:` line — curated, not noisy:

```yaml
---
name: caveman-ultra
description: Terse output style ...
pulse_reminder: terse output — drop filler, hedging, pleasantries, and soft closings.
---
```

Skills without `pulse_reminder` are silent in the re-anchor (force-include via `COMPLIANCE_CANARY_PULSE_SKILLS=a,b`, which falls back to each skill's `description` first sentence). Capped at `MAX_SKILLS_IN_PULSE=8`.

**The re-anchor yields to a fired probe.** On a turn that both hits the cadence *and* trips a probe, only the targeted corrective is emitted — the generic re-anchor is skipped that turn (it returns next cadence). One injection, never two. This is what folding skill-pulse in bought: a single global anti-nag budget that two separate hooks could not coordinate.

Why one re-anchor payload and not a re-read of the bodies: the one-line reminders cost ~97% fewer tokens per 1000 turns (~76k) than re-injecting the 8 pulse skills' full `SKILL.md` bodies at the same cadence (~2.59M).

## Install

Claude Code (project-local):

```bash
bash skills/compliance-canary/tools/install.sh --project
```

Wires `tools/hook.sh` into `.claude/settings.json` under `UserPromptSubmit` — a single hook running both mechanisms. (`prompt-triage` may also wire `UserPromptSubmit`; the hooks fire in sequence, each independent.)

## How a skill opts in

- **A symptom probe** → drop a `drift_probes.json` next to the skill's `SKILL.md`.
- **The periodic re-anchor** → add a `pulse_reminder:` line to the skill's frontmatter (see Mechanism 2).

A skill can do both. `drift_probes.json` example for caveman-ultra:

```json
[
  {
    "kind": "forbidden_regex",
    "id": "filler-phrases",
    "pattern": "(?i)\\b(certainly|sounds good|i'll go ahead)\\b",
    "message": "filler phrase — drop it"
  },
  {
    "kind": "word_count_per_message",
    "id": "word-creep",
    "threshold": 120,
    "window": 3
  }
]
```

Two bootstrapped skills ship probes out of the box: `caveman-ultra` (filler-regex + word-creep) and `verify-before-completion` (claim-without-evidence). Other skills opt in over time.

## Tuning

Env vars (all optional). `SKILL_PULSE_*` names are honored as back-compat aliases from the pre-merge skill-pulse.

| Var | Default | Effect |
|---|---|---|
| `COMPLIANCE_CANARY_DISABLED=1` | — | emergency off-switch — kills **both** mechanisms |
| `COMPLIANCE_CANARY_COOLDOWN` | 3 | turns to suppress the same probe after it fires |
| `COMPLIANCE_CANARY_PULSE_EVERY` | 4 | re-anchor cadence (floored to 2); `0` disables **just** the re-anchor. Alias: `SKILL_PULSE_EVERY` |
| `COMPLIANCE_CANARY_PULSE_DISABLED=1` | — | disable just the re-anchor (probes still run). Alias: `SKILL_PULSE_DISABLED` |
| `COMPLIANCE_CANARY_PULSE_SKILLS=a,b` | — | force-include skills in the re-anchor. Alias: `SKILL_PULSE_SKILLS` |
| `COMPLIANCE_CANARY_STATE_DIR` | `.brainer/compliance-canary` | override state location |
| `COMPLIANCE_CANARY_SKILLS_ROOT` | `.claude/skills` | override skills lookup root. Alias: `SKILL_PULSE_SKILLS_ROOT` |

## Offline analyzer (`measure.py`)

Runs the same probes against any transcript JSONL without installing the hook. Useful for baselining past sessions and tuning thresholds:

```bash
python3 skills/compliance-canary/tools/measure.py ~/.claude/projects/<proj>/<sid>.jsonl
```

Prints per-probe trigger counts and the offending snippets. No state writes, no side effects.

## Rules

- Read at most `TRANSCRIPT_LINE_CAP=400` trailing lines of the transcript (bound transcript-read cost).
- Anti-spam: each probe is suppressed for `COMPLIANCE_CANARY_COOLDOWN` turns after it fires.
- Cap symptomatic output at `MAX_PROBES_TRIGGERED=4` and the re-anchor at `MAX_SKILLS_IN_PULSE=8`. On a shared turn the re-anchor yields, so output never exceeds one block.
- The re-anchor reads no transcript and the probes need no frontmatter — one dir-walk feeds both.
- The probe phase runs under a `PROBE_TIMEOUT_SECONDS=1.5` SIGALRM budget: a catastrophic-backtracking regex in some skill's `drift_probes.json` degrades to "no probes this turn" rather than wedging the prompt. (Author regexes are trusted-ish but this is the single mandatory hook — never let it hang.)
- Hardened against malformed hook input: a non-object JSON payload or a non-string `session_id` is handled, not crashed. State updates flock-guarded. **Always exit 0** — a non-zero `UserPromptSubmit` exit would block the user's prompt.

## Files

```
tools/
├── hook.sh        # UserPromptSubmit shell shim
├── hook.py        # probes + periodic re-anchor + state (one process)
├── install.sh     # wires UserPromptSubmit into project-local .claude/
├── test.sh        # regression suite (56 cases: probes + re-anchor + hardening)
└── measure.py     # standalone offline probe analyzer
```

## Compatibility

**Claude Code only** — `UserPromptSubmit` is a Claude-Code-specific event. The top-level `./install.sh` symlinks the folder into all four host dirs for description visibility; only Claude Code wires the hook.

## Known gaps

- Probe detectors are syntactic — they catch keyword/structural signals but miss semantic drift (a paraphrased "done" without claim-word match). A judge-style probe using a tiny LLM is the natural next add (the `llm_judge` kind, currently deferred).
- `edit_count_per_turn` (lean-execution drift) and `tool_choice_drift` (model picks Write when rule says Edit) are not yet detector kinds. Easy adds when needed.
- The re-anchor is cadence-based (turn count), not staleness-aware: it re-states rules on schedule even if attention hasn't actually decayed. It yields to probes, but on a quiet long session it still fires every N turns. A true staleness signal would need a cheap per-rule "faded?" probe — none exists yet.
