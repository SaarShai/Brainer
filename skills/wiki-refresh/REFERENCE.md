# wiki-refresh — deep-dive reference

Extended reference material for [`SKILL.md`](SKILL.md): the nine (+disuse) quality-scan
verbs and the opt-in staleness-nudge hook / stale-marking convention. Consult this when
drilling into a specific epistemic lens or wiring the opt-in nudge — not on every
reconcile pass.

## Quality-scan verbs

The nine report-only epistemic lenses from the OKF review (code lives in
[`wiki-memory`](../wiki-memory/SKILL.md)'s `tools/wiki.py`; documented here because
the refresh pass is what consumes them). Heuristic aids, never gates. **Start with
`health`** — one pass across all lenses with rolled-up actionable counts (`0` =
healthy); drill into the verb behind any non-zero count.

```bash
python3 skills/wiki-memory/tools/wiki.py health              # ONE-PASS epistemic health — start here
python3 skills/wiki-memory/tools/wiki.py contradict-scan     # contradiction candidates (see Emit contradiction edges)
python3 skills/wiki-memory/tools/wiki.py novelty             # intra-page redundancy_index (echo-vs-synthesis)
python3 skills/wiki-memory/tools/wiki.py claim-ground <id>   # prose claims whose cited artifact is gone
python3 skills/wiki-memory/tools/wiki.py claim-audit         # data/directive/judgment mix per page
python3 skills/wiki-memory/tools/wiki.py synth-candidates    # same-subject clusters ripe for a synthesis note
python3 skills/wiki-memory/tools/wiki.py maturity            # observation→hypothesis→rule promotion/demotion
python3 skills/wiki-memory/tools/wiki.py gaps                # recurring wikilink targets with no page
python3 skills/wiki-memory/tools/wiki.py calibration         # confidence-vs-evidence drift
```

How each feeds the five outcomes:

- **`maturity`** — separate axis from trust. **Promotion** candidates (hypothesis/observation pages still `trust: asserted` but cited often) route into Update/Consolidate; each carries `corroborating_inbound` (citations *from observation pages* are evidence accrual, distinct from popularity) and `has_falsifier` (a rule earns its status only by stating what would falsify it — a candidate without one is flagged "state a falsification condition first"). **Conflict-driven demotion** (a rule/verified page carrying `contradicts:`) routes into the contradiction pass below — review, don't silently trust.
- **`synth-candidates`** — inverse of dedup: clusters distinct same-subject pages (≥2 shared tags) ripe for a higher-order synthesis note → Consolidate. The agent writes the synthesis; clusters with a likely existing parent are flagged. Tag-based edges only (wikilink edges over-cluster — measured).
- **`claim-audit`** — grades claims by epistemic class ([`claim_grade.py`](../wiki-memory/tools/claim_grade.py)); judgment-heavy weak-evidence pages → Replace/Delete review. Per-claim typing is measurably noisy (~40% unanimous annotator agreement on messy SOP prose) — read aggregate ratios, never single labels; the grader abstains (`unknown`) on unmarked text.
- **`gaps`** — what's MISSING: recurring `[[wikilink]]` targets with no page, ranked by reference frequency (≥N refs = real gap; a one-off is a typo) → write the canonical page or fix the stale link. Curated pages only (raw/ frozen).
- **`calibration`** — a page's stored `confidence` vs its actual evidence (sources + inbound corroboration + trust tier + verified-freshness, 0–4). Flags over- and under-confidence → Update the scalar or verify the page. Sharp/low-noise (live: 1 over, 1 under of 42).
- **`novelty`** — intra-page tautology (page echoes its own headings/schema/refs); a write-gate / refresh signal → Update or Replace.
- **`claim-ground`** — sentence-granular grounding finer than `audit-refs`; the "does present code still match the prose" judge step for the Update-vs-Replace call.
- **`disuse`** — a tenth signal, distinct from the nine above: code lives in **wiki-refresh's own** [`tools/disuse.py`](tools/disuse.py), not `wiki.py` (it's read-value, not code-groundedness). Consumes the retrieval-usage ledger (`wiki/.brainer/usage.json`, written by `wiki.py fetch`) as a prune/review candidate signal — a page written but never fetched back out is cost without payoff. Report-only, same posture as the rest of this table: it flags candidates, it does not delete.

```bash
python3 skills/wiki-refresh/tools/disuse.py report --root wiki   # {page, reads, age_days, candidate} per concepts|queries|patterns page
```

A page is a `candidate` only when reads are at/below threshold (default 0) **and** it's older than a grace window (default 30 days, via `--grace-days`) — a brand-new page with 0 reads hasn't had a chance to be read yet, so age alone doesn't disuse it. `candidate: true` → route into Delete/Replace review per the gates below; a 0-read page whose domain is still live is a **Keep** or **Update** candidate for discoverability (bad title/tags), not necessarily a Delete. Missing/empty/malformed `usage.json` degrades to an empty signal (every page reports `reads: 0`, gated on age alone), never a crash.

## Optional: staleness nudge (opt-in hook)

`staleness.py` gates *when* to bother reconciling — nudge only when HEAD moved past the last full reconcile, never every session. `is-stale` returns JSON (`stale`, `stored`, `head`, `changed`, `code_changed`; the two counts are `null` when the marker commit is unreachable, never a fake 0). Only `nudge` is hook-safe — it always exits 0 and prints nothing on the no-op/fresh path (zero cache churn); `is-stale` exits 1 on fresh *by design*, so don't wire it under `set -e`. Wire by hand (output-filter precedent — shipped, not auto-installed) as a `SessionStart` hook in `.claude/settings.json`:
```json
{ "hooks": { "SessionStart": [ { "hooks": [ { "type": "command", "command": "python3 skills/wiki-refresh/tools/staleness.py nudge --root \"$CLAUDE_PROJECT_DIR\"" } ] } ] } }
```

## Stale-marking (headless ambiguous cases)

Add to frontmatter, do not guess an action:
```yaml
status: stale
stale_reason: "<what drifted / what's missing>"
stale_date: <today>
```
