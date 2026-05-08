# summ

Use when the user says `summ` or asks for a manual context refresh.

Goal: preserve continuity with the smallest useful fresh context. The required phases are: summarize current work, document durable memory with a cheap/lightweight wiki-documenter, write a lean handoff, then clear or bypass old context and start fresh with only `start.md` plus the handoff. `summ` is universal up to the handoff, then platform-specific for the actual context reset/successor. The model cannot assume every host clears context the same way.

For manual copy-paste operation, use `prompts/manual-summ-document-and-handoff.md` in the old session and `prompts/manual-fresh-session-from-handoff.md` in the new session.

## Protocol

1. Split session information into two buckets:
   - Fresh handoff: only goal, current state, completed work, next steps, blockers, touched paths, exact errors/commands, and links needed to continue.
   - Durable wiki memory: reusable facts, decisions, source summaries, solved workflows, and lessons that may matter later but are not needed in fresh context.
2. Spawn or route a lightweight documentation worker using `prompts/subagents/wiki-documenter.prompt.md`. Give it only verified evidence and repo-local wiki targets.
3. Create the fresh handoff with `./te context checkpoint --handoff-template` or `prompts/summarize-for-handoff.md`. If the generated checkpoint is generic, replace it with a specific handoff from current session facts. For manual copy-paste refresh, write repo-root `session_handoff.md`.
4. Keep the handoff under 2000 estimated tokens. Do not paste transcript, raw logs, broad wiki pages, or docs-only discoveries.
5. Lint it with `./te context lint-handoff <handoff-file>`.
6. Start fresh with only `start.md` plus the handoff. Use `prompts/manual-fresh-session-from-handoff.md` for manual copy-paste refresh.
7. Fresh session starts in plan mode, thinks step by step, and creates a robust plan before executing.

## Ready Prompt

```text
summ

Split this session into:
1. a lean fresh-context handoff containing only what is needed to continue, and
2. durable wiki memory that should be documented but not loaded into the fresh context unless needed later.

Spawn or route a lightweight documentation subagent for the durable wiki memory using `prompts/subagents/wiki-documenter.prompt.md`. It should update only the repo-local wiki/log after verified evidence and return a compact result packet.

Create the fresh handoff using `./te context checkpoint --handoff-template` or `prompts/summarize-for-handoff.md`. If the generated checkpoint is generic, replace it with a specific handoff from current session facts. Keep it under 2000 estimated tokens. Preserve exact paths, commands, decisions, and errors. Exclude transcript noise, raw logs, broad wiki pages, and docs-only discoveries.

For manual copy-paste refresh, write the handoff to repo-root `session_handoff.md` and lint it with:
`./te context lint-handoff session_handoff.md`

For Codex, do not claim same-thread clearing is solved. Use a fresh successor when you want the cleanest available continuation:
`./te context codex-fresh-thread --handoff <handoff-file> --execute`
Success requires `ok: true`, `thread_persistent: true`, `thread_turns_empty: true`, `assistant_responded: true`, `thread_idle: true`, and ideally `listed_after_start: true`.

In the fresh context, start in plan mode. Think step by step. Create a robust plan before executing.
```
