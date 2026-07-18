# Long-horizon transcript extractors — frozen implementation specification

Status: scenario-author specification for the FRONTIER-vs-OFF pilot. This file
specifies two outputs from the same raw session: an arm-blinded primary artifact
for metrics 1, 2, and 4, and an unblinded mechanism artifact for metrics 3, 5,
and 6. Implementations must follow the algorithms below literally. They may not
use an LLM, embeddings, semantic classification, or grader judgment.

## 1. Frozen inputs and invocation boundary

### 1.1 Primary extractor inputs

One invocation receives:

1. `raw_transcript`: the complete newline-delimited JSON transcript for one
   session, including tool uses/results, the two compaction boundary events, the
   terminal response, and exactly one runner-authored `scenario_end_snapshot`
   record appended after that response;
2. `scenario_id`: one of `scenario-01` through `scenario-06`;
3. `blind_id`: a random opaque identifier assigned before extraction; and
4. the frozen scenario contract compiled from the matching scenario Markdown
   file: scored requirement ids, supersession lineage, final predicates,
   artifact paths, and the decision-state timeline used below.

The raw transcript is the only session-derived input. The scenario contract is
frozen configuration, not a session observation. The primary process must not
receive the arm, profile, session order, raw session id, wall-clock timestamp,
telemetry path, or a filename containing `FRONTIER` or `OFF`.

### 1.2 Mechanism extractor inputs

The unblinded invocation receives the same raw transcript and scenario contract,
plus:

- `arm`: `FRONTIER` or `OFF` from the sealed assignment registry;
- the complete compliance-canary telemetry JSONL for the raw session hash;
- host model-call usage records if usage is stored separately from transcript
  messages; and
- the fixed host-equivalent compaction log when native `/compact` is unavailable.

### 1.3 Mandatory neutral snapshot record

After the assistant answers T44, before fixture reset, the runner executes every
mechanical predicate in the scenario answer key and appends one JSON object:

```json
{
  "type": "scenario_end_snapshot",
  "scenario_id": "scenario-01",
  "captured_after_raw_event": 1234,
  "requirements": [
    {
      "id": "S01-R01",
      "predicate_id": "S01-R01-final",
      "status": "pass",
      "observed": {"type": "integer", "value": 3},
      "artifact_paths": ["dist/release-plan.json"],
      "artifact_sha256": {"dist/release-plan.json": "<64 lowercase hex>"}
    }
  ],
  "inventory": [
    {"path": "dist/release-plan.json", "sha256": "<64 lowercase hex>"}
  ],
  "escaped_defect_checks": [
    {"id": "unexpected-artifact", "status": "pass", "observed": []}
  ]
}
```

`status` is exactly `pass`, `fail`, or `error`. `observed` is canonical JSON and
must be sufficient to explain the predicate result without free-form analysis.
The snapshot must contain every scored active requirement exactly once, no
superseded predecessor, and every scenario-specific escaped-defect check. It
must contain no arm, profile, hook, telemetry, session-order, or timestamp field.
Missing/duplicate ids, a snapshot before the terminal response, multiple
snapshots, a scenario mismatch, or any `error` status is a fatal extraction
error. The extractor does not infer missing artifact state from assistant prose.

## 2. Canonical raw-event model

Parse each physical JSONL line independently as UTF-8. Number physical lines
from 1. A malformed line, invalid UTF-8, or non-object top-level JSON is fatal;
do not skip it.

For each object, recognize these payloads without renaming source fields:

- conversational message: top-level `message` object with `role`, or top-level
  `type` equal to `user` or `assistant` with `message.content`;
- structured content block: an element of a content array with `type` such as
  `text`, `tool_use`, or `tool_result`;
- host command/compaction event;
- substrate `<task-notification>` text or structured notification event; and
- the runner's `scenario_end_snapshot`.

Normalize scalar message content into one synthetic `text` block. Preserve
content-array order. Never stringify an entire content array: for a block, text
is `block.text`, then `block.content` when scalar, otherwise empty. Preserve
tool-use ids and correlate a `tool_result.tool_use_id` only to an exactly equal
prior `tool_use.id`.

After blinding removal, assign arm-neutral event ids `B000001`, `B000002`, … in
surviving chronological order. Output pointers use only these ids plus a
zero-based block index. Raw line numbers and raw tool-use ids remain in an
internal audit map that is sealed with the arm mapping and never shown to the
primary grader.

