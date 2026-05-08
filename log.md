# Log

## [2026-05-08] fix | unblock te CLI and lean baseline

Removed orphan `cleanup` import, handler, and argparse subparser in `token_economy/cli.py` (introduced by `397b00e` without the `cleanup.py` module ever being committed; broke `./te doctor` for fresh clones). Trimmed `start.md` to 1479 tokens (was 1540) so `tests/test_universal_framework.py::test_start_and_adapters_stay_lean` passes again, while preserving the `no softening` and `Default target project comes from the user prompt` substring guards. Made `scripts/run_all_tests.sh` skip semdiff tests when `tree_sitter_languages` is absent and pull deps from `.token-economy/deps` when present, so the canonical baseline runs cleanly with or without the stable bundle installed. Verified: `./INSTALL.sh --dry-run`, `./te doctor`, `./te hooks doctor`, `./te wiki lint --strict --fail-on-error`, `./te bench run --suite framework-smoke`, `bash scripts/run_all_tests.sh` (29 framework tests + 6 semdiff tests, all passing).

## [2026-04-26] policy | reasoning high, reply ultra

Made the model policy explicit in `token-economy.yaml`, `token_economy/config.py`, and `token_economy/profile.py`: reasoning effort is `high`, surfaced reply style is `ultra`. Also narrowed wiki stale-index lint to the tool-owned catalog and suppressed legacy migration warnings in strict lint so the current corpus validates cleanly while preserving the underlying evidence arrays.

## [2026-04-26] clarify | caveman output vs reasoning

Clarified that Caveman Ultra is surfaced-output compression only, not hidden reasoning control. Updated `start.md`, `L0_rules.md`, `skills/caveman-ultra/SKILL.md`, `skills/personal-assistant/SKILL.md`, `token_economy/context.py`, and `concepts/caveman-output-compression.md` so future agents do not conflate terse prose with the model's thinking budget.

## [2026-04-26] harden | lean execution and plan pruning

Added `skills/lean-execution/SKILL.md`, wired it into `start.md`, added an L0 plan-pruning rule, tightened `plan-first-execute` with a simplification pass and low-risk planning bypass, and added a subagent overhead gate plus compact result budget. Added [[concepts/lean-execution]] to capture the source synthesis. Normalized complete-migrate prompt `.md` paths and added the new skill to import bootstrap. Verified with `./te doctor`, `./te wiki lint --strict --fail-on-error`, `bash scripts/run_all_tests.sh`, and `git diff --check`.

## [2026-04-26] research | top repo lean execution deep pass

Ranked the earlier repo candidates by live GitHub signals, then shallow-cloned and inspected the top three: `addyosmani/agent-skills`, `openai/skills`, and `memodb-io/Acontext`. Adopted small follow-ups only: tighter understand-before-delete and scope discipline in `lean-execution`, richer-page-over-thin-page wiki-writing rules, and a stricter subagent fan-out merge-size condition. Updated [[concepts/lean-execution]] with the repo evidence and kept external frameworks as source material, not dependencies.

## [2026-04-25] compile | framework hardening and adoption learnings

Added a compact synthesis page and raw research note for the latest hardening/adoption pass, including Gemini ecosystem research, local M1 Gemma/Ollama research, Gemini cache guidance, local M1/M1B Ollama results, a ranked adoption matrix, implemented retrieval and lifecycle routing, the current skill-crystallizer and code-map layers, and deferred graph-memory/alias/SessionEnd ideas.

## [2026-04-25] update | local model setup matrix

Added a task-capable local-model setup matrix and updated the device inventory so M1B is no longer documented as worker-only. The matrix covers shared Token Economy tools, skills, workflows, and harnesses for M1/M1B/M2.

## [2026-04-24] ship | universal agent framework v1

Added `start.md`, `token-economy.yaml`, the `te` CLI, lean agent adapters, L0/L1 memory files, wiki-search v1, context-refresh, delegate-router, and context-keeper v2 retrieval tools. Verified with `bash scripts/run_all_tests.sh`.

## [2026-04-24] ship | agent-ignition supplement

