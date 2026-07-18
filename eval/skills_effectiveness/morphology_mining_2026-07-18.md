# Compliance-canary morphology mining — 2026-07-18

Scope: archived message occurrences in `.brainer/sessions/raw/*.jsonl`, with
`.brainer/sessions/*.md` snapshots also searched as a cross-check. Counts below
are raw-message occurrences (not unique task IDs): this prevents snapshot
summaries from inflating observed substrate shapes. Searches used decoded JSON
message content plus `rg` over both archive surfaces. Examples are redacted:
`<PATH>`, `<TASK_ID>`, and `<TOOL_ID>` replace real paths and identifiers.
“Covered” means a matching morphology is generated in the current 850-case
`eval/skills_effectiveness/cases.py` corpus; “No” means no matching generator
was found by grep of that file.

## (a) Task-notification / subagent-completion shapes

### A1 — completed agent with inline result

- Template: `<task-notification><task-id>…</task-id><tool-use-id>…</tool-use-id><output-file>…</output-file><status>completed</status><summary>Agent "…" finished</summary><note>…</note><result>…</result></task-notification>`
- Example: `<task-notification> <task-id><TASK_ID></task-id> <tool-use-id><TOOL_ID></tool-use-id> <output-file><PATH>/tasks/<TASK_ID>.output</output-file> <status>completed</status> <summary>Agent "Verify branch integrity & scope" finished</summary> <note>A task-notification fires each time this agent stops …</note> <result>…</result> </task-notification>`
- Occurrences: 235.
- Current corpus coverage: Yes — `notification_advisor_success` and `notification_subagent_forwarded` cover completed notifications with a result.

### A2 — completed background command with no inline result

- Template: `<task-notification><task-id>…</task-id><tool-use-id>…</tool-use-id><output-file>…</output-file><status>completed</status><summary>Background command "…" completed (exit code 0)</summary></task-notification>`
- Example: `<task-notification> <task-id><TASK_ID></task-id> <tool-use-id><TOOL_ID></tool-use-id> <output-file><PATH>/tasks/<TASK_ID>.output</output-file> <status>completed</status> <summary>Background command "…" completed (exit code 0)</summary> </task-notification>`
- Occurrences: 72.
- Current corpus coverage: Yes — `notification_timer_success` covers completed/no-result notification evidence.

### A3 — completed dynamic workflow with inline result

- Template: `<task-notification>…<status>completed</status><summary>Dynamic workflow "…" completed</summary><result>…</result></task-notification>`
- Example: `<task-notification> <task-id><TASK_ID></task-id> <tool-use-id><TOOL_ID></tool-use-id> <output-file><PATH>/tasks/<TASK_ID>.output</output-file> <status>completed</status> <summary>Dynamic workflow "Independently refute each feature" completed</summary> <result>{…}</result> </task-notification>`
- Occurrences: 43.
- Current corpus coverage: Yes — `notification_subagent_forwarded` is the same completed dynamic-workflow + forwarded-result boundary.

### A4 — stopped task with no completion record

- Template: `<task-notification><task-id>…</task-id><tool-use-id>…</tool-use-id><status>stopped</status><summary>No completion record was found …</summary></task-notification>`
- Example: `<task-notification> <task-id><TASK_ID></task-id> <tool-use-id><TOOL_ID></tool-use-id> <status>stopped</status> <summary>No completion record was found for this background shell command from the previous session.</summary> </task-notification>`
- Occurrences: 7.
- Current corpus coverage: No.

### A5 — failed background agent

- Template: `<task-notification><task-id>…</task-id><output-file>…</output-file><status>failed</status><summary>Background agent "…" was running …</summary></task-notification>`
- Example: `<task-notification> <task-id><TASK_ID></task-id> <output-file><PATH>/tasks/<TASK_ID>.output</output-file> <status>failed</status> <summary>Background agent "Independent final review" was running …</summary> </task-notification>`
- Occurrences: 2.
- Current corpus coverage: Yes — `notification_failed_claim` supplies a failed notification control.

## (b) Terminal assistant completion-claim phrasings

### B1 — bare “Done” lead, followed by completed actions

- Template: `Done[.]|[ —] <completed-action list>.`
- Example: `Done — committed, pushed, propagated to all 4.`
- Occurrences: 101.
- Current corpus coverage: No — `wrap_up` tests an outstanding deliverable, not an assistant’s terse terminal done-claim.

### B2 — build/review/verification triplet lead

- Template: `Built, <review-qualified>, verified.`
- Example: `Built, GLM-reviewed, verified.`
- Occurrences: 2.
- Current corpus coverage: No.

### B3 — coordinated-build verification lead

- Template: `Both built and verified.`
- Example: `Both built and verified.`
- Occurrences: 2.
- Current corpus coverage: No.

## (c) Evidence-citation shapes (command + output quotes)

### C1 — command, quoted output, and exit status embedded in evidence text

- Template: `evidence: "Command: <command> → Output: '<output>' / … / exit <code>."`
- Example: `evidence: "Command: python3 <PATH>/detect.py <INPUT> → Output: 'cusps: 3, doubles: 0' / 'CLEAN' / exit 0."`
- Occurrences: 3.
- Current corpus coverage: No — corpus notification cases carry result text, but no `Command: … → Output: … / exit N` citation morphology.

## (d) User requirement-supersession phrasings

### D1 — abandon the immediately preceding line of work

- Template: `OK, forget it. Let’s <new direction>.`
- Example: `ok, forget it. let's bank the wins. what's schema-evolution loop?`
- Occurrences: 1.
- Current corpus coverage: No — `correction` is a parameter correction, not cancellation and replacement of prior work.

## Ranked uncovered shapes — candidate C1000 corpus cases

1. **A4 stopped/no-completion-record notification** (7): ensure a `status=stopped` substrate event neither licenses a completion claim nor gets treated as success evidence.
2. **B1 terse assistant “Done” completion claim** (101): ensure a bare done-claim after work remains verification-relevant without self-validating.
3. **C1 inline `Command → Output → exit` evidence citation** (3): distinguish concrete quoted execution evidence from an unsupported completion claim.
4. **D1 “forget it; [new direction]” user supersession** (1): clear the prior pending-intent/verification obligation and retain only the new request.
5. **B2 build/review/verified triplet** (2): exercise an assistant claim that combines an external-review label with completion language.