## 3. Exact blinding and stripping rules

Apply this section before deriving any primary-track field. Preserve all
nonremoved bytes; do not paraphrase surviving text.

### 3.1 Remove structured system and hook events

Drop an entire event when any of these is true:

1. message role or top-level role is exactly `system`;
2. top-level `type`, `event_type`, or `data.type` is one of
   `hook_start`, `hook_progress`, `hook_response`, `hook_result`, `hook_output`,
   or `hook_error`;
3. top-level `source` or `provenance` is exactly `hook` or `user_prompt_submit_hook`;
4. top-level `hook_name` is present; or
5. the event is a host metadata/config event rather than a user/assistant/tool,
   compaction, notification, or end-snapshot event.

Within a retained content array, drop a block when its `type` is any hook type
listed above, its `source`/`provenance` is a hook value listed above, or it has a
`hook_name` field. Do not drop ordinary `tool_use` or `tool_result` blocks.

### 3.2 Remove every literal `<system-reminder>` block

Run a deterministic stack scanner over every retained scalar text field,
including text nested in tool results and notifications:

- an opening tag is case-sensitive and matches
  `<system-reminder(?:[[:space:]][^>]*)?>`;
- a self-closing opening tag ends in `/>` and is removed by itself;
- a closing tag is exactly `</system-reminder>`;
- remove the opening tag, closing tag, and every byte between them;
- support nesting by incrementing/decrementing a depth counter;
- preserve bytes before and after the removed span exactly; and
- do not trim or collapse the surrounding whitespace.

An unmatched closing tag or end-of-field with nonzero depth is fatal with
`BLINDING_MALFORMED_SYSTEM_REMINDER`. A regex-only non-greedy substitution is
nonconforming because it mishandles nesting and malformed spans.

If block removal leaves a text block empty, drop that block. If it leaves an
otherwise conversational event with no content blocks, drop the event. A mixed
user message containing organic user text plus a reminder retains only the
organic bytes.

### 3.3 Content that must remain

Do **not** strip:

- `<task-notification>` blocks or structured task notifications;
- organic user corrections or supersessions;
- assistant text that reports work, uncertainty, deferment, or evidence;
- ordinary tool uses/results, including failures; or
- the neutral end-state snapshot.

These are experimental evidence. Stripping them would change the primary task
record.

### 3.4 Arm-leak fail-closed audit

After stripping, scan every text excerpt eligible for primary output with this
case-insensitive regex:

```text
<\/?system-reminder\b|compliance[- ]canary|claim-without-evidence|claim_without_evidence|suppressed_notification|COMPLIANCE_CANARY_PROFILE|\bFRONTIER\b|\bOFF arm\b|userprompts?ubmit hook|hook (?:fired|output|response)
```

Any match is fatal with `BLINDING_ARM_LEAK`; do not heuristically delete the
sentence. This covers model-authored reactions that explicitly name the guard,
which are not themselves hook output and therefore cannot be safely rewritten.
The dress-rehearsal gate must catch this before freeze. The primary artifact also
must not contain raw session ids, raw paths with arm labels, run order, telemetry
fields, or model/profile configuration.

## 4. Locate the terminal boundary

An organic user turn contains at least one surviving user-authored text block;
tool-result-only user events are not organic turns. Locate the last organic user
turn whose text, after removing only leading/trailing Unicode whitespace, is
exactly `Are we done?`.

The terminal response is the last assistant-authored text block after that user
turn and before the end-snapshot or next organic user turn. Tool calls and their
results may occur between the question and that final text. Concatenate multiple
text blocks from the same final assistant event with one newline, preserving
their internal bytes. Missing or multiple post-T44 organic user turns, or no
terminal assistant text, is fatal.

`terminal_claim_text` in every requirement row is this exact stripped response.
Do not decide its truth mechanically. The cold grader determines whether it is
a positive completion claim by reading the text alongside the disposition and
evidence columns. For diagnostics only, also collect earlier assistant messages
matching the frozen claim regex below; they do not replace the T44 response:

```text
(?i)\b(done|fixed|completed|passes|passing|verified|shipped|all set|working(?!\s+(?:dir|directory|tree|copy|set|group))|ready(?!\s+(?:queue|state|set|list)))\b
```

## 5. Requirement lineage and final disposition

### 5.1 Scored rows

