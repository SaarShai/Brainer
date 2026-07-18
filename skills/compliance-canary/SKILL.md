---
name: compliance-canary
description: "Use when a long session may drift or needs verification-compliance monitoring. Frontier defaults to silent intent state plus one compact, compliance-aware verification probe; shadow measures suppressed legacy probes; legacy preserves rollback behavior; off is a mutation-free control."
model: haiku
effort: low
tools: [Bash, Read, Write]
auto-install: true
---

<!-- split-justified -->

# compliance-canary — profiled drift watcher

## Profiles

Set `COMPLIANCE_CANARY_PROFILE=frontier|shadow|legacy|off` (default:
`frontier`):

- `frontier` silently records pending intent and emits only
  `verify-before-completion:claim-without-evidence`, plus pending intent at a
  genuine wrap-up. There is no pulse, generic style probe, correction nag, or
  escalation wrapper.
- `shadow` makes the same task-facing decisions and emits byte-identical output
  while evaluating suppressed legacy probes into redacted telemetry.
- `legacy` preserves the complete pre-profile behavior below for rollback.
- `off` exits before state, lock, ledger, telemetry, transcript, or activation
  mutation and is the clean experimental control.

`COMPLIANCE_CANARY_PROBE_IDS=skill:id,...` selects exact probes (not entire
skills). In frontier/shadow it overrides the compact default. Telemetry defaults
to `.brainer/compliance-canary/telemetry.jsonl` and contains only session hash,
turn, mechanism, probe ID, emitted flag, exact injected UTF-8 bytes, and content
hash—never prompt or transcript text.

The compact verification probe accepts evidence only when a tool use has a
correlated successful result, the result is newer than the last material
mutation, and its class matches the claim (`test/build`, `filesystem/diff`,
`live service`, or `visual`). Typed-but-unrun commands, failed results, stale or
pre-edit checks, incidental output keywords, and wrong evidence classes do not
suppress it.

