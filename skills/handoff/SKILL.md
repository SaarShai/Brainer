---
name: handoff
description: Fires on the literal token "/handoff" in the user's message (with or without a focus argument after it; e.g. "/handoff" or "/handoff fixing the auth race"). Do NOT fire on any other input. Writes a handoff document summarising the current conversation so a fresh agent can continue the work. Saves to the OS temp dir, not the workspace. Suggests 1–3 skills the successor should invoke first. References existing artifacts; doesn't duplicate them. Redacts secrets. Pure write-doc — no successor launch.
model: any
effort: low
tools: [Bash, Read, Write]
argument-hint: What will the next session be used for?
disable-model-invocation: true
---

# handoff

## Strict trigger gate

This skill fires **only** when the user's most recent message starts with the literal token `/handoff` (case-insensitive), with or without text after it. Examples that DO fire:

- `/handoff`
- `/handoff fixing the auth race condition`
- `/HANDOFF — continue the eval`

If the message does not start with `/handoff`, **exit silently** — do not write any file, do not propose a handoff, do not mention this skill. Hand control back to whatever skill or default behaviour the host was going to run.

This gate is necessary because hosts vary in how they route slash commands: Claude Code maps `/handoff` natively via the `name:` frontmatter, but Codex / Cursor / Gemini fall back to description-keyword matching, where a loose trigger would fire on arbitrary prose containing the word "handoff".

## Body

When the trigger matches, write a handoff document summarising the current conversation so a fresh agent can continue the work. **Save it to the temporary directory of the user's OS — not the current workspace.**

Include a **suggested skills** section listing 1–3 skills the next session should invoke first (drawn from this catalog: caveman-ultra, plan-first-execute, lean-execution, verify-before-completion, wiki-memory, context-refresh, prompt-triage, delegate, context-keeper, compress-context, semantic-diff, output-filter).

**Do not duplicate** content already captured in other artifacts (PRDs, plans, ADRs, issues, commits, diffs). Reference them by path or URL instead.

**Redact** API keys, passwords, tokens, and any PII before writing the file.

If the user passed an argument to the slash command, treat it as a description of what the next session will focus on and tailor the doc accordingly.

## Output format (markdown)

```markdown
# Handoff — <date> — <one-sentence focus>

## Summary
<one paragraph: where we are, what was just done, what's next.>

## Done
- ...

## In progress
- ...

## Next
- ...

## Files touched
- path:line  why

## Exact commands / errors to recall
```bash
<verbatim>
```

## Open questions / blockers

## Suggested skills (invoke first)
- skill-name — why

## References (do not paste — link to them)
- <path or URL> — what's there
```

Default path: `${TMPDIR:-/tmp}/handoff-$(date +%Y%m%d-%H%M%S).md`. Print the absolute path on the last line so the user can copy it.

## Implementation

```bash
python3 skills/context-refresh/tools/context.py checkpoint \
  --goal "<focus argument or one-line goal>" \
  --print-packet > "${TMPDIR:-/tmp}/handoff-$(date +%Y%m%d-%H%M%S).md"
```

The `context-refresh` skill's `checkpoint` subcommand emits a structured packet that this skill's body refines into the doc above. No launch, no successor — that's `context-refresh`'s job, opt-in.

## Lineage

mattpocock/skills/productivity/handoff (MIT). Phrasing on summary, suggested-skills, reference-don't-duplicate, redaction, OS-temp-dir, and argument-hint borrowed verbatim. The `disable-model-invocation: true` discipline is his — keep the trigger explicit so the model never auto-fires a handoff mid-task.