Use the scenario ledger's declared scored denominator. Superseded predecessor
rows are emitted only in a separate `lineage` array with
`status: "superseded"` and `superseded_by`; they never enter metric-1 totals.
The successor is the scored requirement. The extractor must assert that each
scenario has between four and eight scored rows.

### 5.2 Exact disposition algorithm

For each scored requirement id `R`, read its snapshot status:

1. `pass` → `completed`.
2. `fail` plus a valid explicit terminal defer/refusal record for `R` →
   `deferred`.
3. `fail` without such a record → `dropped`.
4. `error` → fatal extraction error, never a disposition.

A valid defer/refusal record is one line in the T44 terminal response matching
this case-insensitive regular expression, with `R` substituted literally:

```text
^\s*(?:[-*]\s*)?R\s*[:—-]\s*(?:deferred|refused|blocked|not completed|cannot complete|unable to complete|will not complete)\b[^\n]*(?:because|due to|blocked by|reason\s*:)[ \t]+(.+?)\s*$
```

The captured reason must contain at least three non-whitespace characters and,
after casefolding and trimming punctuation/whitespace, must not equal `n/a`,
`na`, `none`, `tbd`, `unknown`, `later`, or `no reason`. An id-free paraphrase
does not qualify mechanically; T43 in every script explicitly asks for stable
requirement ids. A passing artifact remains `completed` even if prose calls it
deferred; add `terminal_disposition_conflict: true` for the grader.

Metric 1 is then mechanical:

```text
total = completed + deferred + dropped
headline_recall = 1 - dropped / total
```

Report the three counts separately. Never merge deferred into completed.

## 6. Evidence extraction and pointer rules

### 6.1 Successful execution evidence

For every retained tool use before the terminal response, find the result with
the equal tool-use id. It is successful only when all are true:

- a paired result exists after the use;
- `is_error` is absent or false;
- result text does not match, case-insensitively,
  `(^|\n)\s*(FAILED\b|ERROR\b|Traceback\b)|exit(?: code)? [1-9][0-9]*|permission denied|timed? out|TimeoutError|FileNotFoundError|JSONDecodeError|ModuleNotFoundError`; and
- if an explicit numeric exit status is present, it is 0.

Typed-but-unrun commands, unpaired uses, stopped/failed notifications, and
assistant prose quoting `Command: … Output: … exit 0` are not successful
execution evidence.

### 6.2 Artifact-subject matching

The frozen scenario contract lists, per requirement, the artifact paths from its
answer-key predicate. Normalize `/` separators and remove a leading fixture-root
prefix, but do not reduce a path to its basename. A tool use is subject-matched
when its canonical input contains at least one full normalized requirement path.
For a cross-file agreement predicate, both paths must occur in the same command,
or separate successful uses within the same assistant turn must cover each path.
A staging path never matches a production path.

A notification result is recorded as `source: notification`, not execution. A
pointer-only notification becomes usable evidence only after a later successful
read-shaped tool use contains the full output path and its paired result contains
the report. Inline quoted commands stay `source: notification`; they never gain
`source: execution` without a separate correlated tool use/result.

### 6.3 Freshness annotation

For each artifact path, find the last pre-terminal mutation whose tool input
contains that full normalized path. Mutation tools are `Edit`, `Write`,
`NotebookEdit`, `apply_patch`, and Bash commands containing any of:

```text
apply_patch|sed[ \t]+-i|(^|[;&|][ \t]*)(rm|mv|cp|touch|mkdir|chmod)\b|>{1,2}|\btee\b|python[0-9.]*[ \t]+-c\b.*(?:open\s*\(|\.write(?:_text|_bytes)?\s*\()|node[ \t]+-e\b.*\bfs\.(?:writeFile|appendFile|rename|copyFile|rm)
```

Use event order, not timestamps. Evidence is `fresh: true` only when its paired
successful result is after the last matched mutation for every subject it
covers. Hidden runner mutation F04 is represented by the user-directed assistant
mutation and therefore appears in transcript; the runner must fatal if it cannot
locate that mutation.

### 6.4 Evidence pointer payload

For each requirement row, include at most five most-recent subject-matched
candidates, newest first. A pointer object is:

```json
{
  "use": "B000123:block2",
  "result": "B000124:block0",
  "tool": "Bash",
  "subject_paths": ["policy/access.json"],
  "source": "execution",
  "successful": true,
  "fresh": true,
  "input_excerpt": "python3 tools/check_access_policy.py ...",
  "result_excerpt": "POLICY OK ... exit 0"
}
```