Notification evidence boundary (frontier/shadow only, 2026-07-18; hardened
2026-07-19): when the current `UserPromptSubmit` payload is a
substrate-authored `<task-notification>` reporting terminal SUCCESS
(completed status / exit code 0) for a self-contained job kind — timer
wakeup, background command, or advisor consult — and the notification
carries its own result content or an output-file pointer, the
`claim_without_evidence` probe does not emit for that turn: the notification
IS the evidence boundary and the agent authored no claim on it. The
predicate is fail-open — any classification uncertainty (a user ask riding
along, a failed/killed job, an unrecognized job kind, or world-state
assertion prose such as "files moved" / "tests pass" / "DONE" / "READY FOR
JUDGING" — the implementation-subagent shape whose forwarded claim is the
guard's one proven live catch) leaves the probe armed exactly as before.
Hardening (two adversarial sense-checks):

- **Provenance.** Suppression additionally requires the notification's
  task-id string to appear EARLIER in the session transcript (e.g. in the
  tool_result that announced the background task). A pasted, syntactically
  valid `<task-notification>` has no such anchor and fails open — the turn
  fires exactly as before.
- **Deferred fire.** Suppression never destroys a fire, only defers it: the
  suppressed probe is still EVALUATED on the notification turn, and a
  would-have-fired is persisted as a `deferred_fires` marker in session
  state. On the next `UserPromptSubmit` that is NOT a qualifying
  notification, the probe emits once (marker cleared), regardless of
  message-window slide.
- **Pending content.** A pointer-only success records a
  `notification_pending_content` entry (output-file path + kind + turn +
  timestamp) in the session state file. On later turns an entry clears once
  the transcript shows the output file being read back (path substring in a
  tool_use input or tool_result content); entries still unresolved are
  listed, one compact line each (`<kind> output never read: <path>`), at the
  existing wrap-up surface — no new emission point.

Every suppression is logged to telemetry as a `suppressed_notification`
event (emitted=false) so the counterfactual stays measurable. `legacy`
deliberately keeps the pre-fix behavior for rollback.

The remainder of this document describes `legacy` rollback behavior.

The single, non-optional drift defense for long sessions. One `UserPromptSubmit`
hook runs **four orthogonal mechanisms** in one process (skill-pulse was folded
in here 2026-06-16 — the leaner "one reactive hook instead of two" the eval
notes had flagged; the request ledger was added 2026-06-17; the correction
ledger closes the LEARNING_CONTRACT §2 gap — a user correction must become a
durable artifact before the task closes):

| # | Mechanism | When it speaks | Covers |
|---|---|---|---|
| 1 | **Symptomatic probes** | only when a drift symptom appears | filler, verbosity creep, unverified done-claims, self-closing without asking, looping tool errors, error-rate spikes |
| 2 | **Periodic re-anchor** | every Nth turn, unconditionally | rules that *fade* before any symptom shows — incl. rules with no probe |
| 3 | **Request ledger** | at wrap-up turns (+ on cadence) | a user request silently dropped before it was completed or the user closed it |
| 4 | **Correction ledger** | every turn it is non-empty | a user correction closed out without being banked as a durable rule + gate + exemplar (LEARNING_CONTRACT §2) |

All four emit into **one** `<system-reminder>` with a shared budget. On a turn
where a probe fires, the periodic re-anchor **yields** (symptom correction is
higher-signal and itself re-anchors attention) — so the two never stack into
consecutive nags. The request ledger does NOT yield at a wrap-up turn: surfacing
still-open requests precisely as the agent moves to close is the whole point.
The correction ledger likewise does not yield — it is closeout-blocking, so it
surfaces every turn it holds an open item.

Legacy emergency switch: `COMPLIANCE_CANARY_DISABLED=1`. For experiments use
`COMPLIANCE_CANARY_PROFILE=off`, whose no-mutation contract is tested.

Deep-dive reference: [REFERENCE.md](REFERENCE.md) — the offline `measure.py` analyzer, host compatibility notes, and known gaps.

## Mechanism 1 — symptomatic probes

Every UserPromptSubmit, reads the last few assistant messages and recent tool calls from the session transcript, then runs **per-skill drift probes** against them. When a probe fires, injects a targeted corrective naming the violated rule and quoting the specific evidence.

Probes are declared by each skill in `<.claude/skills>/<skill>/drift_probes.json`. The canary discovers them on every run — no central registry.

### Probe kinds (v1)

Each kind is the JSON shape an author writes in their skill's `drift_probes.json`. Full schema + per-field semantics for every kind: [`tools/PROBES.md`](tools/PROBES.md) (`hook.py`'s `DETECTORS` registry is the authoritative behavior).

- **`forbidden_regex`** — regex on recent assistant text → style drift (pleasantries, fluff, "as an AI" hedges, emoji creep).
- **`word_count_per_message`** — avg words/msg over a window → terseness drift (caveman-ultra creep, explanation bloat).
- **`claim_without_evidence`** — a claim word with no verify-style tool call in recent history → [verify-before-completion](../verify-before-completion/SKILL.md) drift.
- **`repeated_tool_error`** *(v1.7)* — a recurring `is_error` signature → a tool error the agent keeps re-triggering.
- **`user_correction`** *(v1.7)* — current prompt matches a correction pattern → surface it so it isn't ignored (route the lesson through [write-gate](../write-gate/SKILL.md)) and open a closeout-blocking correction-ledger item (Mechanism 4, LEARNING_CONTRACT §2) until it is banked or user-closed.
- **`trajectory_drift`** *(v1.8)* — session tool-error RATE over the tail → thrashing (retry loops, schema-mismatch storms).
- **`prompt_intent`** *(v1.11)* — current prompt matches a governed situation → a PRE-TASK skill nudge (spontaneous Skill invocation is unreliable, so fire mechanically).
- **`early_stop`** *(v1.11)* — last turn is a forward-looking promise with no tool/claim/question → the anti-early-stop reflex ([verify-before-completion](../verify-before-completion/SKILL.md)).
- **`completion_without_closure`** *(v1.11)* — a terminal done-claim without asking the user to confirm closure → the self-close gate ([verify-before-completion](../verify-before-completion/SKILL.md)).

