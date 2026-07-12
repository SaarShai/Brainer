# standing-orders — deep-dive reference

Companion to [`SKILL.md`](SKILL.md): the tuning guide, negative-test/
premortem doctrine, and design rationale that don't need to load on every
trigger. Content moved here verbatim from `SKILL.md` — nothing deleted, only
relocated to keep the always-loaded body under the split threshold.

## (d) Tuning

- Patterns live in [`drift_probes.json`](drift_probes.json)'s `pattern`
  field per probe; edit in place (both are single Python `re` strings with
  a leading `(?i)`).
- Fixture corpora: [`tools/corpus_tuning.jsonl`](tools/corpus_tuning.jsonl)
  (the primary tuning set this skill was built against) and
  [`tools/corpus_holdout.jsonl`](tools/corpus_holdout.jsonl) (adversarial,
  vocabulary-disjoint from the tuning set — evaluated by the same test with
  the same floors when present, absent is not a failure).
- Re-run the gate after any pattern edit:
  ```bash
  python3 skills/standing-orders/tools/test_standing_orders.py
  ```
  It invokes the REAL `compliance-canary` hook (not a regex re-implementation)
  the same way `eval/behavior/e1_probe_pr.py` does — a fresh session id per
  case, `COMPLIANCE_CANARY_SKILLS_ROOT` pointed at this repo's `skills/`, and
  detects a fire by the unique message signature `[standing-orders] ORCH` /
  `[standing-orders] DEEP` appearing in the hook's stdout. Floors: ORCH
  recall ≥0.85 over `orchestrate`+`both`, DEEP recall ≥0.85 over
  `deep`+`both`, zero fires on `none`-labeled prompts, each probe fires at
  most once per prompt.
- `json.loads` + `re.compile` on both patterns is the cheapest first check
  before running the full behavioral gate — a syntax error surfaces
  immediately instead of as a silent zero-recall run.

## Failure modes

Premortem ([`LEARNING_CONTRACT`](../_shared/LEARNING_CONTRACT.md) §8):

- **Silent-failure path** — a pattern edit that widens or narrows a regex without
  re-running `tools/test_standing_orders.py` ships with no signal that recall
  dropped or a false-fire appeared; the probe still "looks armed" (it parses,
  `compliance-canary` still discovers it) while silently missing the class of
  prompt it was meant to catch, or nagging on prompts it shouldn't. There is no
  CI wiring that runs this test automatically today — see the negative-test note
  below.
- **Rot-when-unwatched** — the corpus fixtures (`tools/corpus_tuning.jsonl`,
  `tools/corpus_holdout.jsonl`) are a snapshot of today's phrasing; as real usage
  surfaces new decomposable-work or strategy phrasings this skill's regexes don't
  yet cover, the gap grows unnoticed unless someone periodically adds the missed
  prompt to a corpus and re-runs the gate — nothing forces that addition.
- **No-hooks host** — on a host with no `UserPromptSubmit` hook (see Honest
  limitations above), both probes are inert; the mechanical enforcement this
  skill exists to provide reduces to the resident-catalog prose rule, and a
  hookless-host regression (the hook silently stops being invoked, e.g. a
  broken `.claude/settings.json` wiring) would produce zero fires with zero
  error — indistinguishable from "nothing decomposable happened this session"
  without independently checking the hook actually ran.

`tools/test_standing_orders.py` is this skill's negative-test artifact: it
asserts `none_fires == 0` over 28 known-bad (non-triggering) prompts across two
corpora — a regression that makes either probe fire on a `none`-labeled prompt
trips it, and it invokes the REAL hook (not a regex reimplementation), so a
detector-level regression in `hook.py` itself would also be caught.

## (e) Relationship to team-lead / ORCHESTRATION §6 / loop-engineering

This skill does not restate `team-lead`'s protocol, `ORCHESTRATION.md`'s
cost doctrine, or `loop-engineering`'s loop-shape design — it is the
**mechanical trigger** that gets those protocols into context at the right
moment, the same relationship `loop-engineering`'s own now-retired
`fleet-orchestration-intent` probe had to it. That probe's full pattern
content is absorbed verbatim into `orch-tier-intent` here (see the probe's
`_note`); `loop-engineering/drift_probes.json` no longer ships it, so the
fleet-orchestration trigger surface lives in exactly one place now, not two.
`team-lead`'s own trigger ("lead, orchestrate, use your team, use builders")
stays a separate, narrower, session-model-gated trigger (only fires when the
session model is frontier-tier) — `standing-orders`' ORCH tier is broader
(any host, any model, fires on the SHAPE of the work, not on the word
"lead") and inlines the specific standing-orders doctrine (goal-writing,
GLM-5.2-first ladder, cross-vendor advisor, three stop conditions) that
`team-lead` cross-references rather than restates.
