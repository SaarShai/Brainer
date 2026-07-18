---
schema_version: 2
title: "secrets.env shell command substitution pitfall — flat KEY=VALUE parsers fail on $(…) syntax"
type: lesson
domain: "framework"
tier: semantic
confidence: 0.95
created: "2026-07-18"
updated: "2026-07-18"
verified: "2026-07-18"
sources:
  - "2026-07-18 long-horizon rehearsal session observation: ~secrets.env pitfall"
  - "longhorizon_gate.py load_api_key() implementation"
  - "commit 448f2cc: rehearsal gate-report.json"
tags: [secrets, api-key, auth, pitfall, configuration, environment-variables, parser-mismatch]
supersedes: []
superseded-by:
---

# secrets.env shell command substitution pitfall — flat KEY=VALUE parsers fail on $(…) syntax

## The failure

In the 2026-07-18 long-horizon rehearsal session, API authentication was failing with 401 errors during grading runs. The configuration file `~/.config/brainer/secrets.env` contains:

```bash
export ZAI_API_KEY="$(cat ~/.config/zai/key)"
```

When the grading harness (`longhorizon_gate.py`) loaded the API key using a flat KEY=VALUE parser (not a bash interpreter), it read the literal string `$(cat ~/.config/zai/key)` instead of executing the shell command to retrieve the actual key. Auth then failed immediately with 401.

## Root cause

The secrets file uses **bash command substitution** syntax (`$(…)`) to dynamically load the key at runtime. Any script or tool that:

1. Reads the file as a flat text configuration (line-by-line KEY=VALUE parsing)
2. Does not shell-source the file through bash

...will receive the literal string `$(cat` as the key value, not the expanded key. This mismatch between the file's intended syntax and the loader's parsing mode causes hard failures.

## The fix

The fix in `longhorizon_gate.py load_api_key()` shells out to bash to properly source the file:

```python
# Instead of: parsing ~/.config/brainer/secrets.env as flat KEY=VALUE
# Correct: source through bash to expand $(…) syntax
result = subprocess.run(
    ["bash", "-c", "source ~/.config/brainer/secrets.env && echo $ZAI_API_KEY"],
    capture_output=True,
    text=True
)
api_key = result.stdout.strip()
```

Only bash (or sh) interpreters handle the `$(…)` syntax; flat parsers see literal text.

## Lesson

- **Secrets files with dynamic syntax require dynamic loading.** If your `secrets.env` uses shell expansion (`$(…)`, `${…}`, `$VAR` references), you must source it through a shell interpreter, not parse it flat.
- **Loaders must match the file's intended syntax.** Document whether a secrets file is flat KEY=VALUE (parseable by any language) or bash-sourced (requires `bash -c "source …"`).
- **Test the actual loading path.** A 401 from an empty/malformed key is a category-specific failure; test loaders against the real config format before shipping.
- **Provide both forms if possible.** Codebases using multiple languages often need both a flat-parseable version and a bash-sourced version for different contexts.

## Related

- [[concepts/codex-sandbox-dns-api-access-pitfall]] — API access issues in sandbox environments
- `~/.config/brainer/secrets.env` — canonical location (bash-sourced format)
- `longhorizon_gate.py` — grading harness with correct bash-sourced loader

## Open questions

- Should the canonical `secrets.env` template offer both a bash-sourced version and a flat-parseable fallback?
- Are there other loaders in the codebase still using flat parsers that might fail on this file?