Added wiki schema v2 templates, model-agnostic skills/prompts, context meter + handoff lint, stricter delegation contracts, hooks/configs/extensions, install dry-run, profile support, framework smoke bench, and CI gate. Verified with `bash scripts/run_all_tests.sh`, `te wiki lint --strict --fail-on-error`, `te bench run --suite framework-smoke`, JSON config validation, and Python compile.

## [2026-04-24] ship | personal-assistant routing

Added `/pa` and `/btw` prompt bypass via `te pa`, hook routing, a personal-assistant skill, and router prompt. Purpose: route context-light prompts through a lightweight classifier/dispatcher with minimal context, escalating only when risk or complexity requires the main model.

## [2026-04-24] harden | repo-local startup review

Reviewed the framework, repo docs, and setup prompt for duplicated startup glue, stale global setup language, noisy hooks, and routing/context-meter gaps. Updated `HANDOFF.md`, startup docs, `L0_rules.md`, wiki schema defaults, docs audit scope, context meter model sizing, adapter overwrite detection, and prompt hook behavior. Verified with `bash scripts/run_all_tests.sh`, `./INSTALL.sh --dry-run`, `./te wiki lint --strict --fail-on-error`, `./te doctor`, `./te hooks doctor`, `./te bench run --suite framework-smoke`, Python compile, `git diff --check`, active-doc global-term scan, and token-budget checks.

## [2026-04-24] harden | fresh folder setup

Updated the setup prompt and onboarding docs to keep first-run setup simple: if the target folder lacks `token-economy.yaml`, the prompt explicitly permits clearing that current folder only, including hidden files and `.git`, then cloning the canonical repo fresh. Purpose: avoid false stops in non-empty setup folders while still forbidding deletion outside the target folder.

## [2026-04-24] feature | repo-maintainer worker

Added a lightweight repo-maintainer subagent prompt and routing policy for task workspaces with GitHub remotes. It runs only at verified save-points, before context refresh/handoff, or on explicit save/commit/push requests; it stages only intended task changes and skips entirely when no GitHub remote exists.

## [2026-04-24] feature | summ context refresh

Added the `summ` manual refresh prompt, a lightweight wiki-documenter subagent prompt, and stricter context-refresh rules. Fresh sessions now load only the lean handoff plus `start.md`; durable but non-immediate memory is routed to repo-local wiki documentation instead of being carried into fresh context.

## [2026-04-24] harden | terminal summ behavior

Updated `summ` so appended instructions become next-session requirements, generic checkpoints must be replaced with session-specific handoffs, missing documenter prompts use an inline fallback instead of broad searching, and old-context work stops after emitting the packet.

## [2026-04-24] feature | host context controls

Added host-native context control guidance for `summ`: Claude Code `/clear` and `/compact`, Codex `/new`, `/clear`, and `/compact`, Gemini `/compress`, and generic fallback to a fresh session. Added `./te context host-controls` so agents can retrieve the right command without loading broad docs.

## [2026-04-24] feature | subagent lifecycle cleanup

Added a lifecycle prompt for closing completed or idle subagents only after their result packet has been read, useful output has been merged or documented, and follow-up risks have been captured. This prevents thread-limit stalls without losing worker results.

## [2026-04-24] harden | summ host-boundary tests

Clarified that `summ` cannot assume the model can execute host slash commands from its own response. Added `prompts/summ-experiments.md` for measuring whether a host actually dropped context, and updated host-control guidance to require user/host execution unless a real tool exists.

## [2026-04-24] feature | fresh successor workaround

Added `./te context fresh-command` and documented the best non-slash workaround: start a fresh successor host process/session with only `start.md` and the handoff file. This bypasses a full old transcript even when the current host cannot be cleared programmatically.

## [2026-04-24] feature | Codex App Server fresh thread

Added `./te context codex-fresh-thread` as the verified Codex successor path. It uses Codex App Server `thread/start` + `turn/start` with an explicit accessible model, creates an ephemeral thread with `turns: []`, and loads only `start.md` plus the handoff. Live smoke passed with `gpt-5.3-codex-spark`; this bypasses rather than erases the old host transcript.

