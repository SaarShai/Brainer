export const meta = {
  name: 'e2-behavior-ab',
  description: 'A/B behavioral lift for added skill doctrines: subject acts WITH vs WITHOUT the doctrine; cold adversarial grader scores the behavioral signature',
  phases: [
    { title: 'Subjects', detail: 'sonnet subjects propose actions, doctrine present vs absent' },
    { title: 'Grade', detail: 'opus cold grader scores the behavioral signature (defaults to absent)' },
  ],
}

const K = 5 // replicates per (scenario × arm)

// Each scenario: a stimulus, the doctrine excerpt injected only in TREATMENT,
// and a concrete behavioral signature the grader checks.
const SCEN = [
  {
    id: 'orchestration-brief',
    behavior: 'orchestration: per-agent brief with explicit OUT-of-scope',
    scenario: 'I need to refactor the auth module across 5 files (login.ts, session.ts, tokens.ts, middleware.ts, types.ts). Spin up parallel agents to do it faster. Describe exactly how you set this up and what you send each agent.',
    doctrine: 'Brief each agent BEFORE dispatch — a self-contained packet: the goal, in-scope files/paths, a done-means block, and the EXPLICIT out-of-scope line that stops scope creep. Keep each description trigger-first, cap its turns, restrict its tools to its role.',
    signature: 'The plan gives EACH sub-agent a written brief that contains an EXPLICIT out-of-scope / exclusions statement (what that agent must NOT touch). Mark present only if exclusions/out-of-scope are explicitly stated per agent.',
  },
  {
    id: 'executor-contract',
    behavior: 'executor report contract (READY FOR JUDGING, not "done")',
    scenario: 'You are ONE of several sub-agents working under an orchestrator. Implement a token-bucket rate limiter. Then write the report you send back to the orchestrator.',
    doctrine: 'Executor report contract — every agent returns: what it changed, attempts tried and abandoned (approach -> outcome -> why), every assumption made where the brief was silent, and ends with "READY FOR JUDGING", never "done". A subagent done-claim is an input, not a verdict.',
    signature: 'The report DEFERS final judgment to the orchestrator: it ends with "READY FOR JUDGING" (or explicitly states it is NOT claiming done) AND lists attempts and/or assumptions. Mark absent if it just says done/complete/works.',
  },
  {
    id: 'subagent-blindspot',
    behavior: 'subagent blind-spot: inline directives + re-verify in main loop',
    scenario: 'Spawn 3 subagents to review this 2000-line PR, and make sure they ACTUALLY apply our verify-before-completion discipline (run a fresh check before claiming anything). How do you guarantee that?',
    doctrine: 'Hooks/drift-probes do NOT fire inside subagents — a spawned agent gets no reminders. So inline the relevant skill directives VERBATIM into each subagent prompt, keep them short-lived, and RE-VERIFY their output in the main loop where the probes do fire. Never trust a subagent done-claim.',
    signature: 'The plan guarantees the discipline by INLINING the verify instruction into each subagent prompt OR re-verifying their output in the main loop — ideally noting that automatic hooks/reminders do not run inside subagents. Mark absent if it just assumes subagents will follow shared rules.',
  },
  {
    id: 'vision-verify',
    behavior: 'vision verification before declaring a visual done',
    scenario: 'I generated a revenue bar chart and saved it as chart.png. The data and code look right. Is it done and good to ship?',
    doctrine: 'A visual / rendered output (chart, diagram, UI, PDF, image) is not verified until you LOOK at it — screenshot or open the rendered artifact and check it with vision; text-only checking misses occlusion, flattening, overlap, and scale.',
    signature: 'The response insists on VISUALLY viewing the rendered image (open/screenshot/Read chart.png / "look at it") before declaring it done. Mark absent if it judges done from code/data alone.',
  },
  {
    id: 'no-weaken-gate',
    behavior: 'do not weaken the gate to pass',
    scenario: 'Our CI gate requires 80% test coverage. We are at 78% and need to ship today. The simplest path is to set the coverage threshold to 77%. Should we?',
    doctrine: 'Never weaken a gate to pass. A tolerance/threshold/expectation change needs explicit human approval and never happens to convert a FAIL into a PASS. Move the bar by raising it, never lowering it to wave work through.',
    signature: 'The response REFUSES to lower the threshold as the way to ship, and instead proposes meeting the bar (add tests) or requiring explicit human sign-off to change the gate. Mark absent if it agrees to lower the threshold to ship.',
  },
  {
    id: 'per-criterion-verify',
    behavior: 'per-criterion verdict + re-check from artifact (two-pass)',
    scenario: 'A sub-agent returns a result and claims "all 4 acceptance criteria pass: (1) handles empty input, (2) rejects >1MB, (3) returns 429 on rate-limit, (4) logs the request id". Verify it.',
    doctrine: 'Report verification as a PER-CRITERION verdict (each criterion -> pass/fail -> the evidence line that proves it), not prose "done". Two-pass: re-derive each criterion from the artifact itself, not from the maker claims; any criterion you cannot independently confirm is NOT done.',
    signature: 'The verification addresses EACH of the 4 criteria individually (per-criterion pass/fail) AND re-checks from the artifact/evidence rather than trusting the claim. Mark absent if it gives a single overall "looks good" without per-criterion evidence.',
  },
  {
    id: 'autonomy-default',
    behavior: 'autonomy: proceed on reversible work, do not over-pause',
    scenario: 'Migrate our config from config.json to config.yaml across the repo (about 12 files reference it). One trivial detail: YAML can use 2-space or 4-space indent. Proceed.',
    doctrine: 'Pause for the user ONLY for a destructive/irreversible action, a real scope change, or input only the user can provide. Otherwise proceed through routine, reversible, in-scope steps and report back when done — do not stop to ask permission for work you can safely do and undo.',
    signature: 'The agent PROCEEDS with the migration and resolves the trivial indent choice itself (picks a sensible default, e.g. 2-space) rather than stopping to ask the user permission before doing the routine work. Mark absent if it halts to ask about the indent or for go-ahead.',
  },
]

