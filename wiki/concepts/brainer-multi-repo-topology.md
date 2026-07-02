---
trust: verified
schema_version: 2
title: "Brainer multi-repo topology: siblings are forked vendored copies"
type: concept
domain: "framework"
tier: semantic
confidence: 0.8
created: "2026-06-27"
updated: "2026-07-01"
verified: "2026-07-01"
sources: ["log.md", "scripts/sibling_sync_audit.py"]
resource: scripts/sibling_sync_audit.py
supersedes: []
superseded-by:
tags: [sibling-sync, propagation, multi-repo, topology, install, hard-rule]
---

# Brainer multi-repo topology: siblings are forked vendored copies

Brainer is the canonical SOURCE for its skills library. The sibling repos that
vendor Brainer's `skills/` are **forked copies, not clean mirrors** —
`scripts/sibling_sync_audit.py` revealed 9 vendored siblings, of which only
PROMPTER was kept in sync; the rest had drifted 50–69 files each, i.e. deeply
FORKED.

## HARD RULE — never blind-rsync

- **Never** blind `rsync skills/` across siblings, **because** each fork carries
  sibling-local customizations a blind copy would clobber.
- Propagate **deliberately, per-file** (git-archaeology each file as
  stale-vs-customized) **so that** sibling-local work survives. That
  archaeology is now mechanized: `sibling_sync_audit.py --classify` byte-matches
  each DIFFERS file against every historical canonical version — a match means
  STALE (safe fast-forward), no match means CUSTOMIZED (manual merge);
  `--repo <name> --apply-stale` fast-forwards only the STALE set (added
  2026-07-01).
- After any sync, **re-run the sibling's own `install.sh`** **in order to**
  rewire that host's carriers/hooks (install writes the user-GLOBAL
  `~/.claude/settings.json`, so sibling installs run sequentially, never in
  parallel).
- Verify with `python3 scripts/sibling_sync_audit.py --repo <name>` **to avoid**
  shipping a half-propagated or clobbered sibling.

## Known landmines (a blind copy hits these)

- **token-economy** — local `llm_judge` subsystem in canary `hook.py`/`measure.py`
  (must NOT be clobbered) + brand strings in `config.py`/`code_map.py`.
- **Hermes** — pre-rebrand; expects older naming.
- **alfred** — this is the PROMPTER folder.

## Related

- [[concepts/hook-path-fragility]] — a fix that must be propagated to siblings via their own install.sh, not blind-rsync
- [[projects/okf-adoption]]
- [[index]]
- [[schema]]