## [2026-04-24] verify | controlled summ fresh-thread result

Verified controlled `summ` successor run: `./te context codex-fresh-thread --handoff .token-economy/checkpoints/20260424-135455-fresh-session.md --model gpt-5.3-codex-spark --execute` returned `ok=true`, `thread_id=019dbfc5-edbe-7632-9a51-0dda81340fb0`, `assistant_responded=true`, and `thread_idle=true`. Events showed `thread/started` with `ephemeral=true` and `turns=[]`; successor read `start.md` plus the handoff only, while the old visible host transcript was not erased. Token usage still showed large Codex host/system overhead, about 53k input tokens, despite no old transcript in the successor-visible prompt. See [[prompts/summ-experiments]].

## [2026-04-24] upgrade | persistent Codex fresh successor

Changed `./te context codex-fresh-thread` to create a persistent same-project successor by default, with `--ephemeral` reserved for throwaway smoke tests. Verified live: `thread_id=019dbfd4-4efb-7453-84d1-b6010cc6d35a`, `ok=true`, `thread_persistent=true`, `thread_turns_empty=true`, `thread_idle=true`, and `listed_after_start=true`. This gives `summ` a durable project-thread continuation without claiming to erase the old active transcript.

## [2026-04-24] clarify | platform-specific summ strategies

Kept `summ` universal through summarize/document/handoff, then made execution platform-specific. `./te context host-controls --agent auto` now returns a `strategy`: Codex uses persistent same-project successor threads, Claude uses native `/clear` or `/compact`, Gemini uses `/compress` or a new session, and generic hosts use a manual fresh session with only `start.md` plus the handoff.

## [2026-04-24] harden | legacy summ fallback

Clarified that `./te context fresh-start` is not a successor launcher; it only writes or prints a packet. If an older project-local `te` lacks `host-controls`, `fresh-command`, or `codex-fresh-thread`, Codex `summ` should fall back to a real successor command such as `codex fork --last -C "$PWD" "<handoff instruction>"` or `codex -C "$PWD" "<handoff instruction>"`.

## [2026-04-24] harden | legacy Codex launch attempt

Updated `summ` so older Codex installs first attempt a direct `codex app-server` persistent successor thread when the project-local Token Economy wrapper is missing. Printing `codex fork --last` is now a last resort after App Server is unavailable or fails, not the default stopping point.

## [2026-04-24] fix | Codex fresh-thread wait

Changed `./te context codex-fresh-thread --execute` to stop waiting as soon as the successor thread responds and returns to idle, instead of waiting through fixed read windows. Live retest passed with `thread_id=019dbfed-9ad3-78a1-a6fa-710c1bb18d01`, `ok=true`, `thread_persistent=true`, `thread_turns_empty=true`, `assistant_responded=true`, `thread_idle=true`, and `listed_after_start=true`.

## [2026-04-24] add | Codex compact lane

Added `./te context codex-compact-thread` for same-session Codex compaction. It uses `CODEX_THREAD_ID` or an explicit `--thread-id`, resumes the thread with a Token Economy `compact_prompt`, calls App Server `thread/compact/start`, and treats success as `resume_ok=true`, `compact_start_ok=true`, and `compacted=true`. `summ` now has two Codex paths: compact current thread when continuity matters, or launch a persistent fresh successor when bypassing the old transcript is better. Disposable live smoke passed on thread `019dbffe-65ca-7441-9c1b-2a400a4e375a` with `ok=true`, `resume_ok=true`, `compact_start_ok=true`, and `compacted=true`.

## [2026-04-24] fix | manual Codex summ fallback

Added `prompts/summ-codex-manual.md` because older project-local Token Economy installs may not have `codex-compact-thread` or `codex-fresh-thread`. The manual prompt now includes a self-contained Python `codex app-server` fallback so agents do not stop after reporting that local `./te` is too old.

## [2026-04-24] fix | older Codex manual path

Changed `prompts/summ-codex-manual.md` to use one reliable path for older installs: launch a persistent fresh successor thread directly with App Server `thread/start` + `turn/start`. Same-thread compaction is skipped in older installs because inherited Codex config such as `tools.defer_loading` can make `thread/compact/start` fail.