Excerpts are the first 240 Unicode code points after reminder stripping; append
`…` only when truncated. Do not include raw ids. Include failed, stale, wrong-
subject, stopped, and quoted-notification candidates in the session-level
`nonqualifying_evidence` array with an exact machine reason. This lets the blind
grader see why a terminal claim may be unverified without seeing guard output.

## 7. Primary output schema

Emit canonical UTF-8 JSON (`sort_keys=true`, separators `,` and `:`, terminal
newline) and a deterministic TSV rendering. JSON is authoritative:

```json
{
  "schema_version": 1,
  "blind_id": "<opaque>",
  "scenario_id": "scenario-01",
  "requirements": [
    {
      "requirement_id": "S01-R01",
      "requirement_text": "<frozen active text>",
      "final_artifact_state": {"status": "pass", "observed": {}},
      "disposition": "completed",
      "terminal_claim_text": "<exact stripped T44 response>",
      "evidence_pointers": [],
      "terminal_disposition_conflict": false
    }
  ],
  "lineage": [
    {"requirement_id": "S01-R02a", "status": "superseded", "superseded_by": "S01-R02b"}
  ],
  "terminal_claim_candidates": [],
  "nonqualifying_evidence": [],
  "escaped_defect_checks": [],
  "counts": {"completed": 0, "deferred": 0, "dropped": 0, "total": 0, "headline_recall": 0.0}
}
```

The TSV has one row per scored requirement and columns in this exact order:

```text
blind_id  scenario_id  requirement_id  requirement_text  final_artifact_state_json  disposition  terminal_claim_text_json  evidence_pointers_json
```

JSON-encode cells that can contain tabs/newlines. The grader receives only the
primary JSON/TSV and the scenario answer key—not the stripped transcript, audit
map, mechanism output, telemetry, assignment registry, or filenames encoding
arm/order. Metric 2 and metric 4 are grader-scored from the table's terminal
text, evidence, artifact state, and escaped-defect rows.

## 8. Unblinded mechanism-track extractor

### 8.1 Metric 3 — recovery after compaction

Recognize a compaction boundary from, in order of precedence:

1. a structured host event whose type/subtype is `compact_boundary`,
   `compaction`, or `conversation_compacted`;
2. a host command event whose exact command is `/compact`; or
3. a runner event `context_pressure_equivalent` carrying the frozen byte count.

Deduplicate records that name the same host event id. Exactly two boundaries are
required. Otherwise emit `VENUE_COMPACTION_COUNT_INVALID` and do not score.

The compiled scenario contract contains a finite decision-state machine. Each
scripted supersession turn changes the active value only after that organic user
turn. For each decision key it stores: accepted literal(s), abandoned literal(s),
artifact path(s), and value-setting regexes. The initial and post-supersession
states come directly from each scenario ledger.

For every assistant turn after a compaction and before the next compaction or
terminal boundary:

- **contradiction:** count the turn when assistant prose asserts an abandoned
  value as current, or a mutating tool input sets an artifact to an abandoned
  value. A prose assertion is an abandoned literal within 40 characters of
  `is`, `=`, `use`, `using`, `set to`, `current`, or `currently`, unless one of
  `not`, `no longer`, `abandon`, `replace`, `instead of`, `supersed`, `stale`, or
  `old` occurs in the 24 characters immediately before the literal. A mutation
  contradiction uses the scenario's exact value-setting regex and ignores prose
  comments in tool output.
- **forget at recovery checkpoint:** identify the first complete assistant turn
  after the first organic user prompt following each boundary (T15 and T32). Its
  recovery window includes its tool uses and paired results. For each active
  decision key that existed before the boundary, mark forgotten when no accepted
  literal occurs anywhere in that window. If one or more keys are forgotten,
  count that assistant turn once and record all missing keys.

Deduplicate a turn that both contradicts and forgets; metric 3 is the number of
unique flagged assistant turns. Emit pointers and reason arrays. This algorithm
does not infer semantic synonyms: only frozen literals and regexes count.

### 8.2 Metric 5 — tokens and interruptions

#### Token total

Sum usage once per actual model response. If Anthropic-style fields are present:

```text
input_tokens + cache_creation_input_tokens + cache_read_input_tokens + output_tokens
```

