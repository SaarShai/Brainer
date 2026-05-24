---
name: memory-decay
description: Use weekly/monthly (or before a wiki audit) to apply time-based confidence decay to wiki-memory pages. Triggers on "/decay", "audit the wiki", "are these facts stale?". Old unverified facts should not be retrieved with the same weight as fresh ones. Errors / lessons-learned / high-evidence pages bypass decay (protection class). Dry-run by default; apply only with --apply.
effort: low
tools: [Bash, Read, Glob]
pulse_reminder: stale facts retrieved as fresh are worse than missing facts. Decay weekly; protect error notes.
---

# memory-decay

Time-based confidence decay for `wiki-memory` pages. Companion to [`write-gate`](../write-gate/SKILL.md): write-gate controls what enters the wiki; memory-decay controls how that confidence ages.

Default model: **exponential decay, half-life ≈ 405 days, 5% per 30 idle days** — published from [ogham-mcp/ogham-mcp](https://github.com/ogham-mcp/ogham-mcp) (91.8% QA on LongMemEval with this decay shape).

Formula:

```
λ = -ln(0.95) / 30                  # ≈ 0.001709 per day
confidence_new = confidence_old * exp(-λ * days_idle)
days_idle      = today - max(verified, updated, created)
```

## Protection class

Per [doobidoo/mcp-memory-service](https://github.com/doobidoo/mcp-memory-service)'s finding (80.4% R@5 on LongMemEval): **mistake notes and high-evidence pages should not decay.** A lesson learned 18 months ago is just as protective today.

A page is protected when ANY of:

- frontmatter `type:` ∈ {`error`, `lesson`, `sop`, `procedure`}
- frontmatter has `protected: true`
- `evidence_count` ≥ 3
- page lives under `wiki/L0_rules.md` or `wiki/L3_sops/`
- page lives under `wiki/raw/` (immutable by schema)

Protected pages report their idle days but never have confidence rewritten.

## When to run

- **Weekly cron** for active projects.
- **Before a wiki audit** ("which facts are stale?").
- **After importing a large batch** of historical content.
- Never on every prompt — decay is a slow process, not a per-turn computation.

## CLI

```bash
# default: dry-run on ./wiki, show what WOULD change
python skills/memory-decay/tools/decay.py

# apply changes (rewrites frontmatter)
python skills/memory-decay/tools/decay.py --apply

# custom root
python skills/memory-decay/tools/decay.py --root /path/to/wiki --apply

# tune the half-life — λ adjusts to whatever rate you pick
python skills/memory-decay/tools/decay.py --halflife-days 365

# emit machine-readable JSON
python skills/memory-decay/tools/decay.py --json

# only pages whose decayed confidence drops below threshold (archive candidates)
python skills/memory-decay/tools/decay.py --archive-candidates 0.3
```

## Exit codes

| Code | Meaning |
|---|---|
| 0 | success (dry-run reported, or --apply completed cleanly) |
| 1 | partial failure — one or more pages couldn't be parsed/written |
| 2 | usage error (no wiki found, bad args) |

## What it changes (and what it doesn't)

**Changes** only the `confidence:` field in v2 frontmatter. Does not touch:

- page body content
- any other frontmatter field
- file modification time (uses `os.utime` to preserve)
- protected-class pages

**Does NOT auto-archive.** It can flag candidates with `--archive-candidates 0.3`, but moving pages to `wiki/L4_archive/` is a human-supervised step.

## Integration

`wiki-memory`'s retrieval (search → timeline → fetch) already weights by `confidence`. Running decay weekly keeps that weighting honest: a fresh 0.9 page outranks a year-old 0.9 page that's actually decayed to 0.49.

If you want decay to flow into retrieval automatically without rewriting frontmatter, set `MEMORY_DECAY_INLINE=1` and update `wiki-memory`'s scoring to compute `effective_confidence = confidence * decay_factor` at query time. (Future work; currently the rewrite path is the only flow.)

## Anti-patterns

- **Don't decay per prompt.** The whole point is amortizing the computation — running on every turn just burns tokens.
- **Don't decay below 0.05.** At that point the page is functionally invisible; move it to `wiki/L4_archive/` and reclaim the index slot.
- **Don't combine decay with deletion.** Decay marks; humans (or `/consolidate-memory`) decide whether to archive.
- **Don't apply decay to pages with `evidence_count` you've never bumped.** If you never increment evidence on retrieval, every page looks stale by month 6 and you're effectively erasing your wiki on a schedule. Either bump evidence on access, or set a longer half-life.

## Configuration

Optional `wiki/memory_decay_config.yaml`:

```yaml
halflife_days: 405          # 5%/30d default; tune up for stable projects
protected_types: [error, lesson, sop, procedure]
protected_dirs: [L0_rules.md, L3_sops, raw]
evidence_count_threshold: 3
archive_below: 0.0          # 0 = never auto-flag (default)
```

## Related

- [`write-gate`](../write-gate/SKILL.md) — entrance bouncer.
- [`wiki-memory`](../wiki-memory/SKILL.md) — what this skill writes into.
- `/consolidate-memory` — separate Anthropic skill that does merge/dedup; memory-decay is its time-based companion.

## Status

Skill body + tool + smoke tests shipped. Parameters track ogham + doobidoo published numbers. EVAL.md notes the integration target with wiki-memory's retrieval scoring.