## [2026-04-24] verify | manual Codex fresh successor

Ran the exact self-contained launcher from `prompts/summ-codex-manual.md` against handoff `.token-economy/checkpoints/20260424-153428-fresh-session.md`. It passed with `ok=true`, `thread_id=019dc021-4597-7560-81a5-900f4fafc950`, `thread_persistent=true`, `thread_turns_empty=true`, `assistant_responded=true`, `thread_idle=true`, and `listed_after_start=true`.

## [2026-04-24] clarify | manual summ handoff prompts

Added manual copy-paste prompts for the `summ` flow: `prompts/manual-summ-document-and-handoff.md` writes repo-root `session_handoff.md` after routing durable memory to a lightweight wiki-documenter, and `prompts/manual-fresh-session-from-handoff.md` starts a new context from only `start.md` plus that handoff. Reaffirmed that Claude `/clear` is the practical manual clear path, while Codex fresh successor is clean continuation only; Codex current-thread compact remains experimental/unsolved in the tested environment.

## [2026-04-24] simplify | summ procedure wording

Trimmed manual-session management text from the canonical `summ` procedure and context-refresh skill. The procedure now focuses on splitting handoff vs durable wiki memory, routing wiki documentation to a lightweight worker, writing/linting the handoff, and starting the next context from only `start.md` plus the handoff.

## [2026-04-25] add | full project migration prompts

Added `prompts/manual-full-summ.md` for exporting an old Claude Code project plus Obsidian wiki into one local `full_summ.md`, including raw secrets when explicitly authorized. Added `prompts/manual-import-full-summ.md` for bootstrapping a fresh Token Economy folder and rebuilding the repo-local markdown wiki from that summary without committing secrets.

## [2026-04-25] compile | superpowers lessons

Promoted Superpowers lessons from raw notes into `concepts/superpowers-skills.md`, added missing concept/pattern/people pages referenced by `index.md`, and added `skills/verification-before-completion/SKILL.md` for evidence-before-claims discipline.

## 2026-04-17

