# relay-session

Standalone Codex relay sessions.

Creates lean handoffs, launches a fresh Codex successor thread with a versioned
`Relay[NN]: name`, and lets the successor ask the old session narrow follow-up
questions when the handoff intentionally omits detail.

This project is independent of Token Economy. Install `relay_session/` into any
repo, and optionally install the `relay-sessions` Codex skill.

## Install From GitHub

From the target repo:

```bash
curl -fsSL https://raw.githubusercontent.com/SaarShai/token-economy/main/projects/relay-session/install.sh \
  | bash -s -- --target "$PWD" --copy --install-skill
python3 -m relay_session.cli --help
```

Checkout install:

```bash
git clone --filter=blob:none --sparse https://github.com/SaarShai/token-economy.git /tmp/token-economy-relay
cd /tmp/token-economy-relay
git sparse-checkout set projects/relay-session skills/relay-sessions
bash projects/relay-session/install.sh --target /path/to/target-repo --copy --install-skill
```

## Commands

```bash
python3 -m relay_session.cli checkpoint --repo "$PWD" --goal "continue work"
python3 -m relay_session.cli launch --repo "$PWD" --handoff .relay-session/checkpoints/<file>.md --name "Setting Up Relay" --version 01 --execute
python3 -m relay_session.cli ask-old --repo "$PWD" --handoff .relay-session/checkpoints/<file>.md --question "What exact decision was made?" --execute
```

`ask-old` is explicit-only by design. The successor should retrieve from repo
state first, then ask the old session only for a specific missing fact.
Narrow repo retrieval means targeted reads/searches of known files, status, or
symbols; it does not mean loading broad archives. Omit `--execute` to dry-run
old-session routing; add `--execute` to actually ask the old session.
If the old session identifies an even older relay handoff as the source, repeat
`ask-old` with that older handoff and the same narrow question.

## Handoff Contract

Relay handoffs include:

- `old-thread-id`
- `old-transcript`
- `old-session-query-policy: explicit-only`
- required sections 1-9
- a successor instruction to ask old only when repo retrieval is insufficient
- a recursive instruction for even older relay handoffs

## Requirements

- Python 3.9+
- Codex CLI only for `launch --execute` and `ask-old --execute`
