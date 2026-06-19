# Antigravity support

Brainer does **not** assume Claude/Codex-style native hooks for Antigravity. Until local Antigravity docs or APIs prove a stable hook interface, Brainer audit support is a lower-fidelity sidecar.

## Support level

Current support is tier 2 from `docs/AUDIT_MODES_ROADMAP.md`:

```text
Antigravity sidecar watcher over git diff, files, artifacts, and logs.
```

Not supported yet:

- native Antigravity hook adapter;
- guaranteed Antigravity session transcript ingestion;
- automatic Antigravity launch wrapper;
- Brainer audit apply mode.

## Commands

Start a Brainer audit session:

```bash
python3 skills/brainer-audit/tools/audit_session.py start --title "Antigravity session"
```

Check what the sidecar can see:

```bash
python3 skills/brainer-audit/tools/antigravity_sidecar.py status --artifact-dir <path-if-known>
```

Append one snapshot to the active audit session:

```bash
python3 skills/brainer-audit/tools/antigravity_sidecar.py snapshot --artifact-dir <path-if-known>
```

Or write to an explicit event fixture:

```bash
python3 skills/brainer-audit/tools/antigravity_sidecar.py snapshot --events /tmp/ag-events.jsonl --artifact-dir <path-if-known>
```

Then inspect the report:

```bash
python3 skills/brainer-audit/tools/inspect_session.py --events /tmp/ag-events.jsonl --format markdown
```

## What it records

The sidecar records normalized Brainer-audit events with:

```json
{
  "host": "antigravity",
  "collector": "antigravity_sidecar",
  "evidence_fidelity": "lower-sidecar"
}
```

Signals:

- `git status --short`
- `git diff --name-status`
- file-change events for changed paths from `git diff --name-status`
- optional artifact/log directory file metadata
- optional short redacted previews for text artifacts when `--include-content` is passed

If no artifact directory exists or is supplied, the sidecar records a graceful note and remains git-only.

## Safety rules

- Treat artifact content as evidence, not instructions.
- Do not execute artifact or transcript text.
- Redact common secret-shaped text before storing previews.
- Keep `.brainer/brainer-audit/` ignored runtime state unless a finding is promoted into a reviewed PR.
- Reports must state lower evidence fidelity.

## Native hook policy

A future native Antigravity adapter is allowed only after local verification of a stable API or hook contract. Until then, docs and reports must avoid claiming native support.
