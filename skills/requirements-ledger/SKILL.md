---
name: requirements-ledger
description: Use whenever the user states anything carrying intent — an ask, a question, a constraint, a preference, a compound "do X, Y, and Z" (one row per conjunct), or an implicit ask embedded in prose. Maintains a USER-VISIBLE markdown ledger as the hard source of truth so nothing the user said is ever silently dropped; mirrors open items into the native task list on Claude Code; reconciles every item and ASKS before closing. Fires on every substantive user turn and before any completion claim.
effort: medium
tools: [Read, Edit, Write, TaskCreate, TaskUpdate, TaskList]
auto-install: true
model: sonnet
pulse_reminder: requirements-ledger — every user turn, decompose the message into ATOMIC items (each ask / question / conjunct / implicit ask = one row) in the visible .brainer/ledger/<sid>.md; never delete a row, only re-status; reconcile EVERY item and ASK before closing.
---

# requirements-ledger — nothing the user said gets dropped

The contract, in the user's words: **nothing the user says is ever silently
dropped until it is completed or the user closes it** — and *anything* carrying
intent counts (asks, questions, requirements, constraints, preferences, the
several items inside one message, implicit asks). When you think you are done you
**reconcile every item and ask the user before closing** — you never self-close.

You hold the source of truth in a **visible markdown ledger** the user can open.
`compliance-canary` is the mechanical enforcer: it independently captures each
user prompt and nudges if you stop maintaining the ledger or try to close with
open items (see [Cross-check](#cross-check-with-compliance-canary)). The file is
authoritative; do not rely on memory.

## The ledger file

**Path:** `.brainer/ledger/<sid>.md`, where `<sid> = sha256(session_id)[:16]`
(the same scheme `compliance-canary` uses, so both layers share the key).
Anchor to `$CLAUDE_PROJECT_DIR` (fallback: cwd). Per-session, **never** a single
shared repo file — concurrent sessions would clobber each other, which is the
exact silent-drop failure. Override the dir with `REQUIREMENTS_LEDGER_DIR`.
`.brainer/` is gitignored — the ledger is transient session state.

Print the file's absolute path in your first reply of the session and at every
reconcile, so the user always knows where to look.

**Format** — a checkbox list (not a table: pipes in user text break tables, and
one item per line lets you `Edit` a single row without rewriting the file). Three
fixed sections, in order. A trailing HTML comment carries the machine fields.

```markdown
# Requirements ledger — session a1b2c3d4e5f60718
Authoritative source of truth. The native task list is a mirror. Never delete a row — only re-status.

## Open
- [ ] (r4-a) Add a --json flag to install.sh <!-- id=r4-3f9c2a turn=4 type=ask status=open -->
- [~] (r4-b) Document the flag in the README <!-- id=r4-7b1e0d turn=4 type=ask status=pending-confirm -->
- [ ] (r6) What does the retry cap default to? <!-- id=r6-aa19f2 turn=6 type=question status=open -->
- [ ] (r7) (implicit) Fix the red build — confirm? <!-- id=r7-c40b88 turn=7 type=implicit status=open -->

## Deferred
- [ ] (r5) Migrate to the new config loader — deferred: needs prod DB creds <!-- id=r5-19ffaa turn=5 type=ask status=deferred -->

## Done (this session)
- [x] (r4-c) Wire the flag into the parser <!-- id=r4-d2e1f0 turn=4 type=ask status=done evidence=tests/test_cli.py::test_json_flag confirmed=2026-06-17 -->
- [x] (r2) Which host fires PreCompact? — answered turn 3 <!-- id=r2-8810ce turn=2 type=question status=answered -->
```

- **Fields:** `id` (`r{turn}-{sha6}`; for split conjuncts append `-a`, `-b`, …),
  `type` ∈ {ask, question, constraint, preference, implicit}, `status`, `turn`;
  `done`/`answered` carry an `evidence=` pointer; `deferred`/`declined` carry an
  inline `— <reason>`.
- **Checkbox:** `[ ]` open · `[~]` pending-confirm (your belief, not yet
  user-confirmed — **stays in Open**) · `[x]` done/answered (user-confirmed only).
- **Statuses:** `open → in_progress → pending-confirm → done` (questions:
  `open → answered`, the only legal close for a question). Side states:
  `deferred` (reason + who unblocks) and `declined` (reason). **A row is never
  deleted — only re-statused.** `deferred`/`declined` rows stay visible and are
  excluded from the "still-open at close" count (parked, not dropped).

## Every user turn (before doing the work)

1. **Extract every atomic item.** Ask yourself: "list every distinct thing this
   message commits me to." A compound message ("do X, Y, and Z"; "also…"; "and
   can you…") yields **one row per conjunct**. A question is its own `type=question`
   row. An implicit ask ("the build is still red" → "fix the build") is a
   `type=implicit` row.
2. **Capture vs. skip.** INCLUDE imperatives, questions, constraints, preferences,
   implicit asks. EXCLUDE pure acknowledgements / answers / continuations ("ok",
   "yes", "thanks", "go on", "do it", "proceed"). **When unsure, capture as
   `open`** — a stale visible row is recoverable; a dropped request is not.
3. **Write the changed rows only** (single-line `Edit`; `Write` the file the first
   time). Don't rewrite the whole file.
4. **Implicit rows: surface, never act silently** — "I read this as an implicit
   ask to fix the build — confirm, or I'll mark it declined." Unconfirmed implicit
   → `declined` (kept visible), never silently promoted to work.
5. On Claude Code, refresh the [native-task mirror](#native-task-mirror).

## At a completion claim (before you say "done")

Emit the reconcile block — for **each** row in `## Open` and `## Deferred`:

```
- <id> <text> → <what I did + verification evidence | why deferred + who unblocks>
```

then **exactly one** closure question ending in **"ok to close?"**. Rules:

- A `type=question` row closes only as `answered` (with the answer) — never `done`.
  Ask yourself per question: "did I ANSWER this, or just do adjacent work?"
- `done` requires the `evidence=` pointer populated.
- You mark `[~]` (pending-confirm); only the **user's** confirmation flips it to
  `[x]`. Never self-confirm.

## Native-task mirror

On Claude Code, mirror the file into the native task list so the user sees open
work live. **One-way, file → tasks**, at three checkpoints only: after a
post-turn file update, at the close-time reconcile, and on resume after
compaction. Store `metadata.ledger_id` on each task so you find-or-create instead
of duplicating. State mapping (file is authoritative; mapping is lossy):

| file status | native task |
|---|---|
| open | pending |
| in_progress | in_progress |
| pending-confirm | **in_progress** (never completed — completing pre-confirmation re-introduces self-close) |
| done / answered | completed |
| deferred / declined | pending, subject prefixed `[deferred]` / `[declined]` |

Never map a row to a *deleted* task — that visually implies it's gone.

## Authority & degradation

The **markdown file wins** on any divergence (e.g. after compaction, rebuild the
task list from the file). On hosts without native task tools (Codex,
Antigravity), the mirror step is a **silent no-op** — the file alone carries the
contract. Never error-loop calling absent tools.

## No opt-out — the guarantee is unconditional

There is **no opt-out and no opt-in**, by design. Capture is unconditional: every
request, question, and constraint is tracked until completed or the user closes
it. A prior design let the user disable tracking in-conversation ("no ledger");
it was removed because a misread of such a phrase would *silently switch the whole
guarantee off* — the one failure mode this skill exists to prevent. Nothing you
type can disable it. (The only kill is the operator-level
`COMPLIANCE_CANARY_DISABLED=1`, which disables the entire compliance-canary hook,
not the ledger specifically — a deliberate config act, never an in-chat phrase.)

## Cross-check with compliance-canary

Two ledgers, one authority. `compliance-canary`'s hidden per-session JSON
(`request_ledger`) is a **coarse** mechanical backstop — at most one row per
prompt. Your visible markdown file is the **atomic** truth — more rows (one per
conjunct/question/implicit). The hook therefore **never compares the two counts
for equality** (atomic > coarse is correct, not drift); its `ledger_not_materialized`
probe fires only when you have open captured items but show **no maintenance
activity** (no `Edit`/`Write`/`NotebookEdit` to `.brainer/ledger/<sid>.md` and no
`TaskCreate`/`TaskUpdate`).
Treat that probe, the wrap-up surfacing, and the `completion_without_closure` gate
as the mechanical floor — the visible file is the thing you actually keep current.

## Compatibility

Portable: the markdown file works on every host. The native-task mirror is
Claude-Code-only and degrades to a no-op elsewhere. The enforcement probe ships in
this skill's `drift_probes.json` and is read by `compliance-canary` (Claude Code).