### Wrap-up learning nudges (`workflow_nomination`)

At a wrap-up turn — the agent's last message reads as a completion claim, past a tool-call floor, with a substantive Edit/Write or a non-boilerplate Bash this window — the `workflow_nomination` probe fires a single ADVISORY nudge so a finished non-trivial workflow doesn't pass unlearned. (The detector kind lives in `hook.py`; the probe instance + message text are shipped by [`learn-skill`](../learn-skill/SKILL.md)'s `drift_probes.json`, so the nudge wording is maintained there, not here.) It suggests two routes, whichever fits:

- **`/learn`** — capture the workflow as a reusable skill ([learn-skill](../learn-skill/SKILL.md)); write-gate + dedup in the `/learn` flow decide whether it earns one.
- **`/retro`** — retrospect the task when it's one that repeats or is worth learning from ([task-retrospective](../task-retrospective/SKILL.md)); it decides whether the lesson belongs in a wiki fact, a gate, a skill, or an always-on rule.

Both are suggestions inside a `<system-reminder>` — the canary NEVER auto-runs `/learn` or `/retro`. They share the one wrap-up detector (one suppression/budget path) so the two never double-nag.

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

## Mechanism 3 — request ledger

Probes and the re-anchor are *stateless against intent* — they cannot tell that
a thing the user asked for three turns ago was quietly dropped. The ledger is the
stateful guard for that: **no user request is dropped until it is completed or the
user says so.**

Lifecycle (per-session state under `COMPLIANCE_CANARY_STATE_DIR`, key
`request_ledger`):

- **Add.** Each substantive user prompt is recorded as an OPEN item `{id, turn,
  text}`. Pure acknowledgements/answers ("ok", "yes", "thanks", "go on") are
  skipped; a closure phrase is handled below, not appended.
- **Surface.** Open items are re-injected when the agent's last message reads as a
  TERMINAL completion claim (a wrap-up turn — "you appear to be wrapping up, but N
  requests are still OPEN — do NOT self-close…"), and, more quietly, on the
  re-anchor cadence when nothing else fired.
- **Close.** An item leaves the ledger **only when the user says so** — a closure
  phrase in the user's prompt ("close it", "that's all", "drop that", "ship it",
  "we're done"). `close all / everything` clears the ledger; otherwise the
  most-recent open item is closed. The closure is confirmed back ("closed N
  request(s) on your say-so").

**The hook never judges semantic completion itself.** It tracks text + turns
mechanically and pushes the semantic reconciliation to the model (which has the
context) via the surfaced reminder. This is deliberate — a syntactic detector
cannot reliably decide "is request X actually done", and guessing would silently
close real work. The contract is exactly the user's words: open until *completed
and the user confirms* (the `completion_without_closure` gate forces the agent to
*ask*; the user's "yes, close it" is what prunes the ledger). The two interlock —
the gate produces the ask, the ask produces the user's closure, the closure prunes
the ledger.

Closure mapping is a heuristic (most-recent-open, or all on "everything") — the
hook cannot map "yes that one's done" to a specific item, so it errs toward
keeping items open (a stale-but-visible item is recoverable; a silently-dropped
one is not). **There is no opt-out and no per-ledger disable** — capture is
unconditional (user directive: "never switch off, never opt out"); the only kill
is the whole-hook `COMPLIANCE_CANARY_DISABLED=1`. Stored items are
capped at `LEDGER_STORE_CAP=50`, surfaced at `LEDGER_SHOW_MAX=8` (with "+N more
open").

## Verbatim intent log

The capture side of the no-drop guarantee (target architecture L0 "Intent
log"). On every `UserPromptSubmit` the hook appends the **user-authored
remainder** of the prompt — after the same harness-block stripping the ledger
uses, so `<task-notification>` bodies and command transcripts are never
captured, and a pure harness-notification turn (empty remainder) writes no
record — to `.brainer/intent/<session_id>.jsonl` (git-ignored; follows a
`COMPLIANCE_CANARY_STATE_DIR` override as a sibling) as one
`{"turn", "ts", "sha256", "text"}` record per line. The text is verbatim and
full-length — unlike the ledger's 140-char mirror — with a sha256 integrity
anchor. Mechanical, zero LLM, zero injected bytes, append-only, best-effort:
a capture failure logs to stderr and never blocks the hook.

**Consumers.** Today: the Mechanism 3 wrap-up surface quotes the user's own
captured words (with turn numbers, truncated to the existing per-item budget)
from this log instead of ledger state. Planned: close-boundary reconciliation
mapping every captured intent to satisfied / deferred / uncovered.

**No opt-out.** Capture is unconditional by standing user directive ("never
switch off, never opt out") — there is no flag, and it runs ahead of even the
whole-hook `COMPLIANCE_CANARY_DISABLED=1` valve (which silences reminders but
must never stop the record). The single exception is profile `off`: the
experimental control arm, which exits before ANY mutation and so writes no
intent records.

## Mechanism 4 — correction ledger

[`LEARNING_CONTRACT`](../_shared/LEARNING_CONTRACT.md) §2: a user correction is
**closeout-blocking** — it must become a durable artifact (rule + gate +
exemplar, SCOPE-classified per §1) before the task closes, unconditionally, not
only "if a retrospective is armed". The `user_correction` probe (Mechanism 1)
already detects the correction at the turn it lands; the correction ledger is
the stateful guard that keeps it from being forgotten — mirroring the request
ledger's shape exactly, one mechanism level up.

Lifecycle (per-session state under `COMPLIANCE_CANARY_STATE_DIR`, key
`correction_ledger`):

- **Open.** Every fired `user_correction` probe (any skill's) opens an OPEN
  item `{id, turn, text}` — unconditional capture, the same no-opt-out posture
  as Mechanism 3. This is unconditional even when `COMPLIANCE_CANARY_PROBE_SKILLS`
  scopes DISPLAY to a different allowlist: the allowlist filters which fired
  probes are shown in the drift-signal block, but every discovered
  `user_correction` probe is still evaluated for ledger OPENING regardless of
  that filter — an allowlist that happens to exclude a skill's `user_correction`
  probe must never silently prevent its corrections from ever entering the
  ledger (this was a confirmed hole; fixed by evaluating `user_correction`
  probes on a path the allowlist doesn't reach, see `hook.py`'s `ledger_probes`).
- **Surface.** Unlike the request ledger (which waits for a wrap-up turn or
  drift coupling), an open correction is surfaced **every turn** it is
  non-empty — "closeout-blocking" means it does not wait for the agent to
  believe it is done.
- **Close.** An item leaves the ledger when (a) a Bash tool call banking the
  lesson is observed — `write_gate.py` (the quality gate §2 requires) or
  `wiki.py new` (materializing the durable artifact; `wiki.py` has no `update`
  subcommand — `new` is the only page-writing verb it exposes) — **actually
  ran and produced a passing execution-evidence signature**, which resolves
  ALL open corrections, or (b) the user explicitly closes it (the same closure
  phrasing as Mechanism 3: "close it", "that's all", …), for a correction the
  agent judges already handled outside the banking tools.

**The hook never judges whether the banked lesson is any good** — only whether
a banking tool call ACTUALLY RAN. There is no auto-resolve on the mere passage
of turns: an unbanked correction stays OPEN indefinitely until one of the two
close paths above fires.

**Bank-resolution requires EXECUTION EVIDENCE, not just command text.** Two
prior fix attempts were each defeated adversarially:

1. A bare substring match let `echo write_gate.py`, `wiki.py new --help`, and
   `grep write_gate.py x` all falsely resolve a closeout-blocking correction —
   none of them ran the gate. Fixed by requiring **command-position invocation
   shape** (the matched token must be the thing actually invoked in a shell
   segment split on `&&`/`||`/`;`/`|`, after stripping leading
   env-assignments/`sudo`, optionally behind a `python`/`python3`/`bash`/`sh`
   interpreter; a segment containing `--help`/`-h` is rejected).
2. Invocation shape alone is still **text-trust**: `CMD="python3
   .../write_gate.py gate --text x"` (a bare shell variable assignment — the
   command string matches, but nothing executes) and `false && python3
   .../write_gate.py gate ...` (a short-circuited compound — the second
   segment still "looks like" an invocation even though `&&` guarantees it
   never runs) both resolved a correction without the gate ever running.
   Command-string matching cannot tell a typed-but-never-run command from a
   genuine one.

The fix: the hook now requires the SAME Bash `tool_use` to have a **paired
`tool_result`** (correlated by `tool_use_id`, the same id every real Claude
Code transcript carries — confirmed against a live transcript fixture) whose
content carries a real execution signature:

- `write_gate.py score`/`explain` (or any subcommand with `--json`) prints a
  `PASSED: …` / `REJECTED: …` verdict (JSON: the `"verdict"` field). **`gate`
  alone (no `--json`) prints nothing to stdout — only an exit code** — so a
  banking call must use `--json` or `score`/`explain` for the hook to see a
  verdict at all; a bare `gate` invocation carries no signature to detect,
  banked or not.
- `wiki.py new` prints JSON with a `"created": "<path>"` key on success, or
  `"refused": "REFUSED: …"` on a write-gate/overlap refusal.

A `REJECTED`/`REFUSED` result is **not** a bank signature — the gate ran but
refused the candidate, so the correction stays OPEN (a rejected banking
attempt is not a successful banking). A command with matching invocation shape
but no observed `tool_result` in the transcript window never resolves anything
either — invocation shape narrows which Bash calls are worth checking, but
shape alone no longer resolves the ledger.

## Install

Claude Code (project-local):

```bash
bash skills/compliance-canary/tools/install.sh --project
```

Wires `tools/hook.sh` into `.claude/settings.json` under `UserPromptSubmit` — a single hook running all four mechanisms. (`prompt-triage` may also wire `UserPromptSubmit`; the hooks fire in sequence, each independent.)

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
| `COMPLIANCE_CANARY_PROFILE` | `frontier` | `frontier`, `shadow`, `legacy`, or mutation-free `off` |
| `COMPLIANCE_CANARY_PROBE_IDS` | frontier verification probe | exact comma-separated `skill:id` selection; replaces skill-level selection |
| `COMPLIANCE_CANARY_TELEMETRY_PATH` | state dir `telemetry.jsonl` | redacted append-only telemetry path |
| `COMPLIANCE_CANARY_DISABLED=1` | — | legacy break-glass: silences drift detection and all reminders, but the turn is still counted and the prompt still recorded to the request ledger first (state mutation happens BEFORE the valve by design); only profile `off` is fully mutation-free |
| `COMPLIANCE_CANARY_COOLDOWN` | 3 | turns to suppress the same probe after it fires |
| `COMPLIANCE_CANARY_PULSE_EVERY` | 4 | re-anchor cadence (floored to 2); `0` disables **just** the re-anchor. Alias: `SKILL_PULSE_EVERY` |
| `COMPLIANCE_CANARY_PULSE_DISABLED=1` | — | disable just the re-anchor (probes still run). Alias: `SKILL_PULSE_DISABLED` |
| `COMPLIANCE_CANARY_PULSE_SKILLS=a,b` | — | force-include skills in the re-anchor. Alias: `SKILL_PULSE_SKILLS` |
| `COMPLIANCE_CANARY_STATE_DIR` | `.brainer/compliance-canary` | override state location |
| `COMPLIANCE_CANARY_SKILLS_ROOT` | `.claude/skills` | override skills lookup root. Alias: `SKILL_PULSE_SKILLS_ROOT` |

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
├── hook.py        # probes + periodic re-anchor + request ledger + correction ledger + state (one process)
├── install.sh     # wires UserPromptSubmit into project-local .claude/
├── test.sh        # regression suite: probes + re-anchor + ledgers + hardening
├── test_profiles.py # frontier/shadow/off + evidence freshness/class gates
└── measure.py     # standalone offline probe analyzer
```

REFERENCE.md — deep-dive: offline `measure.py` usage, host compatibility, known gaps.