Terminology: **ComCom** = our compound-compression project (disambiguate from Claude Code's "CC").
- Wiki created. Folder: repo-local `Token Economy/` markdown wiki.
- Ingested research brief → `raw/2026-04-17-research-brief.md`.
- Setup confirmed: caveman plugin active, superpowers skill loaded, wiki initialized.
- Next: flesh out concept pages, pick first project (likely compound-compression-pipeline or wiki-query-shortcircuit).
- Built [[projects/compound-compression-pipeline/RESULTS]] (aka **ComCom**). Measured 70-73% on prose, 59% on mixed technical at gentler rate. Code/paths/URLs preserved via placeholder protection.
- Ingested [[raw/2026-04-17-semantic-diff-survey]]. Novelty 4/5. Created [[concepts/semantic-diff-edits]]. Added [[ROADMAP]] as live tracker.
- Ran quality eval on Ollama (phi4:14b, 3 tasks). Result: 55.7% token savings @ 100% quality retention at rate=0.5. Placeholder format fixed (`XPROTECT{n}XEND` survives BERT tokenization). Compressed prompts also faster (1.4s vs 9.8s observed).
- Built eval-v2: SQuAD v2 + gemma4:31b judge + bootstrap CIs + failure-mode classification. Running in background.
- Built [[projects/semdiff/README]] (AST-node diff). Measured 95.5% savings after 2 method edits on argparse.py (2575 lines, 19,280 → 859 tokens); 99.5% on stable re-read. Tree-sitter for py/js/ts/rust.
- Kaggle auth set up (user: saarshai).
- Built [[projects/context-keeper/README]]. Skill + PreCompact hook. Regex extractor + optional local-LLM pass. Current framework writes memory under repo-local `.token-economy/` paths.
- **Eval-v2 completed** (SQuAD v2, n=8, 2 runs, phi4:14b + qwen3:8b judge). Token savings **44.5% CI [41.5-47.4]**. Δscore **−0.25 CI [−0.62, 0.00]**. Failure modes on comp: 8 NONE, 6 MISSING, 2 SWAP. **v1's "55.7% @ 100%" overstated**; principled measurement shows small, non-significant quality hit. N too small to resolve CI. Judge swap (gemma4:31b → qwen3:8b) fixed 129s latency thrash.
- Built ComCom v2 (pipeline_v2.py) with question-aware + critical-zone protection; eval-v3 in progress (4 conditions: full, v1, v2, adaptive-escalation). Early data shows v2 over-compresses (critical-protect + rate=0.5 on remainder = total too low). Fix planned: scale rate by (1 - protected_fraction).
- **semdiff MCP server built**. Python 3.11 + mcp SDK. 3 tools exposed (read_file_smart, snapshot_clear, snapshot_status). Protocol roundtrip tested (initialize, tools/list, tools/call all pass). CC plugin wrapper at `plugin/.mcp.json`. Install docs at [[projects/semdiff/INSTALL]].
- **bench/ built**. Kaggle API wired via registry.yaml. 7 datasets registered (2 downloaded so far). Adapters emit uniform {id, context, question, answer, type, meta} schema. CoQA multi-turn items designed for growing-context stress. Kaggle Notebook template drafted for free-T4-GPU evals (30h/wk, 10× local throughput). See [[bench/README]].
- **Eval-v3 complete (ComCom upgrade)**. D_adaptive (self-verify escalation) delivers 44.9% savings at Δscore −0.12 [−0.38, 0.00] — quality effectively preserved. Zero REFUSE failures. C_v2 (question-aware + critical-zone) confirmed broken by over-compression; fix deprioritized since D_adaptive bypasses the issue. Shipped config: `pipeline_v2.compress` + `verify.escalate_gen`.

## [2026-04-20] download-status | Qwen3.6-35B-A3B-5bit | M1=complete, M1B=in-progress (authenticated curl running, ETA ~12h)
## [2026-04-20 22:36 BST] download-complete | Qwen3.6-35B-A3B-5bit | M1B all 5 shards verified (24.73 GB) via LAN HTTP server; shard1 required fresh download after dual-curl corruption; see /tmp/resume_qwen36_report.md
## [2026-04-20] download-finish | Qwen3.6-35B-A3B-5bit | M1=complete, M1B=complete (LAN transfer from M1:8888, all 5 shards verified, ~23GB, completed ~14:36 PDT)
## [2026-04-21] download-finish | Qwen3.6-35B-A3B-5bit | M1=complete, M1B=complete
## [2026-04-25 10:03 BST] install-verify | Qwen3.6-35B-A3B-5bit | M2 TurboQuant server running on /Users/saar/Library/gguf/qwen3.6-35b-q4km.gguf at CTX=524288; loaded via llama-server with -ctk q8_0 -ctv turbo4 on 127.0.0.1:8080
## [2026-04-25 10:03 BST] download-start | DeepSeek-R1-Distill-Llama-70B-Q4_K_M.gguf | M2 resumed from bartowski/DeepSeek-R1-Distill-Llama-70B-GGUF into ~/.cache/huggingface; transfer in progress, not yet installed
## [2026-04-25 10:33 BST] download-resume | DeepSeek-R1-Distill-Llama-70B-Q4_K_M.gguf | M2 background curl resumed /Users/saar/Library/gguf/DeepSeek-R1-Distill-Llama-70B-Q4_K_M.gguf.part from byte 75337728; lower-context install still in progress
## [2026-04-25 10:40 BST] download-progress | DeepSeek-R1-Distill-Llama-70B-Q4_K_M.gguf | M2 detached curl PID 5088 writing /Users/saar/Library/gguf/DeepSeek-R1-Distill-Llama-70B-Q4_K_M.gguf.part; partial file advanced to 100425728 bytes
## [2026-04-25 10:53 BST] exo-cleanup | M1/M1B | Removed EXO app bundles, ~/.exo state, EXO launch agents, and the M1 m1_local_watchdog cron entry; no residual EXO processes remain, Ollama jobs left running
