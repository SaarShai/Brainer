# compliance-canary — eval status

**Status:** v1.5.1. Hook correctness verified by [tools/test.sh](tools/test.sh); offline drift baselining via [tools/measure.py](tools/measure.py).

## Verified — unit

See [tools/test.sh](tools/test.sh). Headline cases:

- Each detector kind triggers when it should and stays silent when it shouldn't
- Anti-spam cooldown suppresses repeat fires
- Custom regex + custom claim_pattern honored
- Bootstrap probes (`caveman-ultra` filler + word-creep, `verify-before-completion` unverified-done) fire on synthesized transcripts
- Malformed `drift_probes.json` → skill skipped, hook proceeds
- Empty / missing transcript → silent
- Two sessions interleaved → independent probe-history
- 10 parallel invocations → state-locked
- State GC at session-start

## Verified — live e2e

`claude -p` haiku session: forced the model to emit a verbose, filler-laden reply, then a follow-up prompt. The next UserPromptSubmit's transcript-attached `hook_success` payload contains a `<system-reminder>` listing the fired probes (filler-phrases + word-creep), with the matched evidence snippets.

## What this gives you that nothing else does

- [delta-hq/cc-canary](https://github.com/delta-hq/cc-canary) reads transcripts **offline** and reports drift after the fact. Useful for analysis, useless mid-session.
- Cursor `alwaysApply` re-injects the same rule every turn, regardless of whether the rule was followed.
- `skill-pulse` re-anchors unconditionally every N turns.

`compliance-canary` is the only piece that **detects drift in the running session and intervenes with a targeted, evidence-quoting reminder**.

## Offline measurement (addresses out-of-scope item 2)

`tools/measure.py` runs the production detectors against any transcript JSONL with no side effects:

```bash
python3 tools/measure.py ~/.claude/projects/<proj>/<sid>.jsonl
python3 tools/measure.py ~/.claude/projects/*/*.jsonl --summary
```

Lets a user:

1. **Baseline before installing** — measure how much drift their existing sessions show
2. **Tune thresholds** — adjust `word_count_per_message.threshold` based on actual session distributions
3. **Validate new probes** — sanity-check a new regex against past transcripts before declaring it in `drift_probes.json`
4. **A/B compare** — run measure.py on sessions captured pre-install vs. post-install to quantify uplift

The data plan for in-the-wild measurement (paper-style):

1. Capture N=50+ long sessions (>20 turns) without the hook → baseline drift rates per probe
2. Install hook, capture N=50+ matched sessions → post-install drift rates
3. Compare trigger-rate distributions; expected outcome: probe trigger rates drop because the corrective text reduces repeat violations within a session

## Self-test

```bash
bash skills/compliance-canary/tools/test.sh
```

## Out of scope

- LLM-judge probes (semantic, not syntactic). Cleanest v2 add.
- Edit-vs-Write tool-choice drift detector. Easy v2 add.
- Cross-session drift trends (week-over-week regression in a project). Belongs in `wiki-memory` long-term, not here.
