---
name: write-gate
description: Decide whether a candidate fact deserves persistent memory. Use before writing to wiki-memory, CLAUDE.md, AGENTS.md, or any cross-session store. Scores content on signal (decisions / errors / architecture / code) and rejects reasonless decisions (must embed because… / so that… / to avoid…). Prevents memory pollution at source.
effort: low
tools: [Bash, Read, Grep]
pulse_reminder: before writing durable memory, run write-gate. Reasonless decisions and trivial recaps don't earn a page.
---

# write-gate

Content-quality gate for persistent memory. Sits between "I think this should be remembered" and the actual write to wiki-memory / CLAUDE.md / any cross-session store.

Two-layer policy:

1. **Execution gate** (existing) — fact came from an action that *executed* and *succeeded*. Plans don't earn pages.
2. **Content gate** (this skill) — fact has signal AND, if it's a decision/convention, gives a reason.

The execution gate is the job of [`verify-before-completion`](../verify-before-completion/SKILL.md) (evidence-first: a fact only earns a page once the action that produced it ran and passed). This skill adds the **content gate**. Both are **procedure gates** — agent steps in `wiki-memory`'s write protocol (`SKILL.md` step 3 instructs running `write_gate.py gate` before a write), not code auto-invoked by `wiki.py`. So the gate fires when the protocol is followed; it is a manual/CLI gate, not enforced inside the write path.

## When to call

Before any persistent write:

- `python skills/wiki-memory/tools/wiki.py new …` — wiki-memory's own write path
- direct edits to `CLAUDE.md`, `AGENTS.md`, `GEMINI.md`
- `mcp__memory__*` writes
- any "save this for later" action

