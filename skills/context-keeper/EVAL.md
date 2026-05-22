# EVAL — `context-keeper`

## Static cost (measured)

| field | tokens / size |
|---|---|
| description (always resident) | **80 tokens** (278 chars) |
| body (loaded on trigger)      | **360 tokens** (1240 chars) |
| tools/ payload                | 14.3 KB |
| model pin                     | `haiku` |
| effort pin                    | `low` |

## Live measurement (extraction fidelity, N=1 real transcript)

Harness: `eval/runner_keeper.py` — feeds the extract.py script a real transcript JSONL and counts (a) compression vs raw transcript, (b) per-category recall against a regex ground-truth count.

Input: 970-event session transcript from this project (`7523878a-…jsonl`).

| metric | value |
|---|---|
| raw transcript | **493.7 KB** (970 events) |
| extracted sidecar | **11.3 KB** |
| **compression vs raw** | **2.3% of original (-97.7%)** |
| extract latency | 973 ms |
| URL recall | **100%** of 22 distinct URLs |
| Number-fact recall | **67%** of 63 (measurements survive) |
| Command recall | **46%** of 87 distinct `Bash` cmds |
| Error recall | 25% of 111 error/exception lines (top-N by frequency) |
| File recall | 22% of 264 path mentions (top-N — paths are most numerous and most repeat) |

Interpretation: the extracted sidecar is **~44× smaller** than the source transcript while capturing **100% of URLs, 67% of numeric measurements, and ~half of distinct shell commands** — exactly the high-value tail that a generic `/compact` summariser tends to drop. URLs and measured numbers are the items most likely to be re-needed after compaction; full file lists are recoverable from git.

Tokens-saved framing: without the hook, recovering an arbitrary one of these post-compaction requires re-reading transcript pages (`Read` calls) or re-running commands. A single `Read` of even a small file usually exceeds the entire sidecar's token cost.

## Methodology

```bash
python3 eval/runner_keeper.py /path/to/transcript.jsonl
```

The runner:

1. Parses every event in the transcript.
2. Regex-extracts distinct files, commands, errors, URLs, numbers — the ground-truth.
3. Invokes `skills/context-keeper/tools/extract.py` against the same transcript.
4. Scores per-category recall (how many ground-truth items appear in the extracted markdown).
5. Reports compression ratio + latency.

To re-run on a different transcript or with the optional LLM-decision-extraction pass:

```bash
python3 eval/runner_keeper.py <transcript.jsonl> --llm gemma4:31b
```

## Failure modes

- Path recall is low because the extractor keeps a top-N-by-frequency cut to avoid bloating the sidecar. The rare paths that appear once are dropped; git/wiki are the right place for those.
- Errors recall is low when many errors are near-duplicates (e.g. the same `KeyError` raised 30 times). The extractor de-duplicates; raw recall counts them all.
- LLM pass (`--llm gemma4:31b`) is OFF by default in this measurement; enabling it raises decision/next-step recall at the cost of ~30 s extra latency.

## Lineage

Pattern aligned with coleam00/claude-memory-compiler (SessionEnd → distillation). This skill targets PreCompact specifically — intra-session memory survival, not cross-session synthesis.