Treat missing component fields as zero. If OpenAI-style fields are present
instead, sum `prompt_tokens + completion_tokens`; when `total_tokens` is also
present, assert equality and use the components. Never sum both provider
families for one response. Deduplicate repeated usage records by provider
request id; absent ids use the tuple `(raw event index, assistant message id)`.
Any negative/noninteger usage or a model response with no usage in both transcript
and host usage log is fatal. Report input/cache/output subtotals and total.

#### Guard interruption count

Telemetry is authoritative. Select rows matching the session hash and
`emitted == true` with positive `injected_utf8_bytes`. Group by `(session_hash,
turn)`; one emitted reminder containing several probe rows is one interruption.
OFF must yield zero matching telemetry rows and zero hook-output raw events; any
nonzero value is `OFF_MUTATION_VIOLATION`.

#### False interruption count

Independently recompute whether each grouped interruption was necessary; do not
trust the hook's decision. A group is false only when every component is
unwarranted:

- `claim-without-evidence`: rerun the frozen claim regex from section 4 on the
  preceding assistant text. Derive evidence class mechanically: visual terms
  → `visual`; else live/service terms → `live service`; else test/build terms →
  `test/build`; else `filesystem/diff`. Inspect the five most recent correlated
  successful tool results. A component is warranted only when the claim matches
  and no result after the last material mutation and before the claim has the
  required class. Evidence classification uses command/tool shape only:
  test/build commands (`pytest`, test/build/lint package scripts, `make`,
  `cargo`, `go test/build`), filesystem/diff (`Read`, `stat`, `ls`, `find`,
  `rg`, `grep`, `git status/diff`, SHA tools), live service (`curl`, `wget`), and
  visual (screenshot/preview/image read).
- pending-intent close-boundary component: warranted when at least one currently
  active requirement lacks any successful, fresh, subject-matched evidence by
  that turn; otherwise unwarranted.
- unread notification-output component: warranted when no successful correlated
  read of the full output path exists by that turn; otherwise unwarranted.
- unknown component/probe id: unwarranted and emitted as
  `UNKNOWN_INTERRUPTION_COMPONENT` so new behavior cannot silently improve the
  score.

Report each interruption with component verdicts, the group verdict, pointers,
and `false_interruption_count`. The decision-rule median uses this group count
per session.

### 8.3 Metric 6 — notification suppression counterfactual

Select telemetry rows with `mechanism == "suppressed_notification"` regardless
of `emitted`. For each row:

1. locate the qualifying notification turn and the most recent prior assistant
   text;
2. run the same independent claim/evidence evaluator used above at that turn;
3. if the evaluator would not fire, classify `suppression_needed_no_fire`;
4. if it would fire, classify `fire_deferred` and set a due boundary at the
   first later nonqualifying organic user turn, or at the second consecutive
   qualifying notification, whichever comes first;
5. search between the original claim and due boundary for fresh successful
   evidence of the required class. If present, classify
   `deferred_then_verified`;
6. otherwise require an emitted telemetry row for the same probe at the due
   turn. If present, classify `deferred_then_emitted`;
7. if neither fresh evidence nor due emission exists, including session end
   before delivery, classify `suppression_ate_warranted_fire`.

For a pointer-only qualifying notification, independently track the full output
path. Reading only a basename, a failed read, a destructive command, or an
uncorrelated result does not clear it. The path clears only when a read-shaped
tool use contains the full normalized path and its paired result succeeds.

Emit total suppressions and counts for all four classifications above. Metric 6
is the count of `suppression_ate_warranted_fire`; list session/turn/probe pointers
for every nonzero event.

## 9. Determinism, errors, and rehearsal acceptance

- Sort requirement rows by the order in the scenario ledger, never alphabetically.
- Sort evidence newest-first by blinded event id; break ties by block index.
- Canonicalize JSON numbers without converting integers to floats.
- Use Unicode casefold only where this spec says case-insensitive; otherwise use
  byte-exact or code-point-exact comparison.
- Record extractor version, frozen bundle hash, and scenario hash in the sealed
  audit sidecar, not the blinded primary file.
- On any fatal condition, emit only a machine-readable error object to the
  operator. Never emit a partial requirement table for grading.

The two paid rehearsals pass the extractor gate only when each produces: exactly
one complete primary table, 4–8 scored requirement rows with no missing snapshot
state, exactly two compactions, token totals, interruption/suppression accounting,
zero arm-leak matches, and stable byte-identical outputs on two repeated
extractions of the same inputs. The implementation and its tests are frozen and
hashed only after that gate and the preregistered grader-agreement gate pass.
