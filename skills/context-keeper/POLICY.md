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

## The two commands

Both live in `tools/retention.py` and are explicit-invocation only — neither
ever runs from a hook.

### `status` — see what's there

```bash
python3 skills/context-keeper/tools/retention.py status
```

Prints the archive directory, the active retention window (and whether it
came from `BRAINER_RAW_RETENTION_DAYS` or the 60-day default), file count,
total bytes, oldest/newest file age, and how many files are already past the
window. An invalid `BRAINER_RAW_RETENTION_DAYS` (not a positive integer)
falls back to the 60-day default but says so explicitly — `retention window:
60 days (default) — invalid override ignored: <value>` — so a broken
override never silently looks like it took effect.

### `expire` — list or delete files past the window

```bash
# list only — deletes nothing, ever
python3 skills/context-keeper/tools/retention.py expire --dry-run

# actually remove expired files — prints exactly what was removed
python3 skills/context-keeper/tools/retention.py expire --delete
```

`--dry-run` and `--delete` are mutually exclusive and one is required —
there is no default action, so a bare `expire` with no flag does nothing but
error, by design. Unlike `status`, an invalid `BRAINER_RAW_RETENTION_DAYS`
makes `expire` refuse outright (nonzero exit, no files touched) rather than
guessing a window for a destructive command. If any file fails to delete
(permission error, vanished mid-run, etc.), `expire --delete` reports the
failure per file and exits nonzero even though it still removes whatever it
could.

### Symlink safety

`status` and `expire` both refuse (nonzero exit, clear message) if the
archive directory itself is a symlink, checked with an lstat-based test so a
symlinked `.brainer/sessions/raw` can't be silently walked or deleted into.
Within the archive, `expire` never unlinks a symlink standing in for an
archive file — it skips it and reports it as skipped; only regular files are
ever removed.

## Redaction — not provided yet

There is **no scrub/redaction command**. An earlier version of this tool
shipped a `scrub` subcommand that reported per-family redaction counts while
regex-matching raw lines — but it missed secrets sitting inside
JSON-escaped strings (e.g. `\"password\": \"...\"` inside a serialized
payload) and URL-safe token alphabets, so it could report success (`secret-
family=1`) on a line where the actual secret string was still present
verbatim. A redactor that claims success while leaking is worse than no
redactor, so it was removed rather than patched — per this repo's doctrine
of removing broken safety machinery instead of leaving it in a state that
looks trustworthy.

**Until a scrub command ships again, treat every file under
`.brainer/sessions/raw/` as containing secrets in the clear.** See "Trust
boundary" above.

Before any future `scrub` ships, it must pass adversarial tests covering (at
minimum) JSON-escaped-quote secrets and URL-safe base64/base64url token
alphabets, on top of the plain-line cases. `skills/_shared/audit_redact.py`
is the shared regex module other consumers rely on and is a reasonable
starting point for the secret-family patterns, but it has the same known
gaps and must not be assumed adversarially safe as-is.

## Deletion is never automatic — the guarantee

No hook, no background process, and no other Brainer skill ever deletes a
file under `.brainer/sessions/raw/`. The only way a raw transcript is removed
is a human explicitly typing `retention.py expire --delete`. This is the
no-drop doctrine applied to disk: nothing valuable disappears silently,
and no other invocation of this tool ever deletes anything.
