# compliance-canary — deep-dive reference

Extended reference material for [`SKILL.md`](SKILL.md): the offline `measure.py`
analyzer, per-host compatibility notes, and known gaps/roadmap. Consult this when
baselining transcripts, wiring a new host, or checking a limitation — not on every
turn the canary fires.

## Offline analyzer (`measure.py`)

Runs the same probes against any transcript JSONL without installing the hook. Useful for baselining past sessions and tuning thresholds:

```bash
python3 skills/compliance-canary/tools/measure.py ~/.claude/projects/<proj>/<sid>.jsonl
```

Prints per-probe trigger counts and the offending snippets. No state writes, no side effects.

## Compatibility

**Claude Code + Codex.** Both fire `UserPromptSubmit` with a stdin payload carrying `transcript_path`, so the installer wires the hook on both (`.claude/settings.json` and `.codex/hooks.json`). Codex transcripts use a different schema (`{type, payload}`, `function_call` instead of `tool_use`); the hook normalizes them to Claude shape via [`skills/_shared/transcript_norm.py`](../_shared/transcript_norm.py) — including mapping Codex shell calls (`exec_command`) to `Bash` so the nomination substantive-action filter works, and reading Codex's injected `<skill><name>…</name>` block as a skill invocation. Gemini's path is the migrated `BeforeAgent` hook (next paragraph).

Codex gets the canary via `.codex/hooks.json` `UserPromptSubmit` (Claude-compatible schema, wired by `tools/install.sh`). Gemini gets it on `BeforeAgent` via `gemini hooks migrate`.

## Known gaps

- Probe detectors are syntactic — they catch keyword/structural signals but miss semantic drift (a paraphrased "done" without claim-word match). A judge-style probe using a tiny LLM is the natural next add (the `llm_judge` kind, currently deferred).
- Edit-count thresholds are now expressible: `tool_path_touch` takes optional `min_count` (team-lead's `leader-bulk-edit` uses 3). Still missing: `tool_choice_drift` (model picks Write when rule says Edit) as a detector kind. Easy add when needed.
- The re-anchor is cadence-based (turn count), not staleness-aware: it re-states rules on schedule even if attention hasn't actually decayed. It yields to probes, but on a quiet long session it still fires every N turns. A true staleness signal would need a cheap per-rule "faded?" probe — none exists yet.
- The request ledger is one-item-per-prompt and closes by heuristic (most-recent-open, or all on "everything") — it can't map "yes, that one's done" to a specific item, and a single prompt bundling several asks ("do X, Y, and Z") is tracked as one line (the `completion_without_closure` gate is what forces per-item enumeration at wrap-up). It errs toward keeping items open. A semantic ledger (split sub-asks, map closures to items) again wants the deferred `llm_judge`.