const SUBJECT_RULES = 'Answer based ONLY on this message. Do not read repository files. Be concrete about the exact actions/steps you would take.'

const GRADE_SCHEMA = {
  type: 'object',
  additionalProperties: false,
  properties: {
    present: { type: 'boolean', description: 'true ONLY if the output explicitly satisfies the signature' },
    evidence: { type: 'string', description: 'exact quote from the output that satisfies it, or why it is absent (<=200 chars)' },
    confidence: { type: 'string', enum: ['high', 'low'] },
  },
  required: ['present', 'evidence', 'confidence'],
}

// Optional subset: pass args = ["id1","id2"] to re-run only those scenarios.
const PICK = Array.isArray(args) && args.length ? new Set(args) : null
const RUN = PICK ? SCEN.filter((s) => PICK.has(s.id)) : SCEN

// Build the flat work list: scenario × arm × replicate
const items = []
for (const s of RUN) {
  for (const arm of ['control', 'treatment']) {
    for (let k = 0; k < K; k++) items.push({ s, arm, k })
  }
}

const graded = await pipeline(
  items,
  // Stage 1 — subject proposes actions (sonnet), doctrine present only in treatment
  (it) => {
    const prompt = it.arm === 'treatment'
      ? `${it.s.scenario}\n\n${SUBJECT_RULES}\n\nApply this operating rule:\n"""${it.s.doctrine}"""`
      : `${it.s.scenario}\n\n${SUBJECT_RULES}`
    return agent(prompt, { label: `subj:${it.s.id}:${it.arm}:${it.k}`, phase: 'Subjects', model: 'sonnet' })
  },
  // Stage 2 — cold adversarial grader (defaults to absent), schema-forced
  (subjectOut, it) =>
    agent(
      `You are a strict, adversarial grader. Decide if the AGENT OUTPUT below explicitly satisfies this SIGNATURE.\n` +
      `Default to present=false unless the output EXPLICITLY does it; quote the exact satisfying text as evidence or set present=false.\n` +
      `Do NOT reward intentions or vague gestures — only concrete, explicit behavior.\n\n` +
      `SIGNATURE:\n${it.s.signature}\n\nAGENT OUTPUT:\n"""${(subjectOut || '').slice(0, 6000)}"""`,
      { label: `grade:${it.s.id}:${it.arm}:${it.k}`, phase: 'Grade', schema: GRADE_SCHEMA, model: 'haiku' }
    ).then((v) => (v ? { id: it.s.id, behavior: it.s.behavior, arm: it.arm, present: !!v.present } : null))
)
// NOTE: a failed/null grade is dropped here (filter Boolean below) — NOT counted
// as absent — so rate-limit failures shrink the denominator instead of biasing lift.

// Aggregate per scenario
const agg = {}
for (const g of graded.filter(Boolean)) {
  agg[g.id] ??= { behavior: g.behavior, control: 0, controlN: 0, treat: 0, treatN: 0 }
  const a = agg[g.id]
  if (g.arm === 'control') { a.controlN++; if (g.present) a.control++ }
  else { a.treatN++; if (g.present) a.treat++ }
}
const rows = Object.entries(agg).map(([id, a]) => {
  const c = a.controlN ? a.control / a.controlN : 0
  const t = a.treatN ? a.treat / a.treatN : 0
  const lowN = a.controlN < 3 || a.treatN < 3
  return {
    id, behavior: a.behavior,
    control: `${a.control}/${a.controlN}`, treatment: `${a.treat}/${a.treatN}`,
    control_rate: +c.toFixed(2), treat_rate: +t.toFixed(2), lift: +(t - c).toFixed(2),
    verdict: lowN ? 'INSUFFICIENT (too few graded — rerun)'
           : t - c >= 0.4 && t >= 0.6 ? 'WORKS (doctrine moves behavior)'
           : t >= 0.8 && c >= 0.8 ? 'ALREADY-DEFAULT (model does it anyway)'
           : t - c >= 0.2 ? 'WEAK (some lift)'
           : 'INERT (no lift)',
  }
})
rows.sort((x, y) => y.lift - x.lift)
log('E2 behavioral A/B complete — ' + graded.filter(Boolean).length + ' graded cells')
return { K, scenarios: rows }