Trigger phrases: "remember that …", "log this …", "add to memory", "record …", "write a note about …", "this should go in the wiki". (A `prompt_intent` drift probe fires on these so the gate isn't skipped.)

## What earns a memory (and which store)

The gate is about *quality*; the *contract* is about shape. Record **corrections AND confirmed approaches alike**, each with the **why** it mattered. Don't store what the repo, the code graph, or chat history already records. **Update an existing note rather than creating a duplicate** (`wiki.py overlap` flags near-matches). **Delete a note that turns out wrong** — git is the archive; a falsified non-protected page is removed via [`wiki-refresh`](../wiki-refresh/SKILL.md)'s Delete outcome.

Two stores, two shapes — don't conflate them:
- **The cross-session memory dir** (`~/.claude/projects/<proj>/memory/`, harness-owned): **one fact per file**, with a **one-line summary at the top** (the frontmatter `description:`). Atomic by contract.
- **The repo wiki** (`wiki/`): prefers **fewer, richer domain-level pages** over many thin one-off pages — consolidation, not atomicity. Same why-clause + signal gate; different granularity.

## How it scores

Signal score = sum of weighted features in the candidate text. Threshold defaults to **3.0** (tunable per project in `wiki/L0_rules.md`).

| Feature | Weight | Match |
|---|---:|---|
| Decision marker | +2.0 (cap ×2) | "we decided", "chose X over Y", "going with", "rejected", etc. |
| Error / failure | +2.0 (cap ×2) | "failed because", "fix:", "bug:", regex `error\|panic\|traceback` in cited evidence |
| Architecture / system fact | +1.5 (cap ×2) | "runs on", "calls", "depends on", named systems / dirs / endpoints |
| Code block present | +1.0 (cap ×2) | fenced ` ``` ` block; inline `` ` `` ticks count at half-weight |
| Exact numbers / measurements | +1.0 (cap ×2) | regex `\d+(%|ms|s|x|ops|qps|MB|GB|tokens)\b` |
| Why-clause present | +1.0 | one of the why-clause phrases below appears in prose (not inside a code fence) |
| Procedure (≥2 ordered steps) | +2.0 | numbered/bulleted lines (`1. …` / `- …`) — SOP signature |
| Named entity overlap | +0.5 each (capped 1.5) | repeated capitalized identifiers / paths |
| Filler / recap | −1.5 each | "in summary", "to recap", "as I mentioned", "basically what we did" |
| Speculation | −1.5 each | "might", "probably", "I think", "seems like", "could maybe" |

If the text is classified as a **decision or convention** (decision-marker hit OR `kind: decision` frontmatter), it must additionally contain a why-clause. Accepted phrases:

> `because …` | `so that …` | `to avoid …` | `in order to …` | `due to …` | `in favor of …` | `rather than …` | `the reason …`

Note: `since` is intentionally absent — it's overwhelmingly temporal in practice ("tracked since yesterday") and was bypassing the gate as a pseudo-causal token. Use `because` or `in order to` instead.

Decisions without why-clauses are rejected outright, regardless of signal score.

**Trust bypass (recall).** The score measures lexical *signal density*, not *importance* — a genuine atomic fact with no marker words (e.g. "the PROMPTER folder is also called alfred") scores ~0 and is dropped (measured: ~82% false-reject on bare keep-worthy facts). So a candidate whose provenance is vouched-for bypasses the signal **floor**: `trust: verified` or `user_confirmed` (read from the candidate's frontmatter, or passed via `--trust`) passes even at score 0. Trust vouches importance, **not quality** — net-negative content (filler/speculation penalties) is still rejected, and only `user_confirmed` (a human said keep it) waives the why-clause for a decision; plain `verified` still demands it. This raises recall on vouched content while leaving precision on un-vouched content unchanged. It is the principled form of the manual override below.

Source for the formula: [ogham-mcp/ogham-mcp](https://github.com/ogham-mcp/ogham-mcp) (signal-score lifecycle, 91.8% QA / 97.2% R@10 on LongMemEval). Source for the why-clause requirement: [codenamev/claude_memory](https://github.com/codenamev/claude_memory) (100% on 100-case FEVER-derived test).

## CLI

```bash
# score a piece of text from stdin or a file
python skills/write-gate/tools/write_gate.py score --kind fact < candidate.md
python skills/write-gate/tools/write_gate.py score --kind decision --text "We chose pgvector over Qdrant because dev parity"

# explain why something was rejected
python skills/write-gate/tools/write_gate.py explain --text "Basically we did some stuff with the database."

# integrate as a precheck in another script
python skills/write-gate/tools/write_gate.py gate --kind decision --file ./candidate.md && echo "write it" || echo "rejected"

# a vouched-for atomic fact bypasses the signal floor (--trust, else read from frontmatter)
python skills/write-gate/tools/write_gate.py gate --kind fact --trust verified --text "The PROMPTER folder is also called alfred."
```

Exit codes:
- `0` — gate passed (signal ≥ threshold, why-clause present if decision)
- `1` — rejected (signal below threshold OR missing why-clause)
- `2` — bad input / usage error

## Protocol

Before persistent write:

1. Run `write_gate.py gate --kind <kind> --file <candidate>`.
2. On exit 0: proceed with write.
3. On exit 1: read the explanation. Either revise the candidate (add the reason, cite evidence, drop the filler) or drop the write entirely. Do not bypass.
4. Override is only legitimate when the user explicitly says "save it anyway" or "I know it's thin, save it". Record it as user-directed in the write target or `wiki/log.md`:

```json
{
  "write_gate": "rejected",
  "override": "user_directed",
  "override_reason": "User explicitly wants this remembered despite gate rejection."
}
```

There is no agent-only override.

## Anti-patterns

- Don't gate non-persistent state (todos, scratch pads). The gate is for stuff that will be re-read across sessions.
- Don't tune the threshold higher than 4.5 — at that point you reject almost everything and the wiki goes stale. Default 3.0 is calibrated to ogham's reported retrieval numbers.
- Don't combine this gate with an LLM-judge gate in series unless you've measured that the judge actually catches things the rules miss; double-gating doubles latency for marginal gain.

## Related skills

- [`wiki-memory`](../wiki-memory/SKILL.md) — owns the actual write path; this skill is its precheck.
- [`verify-before-completion`](../verify-before-completion/SKILL.md) — execution-gate sibling; together they enforce "no execution, no memory; no reason, no decision."
- [`wiki-refresh`](../wiki-refresh/SKILL.md) — reconciles stored memories against the codebase after they pass this gate.

## Configuration

Optional `wiki/write_gate_config.yaml` overrides `threshold` (default 3.0), `require_why_for_decisions`, and any of the `weights` / `filler_phrases` from *How it scores* above. Absent → defaults. Measured: f1 0.96 (precision 1.0) on a 56-case labeled set (`eval/exp3_classifiers/`).
