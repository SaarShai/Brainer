# Raw session archive — retention, redaction, deletion policy

## What's archived, and where

`context-keeper`'s `SessionEnd` hook (`tools/archive.py`, plus
`tools/codex_archive.py` for Codex) copies the just-ended session transcript
**verbatim** — lossless, byte-for-byte, no enrichment, no scrub — into:

```
<project>/.brainer/sessions/raw/<session-id>.jsonl
```

That directory carries a self-contained `.gitignore` (`*`), so archived
transcripts never enter version control in any host repo.

## Trust boundary — read this honestly

`.brainer/sessions/raw/` is **git-ignored and local-only** — it is not
committed, pushed, or synced anywhere by Brainer. But it is **not
access-controlled**: any process, script, or person with filesystem access to
the repo can read it in full, unredacted, by default. Nothing in this policy
changes that; the commands below are opt-in tools you run, not gates that
restrict who can open the files. Treat the raw archive as being as sensitive
as the most sensitive thing ever pasted into a session in this project.

## Retention window

Default: **60 days**, measured from each file's mtime. Override for the
whole project (or per-invocation, via the environment) with:

```bash
export BRAINER_RAW_RETENTION_DAYS=30
```

The window is advisory data until you act on it — see "deletion is never
automatic" below.

## The three commands

All three live in `tools/retention.py` and are explicit-invocation only —
none of them ever run from a hook.

### `status` — see what's there

```bash
python3 skills/context-keeper/tools/retention.py status
```

Prints the archive directory, the active retention window (and whether it
came from `BRAINER_RAW_RETENTION_DAYS` or the 60-day default), file count,
total bytes, oldest/newest file age, and how many files are already past the
window.

### `expire` — list or delete files past the window

```bash
# list only — deletes nothing, ever
python3 skills/context-keeper/tools/retention.py expire --dry-run

# actually remove expired files — prints exactly what was removed
python3 skills/context-keeper/tools/retention.py expire --delete
```

`--dry-run` and `--delete` are mutually exclusive and one is required —
there is no default action, so a bare `expire` with no flag does nothing but
error, by design.

### `scrub` — redact one archived transcript on demand

```bash
# writes a sibling file, leaves the original byte-for-byte untouched
python3 skills/context-keeper/tools/retention.py scrub .brainer/sessions/raw/<session-id>.jsonl
# -> .brainer/sessions/raw/<session-id>.redacted.jsonl

# also overwrite the original with the scrubbed content
python3 skills/context-keeper/tools/retention.py scrub .brainer/sessions/raw/<session-id>.jsonl --replace
```

Redaction is never applied at archive time — the archive must stay a
faithful, lossless copy. `scrub` is the only place secrets get removed, and
only when you ask. It catches, per raw line (never parse-then-reserialize
JSON, so structure/escaping can't drift): API keys, bearer/OAuth tokens,
password-like assignments (delegated to the already-hardened
`skills/_shared/audit_redact.py`), high-entropy hex/base64 runs sitting next
to a key, and email addresses other than the repo owner's (`git config
user.email`, or `BRAINER_OWNER_EMAIL` to override).

## Deletion is never automatic — the guarantee

No hook, no background process, and no other Brainer skill ever deletes a
file under `.brainer/sessions/raw/`. The only way a raw transcript is removed
is a human typing `retention.py expire --delete`, after having seen (via
`--dry-run` or `status`) exactly what's about to go. This is the no-drop
doctrine applied to disk: nothing valuable disappears silently.
