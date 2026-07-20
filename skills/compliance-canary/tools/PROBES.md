# compliance-canary — probe-kind reference

Author reference for the symptomatic probes (Mechanism 1). Each skill declares
concrete probe *instances* in its own `<skill>/drift_probes.json`; this file
documents the probe **kinds** (the JSON shape an author writes against) and what
drift each one targets.

**Source of truth:** `tools/hook.py`'s `DETECTORS` registry is the authoritative
behavior for every kind. This file and each skill's `drift_probes.json` both
shadow it — keep all three in sync (the body lists the kind *names*, this file
the *schemas*, `hook.py` the *implementation*).

## Probe kinds (v1)

### `forbidden_regex`

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

### `word_count_per_message`

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

### `claim_without_evidence`

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

### `repeated_tool_error` *(v1.7)*

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

### `user_correction` *(v1.7)*

Matches the user's CURRENT prompt (not the transcript) against correction patterns ("no, use X", "that's wrong", "I said …"). It surfaces the correction at the exact turn it lands; if task-retrospective is armed, record it as evidence, and if persistence is explicitly selected, route the lesson through write-gate. Context-safe matching (2026-07-20): before matching, the prompt has fenced code blocks, inline backtick spans, double-quoted spans, and markdown `>` blockquote lines stripped (`hook.py`'s `strip_quoted_and_code`) — a correction-shaped phrase the user is merely quoting/pointing at (a pasted article, a code fence) is not a live correction directed at the agent. This stripping applies only to the `user_correction` kind, not `prompt_intent` below, which shares the same detector function. When the correction ledger is ARMED (task-audit mode active via `.brainer/task-retrospective/current.json`, or `COMPLIANCE_CANARY_CORRECTION_LEDGER=1`), a fire ALSO opens a correction-ledger item (Mechanism 4, LEARNING_CONTRACT §2) — closeout-blocking until a `write_gate.py` bank call in **command position** is observed (see `hook.py`'s `_bash_call_banks_correction` — a bare substring like `echo write_gate.py` or a `--help`/`-h` invocation does NOT resolve it) or the user explicitly closes it; see `hook.py`'s `update_correction_ledger`. Unarmed (the default frontier posture, 2026-07-20), the ledger does not open: the correction is acted on and acknowledged in the reply only. Lineage: BayramAnnakov/claude-reflect; ships in `wiki-memory/drift_probes.json`.

```json
{
  "kind": "user_correction",
  "id": "user-correction",
  "pattern": "(?i)(?:^\\s*no[,. ]|don'?t use\\b|i said\\b|that'?s wrong)",
  "severity": "warn"
}
```

Use for: preventing corrections from being ignored without turning every correction into an automatic memory write.

### `trajectory_drift` *(v1.8)*

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

### `prompt_intent` *(v1.11)*

Same mechanism as `user_correction` (matches the CURRENT user prompt) but for a PRE-TASK nudge rather than a correction: a skill fires the moment the prompt describes the situation it governs — e.g. `loop-engineering` on a "build a self-correcting automation" or "spawn parallel agents" prompt, or `eval-gate` on "is this good enough / would this pass". Measured rationale: spontaneous Skill-tool invocation is unreliable (blind agents don't auto-load a skill even with a strong description), so a mechanical trigger beats hoping the model remembers. Ships in `loop-engineering/drift_probes.json` (loop-build + fleet-orchestration intent) and `eval-gate/drift_probes.json`.

```json
{
  "kind": "prompt_intent",
  "id": "loop-build-intent",
  "pattern": "(?i)\\b(iterate|retry)\\b[^.?!]{0,30}\\buntil\\b",
  "severity": "warn"
}
```

### `early_stop` *(v1.11)*

Fires when the agent's LAST turn ended on a forward-looking PROMISE ("I'll now implement…", "let me start…") with no completion claim, no question, and no tool call that turn — it narrated the next step instead of doing it. Suppressed when the closing turn called a tool (work happened), reported completion (a legit "next steps" note), or asked the user a question (a legitimate pause). The anti-early-stop reflex; ships in `compliance-canary/drift_probes.json` (rehomed 2026-07-19 from `verify-before-completion` — that skill remains for the FULL manual workflow, but the mechanical probe is canary-owned). Overridable: `pattern` (the promise), `done_pattern` (suppress on completion), `question_pattern` (suppress on a question).

```json
{
  "kind": "early_stop",
  "id": "early-stop-on-promise",
  "severity": "warn"
}
```

### `completion_without_closure` *(v1.11)*

The closure gate — mirror of `early_stop`. Fires when the agent's last turn makes a TERMINAL "whole task is finished" claim ("all done", "task is complete", "ready to ship") but does NOT ask the user to confirm closure — i.e. it self-closes. Suppressed when the message invites confirmation ("shall I close this?", "anything else?") or is only a mid-task milestone (the claim regex is tighter than `claim_without_evidence`'s, which fires on any sub-step "done"). Distinct from `claim_without_evidence` (that is about EVIDENCE; this fires even when verification ran, because a verified-done still must be offered to the user). Ships in `compliance-canary/drift_probes.json` (rehomed 2026-07-19 from `verify-before-completion` — that skill remains for the FULL manual workflow, but the mechanical probe is canary-owned). Overridable: `claim_pattern` (terminal claim), `ask_pattern` (closure invite that suppresses).

```json
{
  "kind": "completion_without_closure",
  "id": "completion-without-closure",
  "severity": "warn"
}
```
