---
name: output-filter
description: Use when terminal output is noisy with ANSI / progress bars / duplicate lines and you want to keep the agent's eyes on signal. Strips ANSI, collapses adjacent duplicates, archives raw output locally for recovery, exposes stats and rewind. Wire as a shell pipe or PostToolUse hook on Bash. Preserves error lines and exact failure evidence verbatim.
effort: low
tools: [Bash]
---

# output-filter

## What it does

Strips ANSI escape codes and progress-bar redraws, collapses adjacent duplicate lines, and preserves error lines / exit-status markers verbatim. For large search results, logs, and diffs it can apply conservative content-aware summaries while archiving the raw output under `.brainer/output-filter/<session>/` so you can always recover the original. CLI exposes `stats` (token savings per session) and `rewind` (restore raw output for the last N runs, optionally grep-filtered).

## Usage

Direct pipe:

```bash
some-noisy-command | TOKEN_ECONOMY_ROOT="$PWD" bash skills/output-filter/tools/filter.sh
rg "needle" | TOKEN_ECONOMY_ROOT="$PWD" bash skills/output-filter/tools/filter.sh filter --content-type search --show-marker
```

CLI:

```bash
python skills/output-filter/tools/cli.py stats
python skills/output-filter/tools/cli.py rewind
python skills/output-filter/tools/cli.py rewind <archive-id> --grep "ERROR|FAILED"
python skills/output-filter/tools/cli.py rules --init
```

Custom rules live at `.brainer/output-filter-rules.txt`. Syntax: `keep:<regex>`, `drop:<regex>`, `collapse:<regex>`.

Optional session-aware suppression (suppresses lines already seen in the current `TOKEN_ECONOMY_SESSION_ID`) is OFF by default — repeated lines often matter during debugging. Enable with `--session-aware`.

Content-aware mode is deterministic and fail-safe:

- `--content-type auto` (default) detects large search/log/diff output and summarizes only above conservative size thresholds.
- `search` keeps first/last hits, one hit per file, and all failure lines.
- `log` keeps test/build summaries, warnings, errors, tracebacks, and the head+tail; also detects `git log` (runs of `commit <hash>` lines) so long histories compress instead of passing through as plain text.
- `diff` keeps diff headers, hunk headers, and changed lines.

Use `--show-marker` when you want the filtered output itself to include the archive id and recovery command. The recovery command advertises `--grep '<regex>'` so a consumer pulls only the matching raw lines instead of over-pulling the whole archived output. The marker is opt-in so normal command output stays quiet.

## Hook wiring (Claude Code)

No installer ships yet — wire by hand. Add to `.claude/settings.json`:

```json
{
  "hooks": {
    "PostToolUse": [
      {
        "matcher": "Bash",
        "hooks": [
          {
            "type": "command",
            "command": "bash \"${CLAUDE_PROJECT_DIR:-$PWD}/.claude/skills/output-filter/tools/filter.sh\""
          }
        ]
      }
    ]
  }
}
```

Or apply the pipe form per-invocation by appending `| bash skills/output-filter/tools/filter.sh` to noisy commands.

## Files

```
tools/
├── filter.sh         # pipe entrypoint
├── cli.py            # stats/rewind/rules
└── output_filter.py  # python impl
```
