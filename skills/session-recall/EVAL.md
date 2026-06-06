# EVAL — `session-recall`

Status: **opt-in (`auto-install: false`)** — guardrail + smoke verified on real local sessions; A/B token-savings vs. naive grep-the-transcripts not yet run. The token-economy claim here is structural (the no-raw-into-context invariant), not yet a measured Δ.

## The invariant under test

The skill exists to answer cross-session questions **without ever loading a raw transcript into orchestrator context**. Local sessions on this machine run 1–70MB. If even one were read whole, the skill would cost more context than it saves. So the load-bearing check is: extraction is file-mediated, and the only thing the orchestrator sees per session is a constant-size `_meta` status line.

## Guardrail — no raw transcript bytes enter orchestrator context

Harness: [`tools/selftest.sh`](tools/selftest.sh). Picks the **largest** real session discovered (worst case), runs `extract-skeleton.py --output`, and asserts on the stdout the orchestrator would capture.

| Assertion | Result |
|---|---|
| stdout is exactly one line | ✅ |
| that line parses as `{_meta: true, wrote: …}` | ✅ |
| no transcript markers (`[user]`/`[assistant]`/`[tool]`/`[tools]`) in stdout | ✅ |
| stdout < 2048 B (constant, input-size-independent) | ✅ |
| bulk skeleton written to scratch (non-empty) | ✅ |

Measured run (`bash tools/selftest.sh token-economy 30`, 2026-06-06, this machine):

```
discovered 348 session file(s)
largest session: ~/.codex/sessions/2026/06/05/rollout-…019e9b7a….jsonl (69,381,407 bytes)
stdout 220B < 2048B (constant, input-size-independent)
scratch skeleton 5,689B written
ratio: input 69,381,407B / stdout 220B = 315,370x kept out of orchestrator context
RESULT: 4 pass, 0 fail
```

**A 66 MB transcript collapses to a 220-byte status line in the orchestrator's view.** The 220 B is independent of input size — it's the same `_meta` shape for a 60 KB or a 66 MB session. That is the invariant.

On a smaller, in-repo Claude Code session (2.27 MB) the same path yields 215 B stdout / 40 KB scratch — confirming the constant-stdout property across two orders of magnitude of input.

## Smoke — discover → metadata → skeleton runs end-to-end here

Same harness, earlier checks:

| Stage | Assertion | Result |
|---|---|---|
| discover | ≥1 session file for repo+window | ✅ 348 |
| metadata | `_meta` line, `files_processed > 0` | ✅ |
| skeleton | non-empty scratch file written | ✅ |

Host-path coverage verified live:
- **Claude Code** — `~/.claude/projects/-Users-za-token-economy/` and `…--claude-worktrees-*/` matched by the `*<repo>*` glob; flat `.jsonl`, `--maxdepth 1`. ✅
- **Codex** — `~/.codex/sessions/2026/MM/DD/rollout-*.jsonl` reached by recursive `find`; cross-repo sessions narrowed by `extract-metadata.py --cwd-filter`. ✅
- **Cursor** — `~/.cursor/projects` absent on this machine; `discover-sessions.sh` guards `[ -d ]` and returns nothing. Degrades silently, no error. ✅ (Cursor path untested against real data — no Cursor sessions present.)

## Not yet measured (open work)

- **A/B vs naive.** Tokens to answer "how did we investigate X" via session-recall (paths + 1–2k-token synthesis) vs. grepping/reading transcripts directly. Expected large, unquantified.
- **Synthesis fidelity.** Whether the step-6 subagent's prose actually recovers the investigation journey vs. a human-labeled ground truth across a session set. N=1 manual spot-checks only so far.
- **Cursor real-data path.** No Cursor sessions on this machine to exercise the `agent-transcripts/` branch.

Until these land, the skill stays opt-in: a bare `./install.sh` symlinks and lists it but runs nothing extra (no hook, no dep — the tools are stdlib Python + bash).

## Static cost

| field | value |
|---|---|
| description (always resident) | ~120 tokens |
| body (loaded on trigger) | ~1.3k tokens |
| tools/ payload | 4 vendored scripts + selftest, stdlib only (no deps) |
| model pin | none (orchestrator inherits; synthesis subagent → sonnet) |
