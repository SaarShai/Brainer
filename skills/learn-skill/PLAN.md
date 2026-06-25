# PLAN — `learn-skill` (Brainer's `/learn`)  [GLM-reviewed]

## WHAT / WHY
Brainer can *retrospect* (task-retrospective) but cannot **ingest a pointed-at source
into a skill** (skill-creator was removed). Hermes' `/learn` fills exactly that gap.
Build a Brainer-native `learn-skill` that turns a source (local dir, URL, described
workflow, pasted notes) into `skills/<name>/SKILL.md` — prompt-only over existing tools
(WebFetch/Read/Grep/deep-research), gated by write-gate, **born untrusted (slash-only)**.

**Non-goals:** no new ingestion engine; no vector DB; no LLM-judge in the write path;
no auto-fire on day one; no auto-promotion (manual until telemetry exists); does NOT
edit canonical Brainer skills.

## Flow (5 steps — GLM cut the promote step)
1. **SOURCE** — read with existing tools. MANDATE *literal* extraction (exact commands,
   code, error strings) — guard summarization collapse.
2. **DEDUP-BEFORE-WRITE** — `learn.py dedup --desc … [--body-file …]`:
   - description token-overlap vs every existing skill desc → **LIKELY_PATCH** if ≥ thr.
   - body code/command lines vs existing skill bodies → **POSSIBLE_PATCH** on exact hit.
   - else **CREATE**. PATCH verdict ⇒ **abort with a summary**; user decides next turn
     (no auto-merge).
3. **AUTHOR** — house standards: fixed section order (`When to Use` / `Procedure` /
   `Pitfalls` / `Verification`), no invented commands, tool-framing. `description ≤60`
   is **advisory** (Brainer uses long trigger descriptions; proposed skills are
   slash-only so short is fine). `learn.py lint` hard-fails only on missing
   frontmatter keys or missing required sections.
4. **GATE** — `write_gate.py gate --kind sop` on the "why this earns a skill" block.
   Exit 1 ⇒ revise or drop. No agent-only override.
5. **WRITE** — scaffold `skills/<name>/SKILL.md`, frontmatter: `status: proposed`,
   `source:`, `learned_at:`, `disable-model-invocation: true`, `auto-install: false`.

**Trust (BUILT in turn 4):** counted promotion is telemetry-gated — `learn.py promote`
flips `proposed → trusted` only after `telemetry.py` shows N consecutive hits with no
trailing abort. Not a manual flip.

## Deliverables
- `skills/learn-skill/SKILL.md` — the 5-step protocol, slash-documented (`/learn <source>`).
- `skills/learn-skill/tools/learn.py` — `dedup` / `lint` / `scaffold` / `promote` / `demote` / `staleness`. Pure-stdlib.
- `skills/learn-skill/tools/telemetry.py` — record / scan / stats / flag (usage instrumentation).
- `skills/learn-skill/tools/test_learn.py` + `test_telemetry.py` + `test_nomination.py`.
- `skills/learn-skill/templates/learned-skill.template.md` — proposed-skill scaffold.
- `skills/learn-skill/{LOOPS.md,EVAL.md}` — loop specs (lint clean) + honest-limits posture.

## Follow-ups — ALL BUILT in turn 4 ("complete everything")
NOTE: turn-3 GLM review cut `promote` for lack of evidence; turn 4 built the evidence
(`telemetry.py`) and re-added it as a counted gate. History kept for honesty.
- **#4** canary nomination — `workflow_nomination` detector + `drift_probes.json`; nudges, never writes.
- **#5** utility telemetry — `telemetry.py`; unblocks counted promotion.
- **#6** staleness — `learn.py staleness` (git/age aware); consumes `source:`/`learned_at:`.

## done means:
1. `skills/learn-skill/SKILL.md` exists; frontmatter valid (`name`, `description`, `status`, `auto-install: false`); documents the 5-step flow + manual-trust note.
2. `learn.py {dedup,lint,scaffold}` run; `test_learn.py` passes (quote output).
3. Demo: a real source → a `proposed` SKILL.md that passes `learn.py lint` AND `write_gate.py gate` on its rationale; dedup correctly flags a near-dup.
4. New skill appears in the install catalog frontmatter scan (or note why deferred).
5. GLM-reviewed; its 5 edits folded in (promote cut, body-dedup, PATCH-abort, hole documented, 5-step). `description ≤60` kept advisory with stated reason.
