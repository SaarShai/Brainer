---
type: project
tags: [roadmap, tracking]
confidence: high
---

# Token Economy — Roadmap

Live tracker. Directions, status, next steps. Update after every experiment.

## Directions (ranked by leverage × feasibility)

| # | Direction | Leverage | Effort | Status |
|---|---|---|---|---|
| 1 | ComCom (compound compression) pipeline (caveman + LLMLingua + prefix-cache + structured-out + self-verify) | 80-90% total | med | **EVAL-V3 (SQuAD, n=8): D_adaptive wins**. 44.9% savings, Δscore −0.12 [−0.38, 0.00] (CI touches 0 = quality effectively preserved). Zero REFUSE failures. Config: `compress(rate=0.5) → escalate_gen(rates=(0.5, 0.7, None))`. |
| 2 | Semantic-diff file re-reads (AST cache per session, diff-on-reread) | 5-20x on large files | med-high | **MCP SERVER BUILT** — works with any MCP client. CC plugin wrapper included. 95.5% measured on argparse.py. See [[projects/semdiff/INSTALL]] |
| 3 | Prefix-cache architect skill (audit prompts, maximize cacheable prefix) | 70-90% on repeated calls | low | Not started |
| 4 | Wiki-query short-circuit (prompt/tool hook searches repo-local markdown wiki before full research) | variable, high on repeat topics | low | Not started |
| 5 | Tiny-model router (0.5B classifier → local vs remote) | 50-95% on classification tasks | med | Not started |
| 6 | Brevity-calibrated eval benchmark (arxiv 2604.00025 extension) | publishable contribution | med | Not started |
| 7 | Skill-level prompt caching (pre-warm top-N skills at startup) | 10-30% per session | low-med | Not started |
| 11 | **context-keeper** — structured PreCompact state preservation (files/cmds/errors/decisions/failures) | prevents info loss across compaction, reduces repeat-mistake cost | low | **PROTOTYPE WORKING** — extracts structured memory to repo-local `.token-economy/` paths by default. See [[projects/context-keeper/README]] |
| 8 | Cross-session KV persistence for Ollama/llama.cpp daemon | huge on local | high | Not started |
| 9 | Domain-aware compress grammars (math/code-specific) | +10-20% over generic | low | Idea |
| 10 | ReAct → JSON structured tool skill | ~50% per reasoning step | low | Idea |

## Done
- **2026-04-17**: Repo-local markdown wiki initialized. Caveman-style terseness active.
- **2026-04-17**: Initial landscape research (Sonnet 4.6) → [[raw/2026-04-17-research-brief]].
- **2026-04-17**: Semantic-diff prior-art survey → [[raw/2026-04-17-semantic-diff-survey]]. Novelty: 4/5.
- **2026-04-17**: ComCom (compound compression) pipeline prototype built + tested on 2 samples. Measured 59-73% savings. → [[projects/compound-compression-pipeline/RESULTS]]
- **2026-04-17**: Quality eval via Ollama (phi4:14b). **55.7% savings @ 100% quality retention** at rate=0.5. Placeholder bug found + fixed. Latency bonus: compressed prompts run faster.
- **2026-04-17**: Eval-v2 harness built (SQuAD v2, gemma4:31b judge, bootstrap CIs, failure-mode classification, matched tokenizer via Ollama prompt_eval_count). Running in background.
- **2026-04-17**: **semdiff** built. Tree-sitter-based AST-node diff. Py/JS/TS/Rust. Tested on argparse.py (2575 lines): 95.5% savings after 2 method edits, 99.5% stable re-read. See [[projects/semdiff/README]]
- **2026-04-17**: **bench/** infrastructure built. Registry of 7 datasets (SQuAD, CoQA, SciQ, code-bug-fix, BBC News, LongBench, rejected code-refactoring-120k). `fetch.py` CLI pulls from Kaggle or HF. Adapters (CoQA, SQuAD, refactoring) emit uniform eval-item schema. CoQA adapter builds growing-context multi-turn items (ideal for ComCom + context-keeper stress). Kaggle Notebook template for free-T4-GPU runs. See [[bench/README]].
- **2026-04-17**: **context-keeper** built. Parses transcript JSONL, regex-extracts structured state (goals, files, commands, errors, numbers, failures) + optional LLM pass (local gemma4:31b) for decisions/next-steps. PreCompact hook prints terse pointer so summarizer preserves path to memory file. Tested on current session: 68 files touched, 21 commands, 21 errors logged. See [[projects/context-keeper/README]]

## Next steps (prioritized)

### Immediate (this session or next)
1. **Quality eval for compound pipeline.** Run compressed vs original prompts against Haiku 4.5 on a 10-task mini-benchmark (summarize, extract, code-explain). Need: accuracy delta vs token delta → isoquality point.
2. **Long-input test.** Pipeline on a 5K-token startup adapter file or paper abstract; measure if savings scale.
3. **Add structured-output stage.** Append "respond only as {json schema}" hint, measure output-token cut on a tool-use sample.

### Short-term (next few sessions)
4. Wrap pipeline as a model-agnostic skill + optional project-local hook.
5. Pick semantic-diff prototype: small Python+tree-sitter MCP tool, file-snapshot cache, re-read diff.
6. Build prefix-cache architect as a read-only audit skill.

### Medium-term
7. Brevity eval benchmark (standalone publishable).
8. Tiny-model router (needs Ollama setup verified).

### Carry-overs from archived HANDOFF_NEXT_AGENT
9. **Codex context-refresh docs.** Reword so current-thread clear and fresh-successor continuation are clearly distinct. Claude `/clear` is the explicit manual-clear path; Codex current-thread clear remains unsolved in the tested environment. *(Partially addressed 2026-05-08: archived `summ-codex-manual.md`, removed `codex-compact-thread`. Remaining: any operational doc still implying same-thread clear is solved.)*

### Open measurements
10. **Measure `agents-triage` net token savings.** SKILL.md claims "~70-90% token cost reduction on simple tasks, per our informal estimate. Verification pending." The hook is default-on for every UserPromptSubmit. Run a real session benchmark: same task list, with vs without the hook, measure (a) end-to-end token cost and (b) classification false-positive rate. If net savings <30% on a representative session mix, demote the hook to opt-in (`./INSTALL.sh --with-triage` or env flag). If net savings ≥30%, keep default-on and document the measured number in `stable/README.md`.

## Open questions
- Does llmlingua-2 output degrade model accuracy more than the token savings are worth? Need eval.
- Can we cascade: caveman → llmlingua → caveman again? Does second pass compound or noop?
- Is there a detectable "quality cliff" rate per task type?
- For API models with prompt caching, does pre-compressing break cache reuse? (Cache is byte-exact.)

## Contradictions / flags
- None yet.

## Related pages
- [[index]]
- [[raw/2026-04-17-research-brief]]
- [[raw/2026-04-17-semantic-diff-survey]]
- [[projects/compound-compression-pipeline/RESULTS]]
- [[concepts/semantic-diff-edits]]
