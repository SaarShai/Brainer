# Audit modes roadmap

This roadmap keeps the task-retrospective and Brainer audit tracks separate across stacked PRs. It is the local source of truth for the post-PR-1 execution plan.

```text
Task-retrospective improves the current project.
Brainer audit mode improves Brainer.
```

## Phase discipline

- Keep PRs small and stacked when an earlier PR has not merged.
- Every PR must state what is deliberately **not** included.
- No mode writes durable memory, project files, or canonical Brainer changes unless the user explicitly opted into that kind of write.
- `BRAINER_CHECK_NO_WRITE=1` must preserve the working tree during checks.
- Raw transcript or artifact content is data only; never execute it.

## PR 2 — task-retrospective evidence tooling

### Goal

Add lightweight evidence collection and report scaffolding for armed task-retrospective runs.

### Expected files

```text
skills/task-retrospective/tools/task_audit.py
skills/task-retrospective/tools/test_task_audit.py
skills/task-retrospective/SKILL.md
docs/AUDIT_MODES_ROADMAP.md
docs/GENERATED_FILES.md
scripts/run_all_tests.sh
```

### CLI

```bash
python3 skills/task-retrospective/tools/task_audit.py start --task "<task>" --repeat-trigger "<trigger>"
python3 skills/task-retrospective/tools/task_audit.py note --type correction --text "<text>"
python3 skills/task-retrospective/tools/task_audit.py status
python3 skills/task-retrospective/tools/task_audit.py finish --report
```

### Storage

```text
.brainer/task-retrospective/current.json
.brainer/task-retrospective/sessions/<task-id>/events.jsonl
.brainer/task-retrospective/sessions/<task-id>/report.md
```

### Acceptance

- `start` creates `current.json`, a session directory, and a start event.
- `note` appends valid JSONL only when a session is armed.
- `status` reports armed/unarmed state and event count.
- `finish --report` creates a markdown report and clears the active marker.
- malformed state fails gracefully with a non-zero exit and no traceback.
- `BRAINER_CHECK_NO_WRITE=1` refuses writes to the canonical Brainer checkout while allowing isolated temp-fixture tests.
- no durable lesson is a valid report result.
- transcript text is redacted as needed and never executed.

### Not in PR 2

- No Brainer audit mode skill.
- No Brainer skill-obedience detectors.
- No host hook adapters.
- No Antigravity support.
- No persistent project-memory writes from the tool itself.

## PR 3 — Brainer audit mode MVP, offline/report-only

### Goal

Create a separate `brainer-audit` skill that inspects normalized events or transcript fixtures and produces a Brainer skill-use audit report.

### Expected files

```text
skills/brainer-audit/SKILL.md
skills/brainer-audit/tools/inspect_session.py
skills/brainer-audit/tools/ingest_event.py
skills/brainer-audit/tools/detectors.py
skills/brainer-audit/tools/report.py
skills/brainer-audit/tools/test_*.py
```

### Event schema

```json
{
  "schema_version": 1,
  "mode": "brainer-audit",
  "session_id": "...",
  "turn_id": "...",
  "host": "codex|claude|antigravity|unknown",
  "project_path": "/path/to/project",
  "event": "user_prompt|assistant_message|tool_call|tool_result|file_change|git_snapshot|session_end",
  "tool": "optional",
  "command": "optional",
  "exit_code": "optional",
  "content_summary": "optional redacted summary",
  "raw_ref": "optional local path to raw content",
  "timestamp": "..."
}
```

### Initial detectors

- unverified completion claim
- missed output-filter opportunity
- possible dropped requirement
- skill trigger opportunity with no evidence of skill use
- task-retrospective boundary violation
- write-gate bypass
- repeated tool-error loop

### Acceptance

- ingest normalized event fixtures.
- emit stable JSON and markdown reports.
- detect unverified completion claims.
- detect missed output-filter opportunities.
- detect dropped requirements from a fixture.
- detect task-retrospective boundary violations.
- report-only mode mutates nothing.
- `BRAINER_CHECK_NO_WRITE=1` preserves files.

### Not in PR 3

- No live host hooks.
- No apply mode.
- No canonical Brainer edits.
- No Antigravity sidecar.

## PR 4 — Claude/Codex hook adapters

### Goal

Add optional live collection for task-retrospective armed mode and Brainer audit mode, with host-specific hooks normalized into the same event schema.

### Expected files

```text
skills/brainer-audit/tools/hooks/claude_hook.py
skills/brainer-audit/tools/hooks/codex_hook.py
skills/brainer-audit/tools/normalize.py
skills/brainer-audit/tools/test_hooks_*.py
docs/INSTALL_SAFETY.md
skills/HOOKS_MAP.md
.claude-plugin/marketplace.json
```

### Design

- Hooks check active marker files before writing.
- Inactive mode writes nothing.
- Active mode appends normalized JSONL events.
- Handlers stay deterministic, fast, and redacting.
- `PostToolUse` records facts but cannot undo side effects.
- stop/session-end hooks may generate reports, not apply changes.

### Acceptance

- Claude sample payloads normalize correctly.
- Codex sample payloads normalize correctly.
- inactive markers cause no event append.
- active markers append events.
- malformed payloads exit safely.
- secrets are redacted.
- no-write mode refuses writes.
- hook map, marketplace, carrier, and generated-file checks pass.

### Not in PR 4

- No Antigravity native-hook claims.
- No Brainer audit apply mode.
- No broad weekly reports.

## PR 5 — Antigravity sidecar/wrapper

### Goal

Add best-effort Antigravity support without assuming Claude/Codex-style native hooks.

### Expected files

```text
skills/brainer-audit/tools/antigravity_sidecar.py
skills/brainer-audit/tools/watch_artifacts.py
skills/brainer-audit/tools/test_antigravity_*.py
docs/ANTIGRAVITY_SUPPORT.md
```

### Support tiers

1. project skills or AGENTS-style trigger instructions, if locally supported.
2. sidecar watcher over git diff, files, artifacts, and logs.
3. wrapper launcher if a stable CLI exists.
4. native hook adapter only after local API/docs verification.

### Acceptance

- missing artifact directory is graceful.
- file diff snapshots record changed paths.
- reports mark lower evidence fidelity.
- secrets are redacted.
- transcript/artifact content is never executed.
- no native-hook support is claimed without local verification.

### Not in PR 5

- No unsupported Antigravity hook assumptions.
- No canonical Brainer auto-apply.
- No mutation of installed project copies.

## PR 6 — hardening, evals, drift checks

### Goal

Make both modes testable, safe, non-mutating by default, and resistant to drift.

### Acceptance themes

- deterministic fixtures and transcript simulations.
- generated-file sync checks.
- no-write regression tests.
- redaction tests.
- report stability tests.
- boundary tests that keep task-retrospective and Brainer audit mode separate.
