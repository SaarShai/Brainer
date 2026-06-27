#!/usr/bin/env python3
"""loop-lint — static linter for an agentic loop spec.

LIMITS (a tripwire, not a sandbox — the framing both source harnesses use): the
gate/self-grading/subjectivity checks are heuristics over natural-language actor
and gate strings. They catch the common and adversarial-common phrasings (4
adversarial rounds hardened them), but cannot prove a loop correct — an exotic
NL phrasing of a self-grade or a subjective gate may still slip. The author owns
intent; this refuses the obvious failure modes cheaply and deterministically.


The article thesis: a loop is a GENERATOR wired to a VERIFIER, and the verifier
is the bottleneck. So a loop you cannot describe as {gate, stop, budget,
generator != verifier} is not a loop — it is an open-ended spin. This linter
refuses such specs BEFORE the loop runs, turning the doctrine into a mechanical
gate (per Brainer's "no prose rule where a mechanical gate can stand").

It validates a loop spec against three FAIL rules and ten WARN rules:

  R1 NO-GATE          (FAIL) — gate absent, or prose with no machine-checkable
                               pass/fail signal (allowlist: a command / test id /
                               path / assertion / exit-code / regex / schema ref).
  R2 NO-STOP-OR-BUDGET(FAIL) — stop condition missing, or budget cap missing /
                               unbounded (no numeric iteration|token|wallclock cap).
                               A cap of 0 (loop never runs) is a degenerate WARN.
  R3 SELF-GRADING     (FAIL) — generator == verifier (an agent grading its own
                               homework), or a closed loop with an empty verifier.
  R4 OPEN-NO-ACK      (WARN) — open topology without `accepted_open_loop: true`
                               (declare that "no feedback" is intentional).
  R5 FLEET-NO-QUORUM  (WARN) — fleet topology with no aggregation/quorum gate.
  R6 NO-TOPOLOGY      (WARN) — topology not declared (you did not choose a shape).
  R7 IRREVERSIBLE-NO-HUMAN (WARN) — autonomous loop that merges/deploys/migrates/
                               charges with no human approval gate (the security tax).
  R8 NO-MEMORY-CONTRACT (WARN) — scheduled/fleet/outer loop lacks anchor/read/write
                               state fields, so it will re-derive after context rot.
  R9 FLEET-STATE-NO-CONCURRENCY (WARN) — fleet has shared state with no explicit
                               single-writer / optimistic-revision / worktree strategy.
  R10 OUTPUT-SURFACE-UNBOUNDED (WARN) — an unattended (scheduled/event/outer/fleet/
                               long-running) loop takes a side-effecting world action
                               (post/comment/close/label/merge/email/commit/delete/…)
                               but declares no bounded `output_actions` allowlist —
                               default-deny + per-action caps, harness-enforced, not
                               a "please don't" in the prompt (cf. GitHub Agentic
                               Workflows `safe-outputs:`). An allowlist of `*`/`all`
                               is not an allowlist and still warns.
  R11 STUCK-NO-ADVISOR (WARN) — a loop that declares a `stuck` policy names no
                               `advisor` (the DIVERGENT, cross-vendor fresh-
                               perspective panel that feeds the generator on a
                               stall), or the advisor collapses into the verifier
                               (propose-and-judge is self-grading). Sourced from
                               skills/_shared/model_roster.py.
  R12 CROSS-VENDOR-EGRESS (WARN) — an advisor/verifier panel sends repo-derived
                               content to a third-party model but declares no
                               `redaction` surface (R12a), or an UNATTENDED loop
                               egresses with no `consent` gate (R12b). The enforced
                               scrub + consent live in model_roster.py; this makes
                               the data surface declarable + auditable in the spec.
                               (Borrowed from ksimback/looper's privacy layer.)
  R13 VERIFIER-BLINDNESS (WARN) — an LLM/agent verifier on a loop where blindness
                               matters (unattended, or a cross-vendor panel) does not
                               declare it is BLIND to the generator's reasoning
                               (`verifier_blind` / `verifier_inputs`, or a "fresh
                               context"/"blind" verifier string), or declares it is
                               NOT. A separate actor that reads the generator's self-
                               justification inherits the same bias. Closes the
                               declare-to-audit asymmetry (egress/concurrency/memory
                               all had a field; the deepest rule did not).

Use --strict-memory to promote R8/R9 findings to FAIL for loops where durable
state matters: scheduled, fleet, outer, or long-running loops.

Exit code IS the verdict: 0 clean · 1 any WARN · 2 any FAIL · 3 usage/unparseable.

House style mirrors skills/cache-lint/tools/cache_lint.py (stdlib only, typed
Finding/Report, --json). No PyYAML dependency: the spec is a flat `key: value`
block (fenced ```loop in markdown, a .yaml/.yml file, a .json file, or stdin).
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Literal

Severity = Literal["OK", "WARN", "FAIL"]

# Rules that are fatal (exit 2). Everything else is advisory (exit 1).
FAIL_RULES = {1, 2, 3}

# R12 CROSS-VENDOR EGRESS — a loop whose advisor/verifier panel sends repo-derived
# content to a THIRD-PARTY model (cross-vendor, model_roster, codex/gemini/glm/
# openrouter/fusion, or an "external"/"cross-vendor" panel). When that egress is
# present the spec must declare two controls, mirroring ksimback/looper's privacy
# layer: a `redaction` surface (R12a — what is scrubbed before it leaves) and, for
# UNATTENDED loops, a `consent` gate (R12b — egress is authorized, not a default).
# A tripwire over the actor strings; the enforced scrub + consent live in
# skills/_shared/model_roster.py (render_prompt redacts; --run needs consent).
_EGRESS = re.compile(
    r"\b(cross[\s-]?vendor|model[\s_-]?roster|openrouter|fusion|codex|gemini|"
    r"glm|z\.?ai|external\s+(?:model|panel|vendor|llm)|other\s+vendors?)\b", re.I)

# R13 VERIFIER-BLINDNESS — `verifier_inputs` content that means the verifier is
# fed the GENERATOR's self-justification (reasoning / chain-of-thought / rationale).
# A verifier that reads that chain inherits the same bias even though it is a
# separate actor — the doctrine's "blind verifier" rule (SKILL.md line 80). This
# detects a declared NON-blind input surface; absence is handled in the R13 check.
_NONBLIND_INPUT = re.compile(
    r"\b(reasoning|rationale|justification|chain[\s-]?of[\s-]?thought|\bcot\b|"
    r"scratchpad|thought\s+process|self[\s-]?critique|deliberation|"
    r"inner\s+monologue|self[\s-]?justification|the\s+why)\b", re.I)

# A verifier string that asserts input ISOLATION in prose ("fresh context", "blind",
# "sees only the outputs") already declares blindness — R13 is satisfied without a
# separate field, the same way R1 reads a machine gate out of the gate string and R5
# reads a quorum word out of the gate. NOT "read-only" — that bounds WRITE access,
# not what the verifier READS, so it does not establish blindness.
_BLIND_DECLARED = re.compile(
    r"\b(blind|fresh[\s-]?context|clean[\s-]?context|separate[\s-]?context|"
    r"isolated[\s-]?context|sees?\s+only\s+(?:the\s+)?(?:task|output|outputs|artifact)|"
    r"outputs?[\s-]only|without\s+(?:the\s+)?(?:generator'?s?\s+)?reasoning|"
    r"no\s+access\s+to\s+(?:the\s+)?(?:generator'?s?\s+)?reasoning)\b", re.I)

# A verifier STRING that ACTIVELY pulls in the generator's reasoning leaks it even
# if the same string also claims "fresh context", so it must NOT be read as blind
# (the _BLIND_DECLARED bypass round-2 surfaced). A leak = an inclusion verb
# (reads/with/plus/fed/…) followed within a short span by a reasoning token, with NO
# negator between them — so "sees only the outputs, not the reasoning" and "without
# the reasoning" stay blind (negation-safe, the FP a bare regex would introduce).
_REASONING_TOKEN = re.compile(
    r"\b(reasoning|rationale|chain[\s-]?of[\s-]?thought|\bcot\b|self[\s-]?justification|"
    r"scratchpad|thought\s+process|deliberation)\b", re.I)
_INCLUSION_VERB = re.compile(
    r"\b(read(?:s|ing)?|see(?:s|ing)?|with|plus|including|includes|incorporat\w+|"
    r"consum\w+|fed|feeding|given|giving|receiv\w+|gets?|getting|along\s+with)\b", re.I)
_NEGATOR = re.compile(r"\b(not|no|without|never|excluding|sans|minus|except)\b", re.I)


def _leaks_reasoning(verifier: str) -> bool:
    """True if the verifier string ACTIVELY includes the generator's reasoning — an
    inclusion verb then a reasoning token (≤30 chars apart) with no negator between.
    Negated forms ('…not the reasoning', 'without the reasoning') return False."""
    for m in _REASONING_TOKEN.finditer(verifier):
        verbs = list(_INCLUSION_VERB.finditer(verifier[:m.start()]))
        if not verbs:
            continue
        span = verifier[verbs[-1].end():m.start()]
        if len(span) <= 30 and not _NEGATOR.search(span):
            return True
    return False


@dataclass
class Finding:
    rule: int
    severity: Severity
    title: str
    file: str = ""
    line: int = 0
    detail: str = ""


@dataclass
class Spec:
    """One parsed loop spec: flat fields + the source line of each field."""
    name: str = ""
    fields: dict[str, str] = field(default_factory=dict)
    field_lines: dict[str, int] = field(default_factory=dict)
    start_line: int = 0
    source: str = ""

    def get(self, key: str) -> str:
        return self.fields.get(key, "").strip()

    def line_of(self, key: str) -> int:
        return self.field_lines.get(key, self.start_line)


@dataclass
class Report:
    root: str
    n_specs: int = 0
    findings: list[Finding] = field(default_factory=list)
    summary: dict[str, int] = field(default_factory=dict)

    def add(self, f: Finding) -> None:
        self.findings.append(f)

    def finalize(self) -> None:
        self.summary = {
            "WARN": sum(1 for f in self.findings if f.severity == "WARN"),
            "FAIL": sum(1 for f in self.findings if f.severity == "FAIL"),
        }


# --- Spec parsing ---------------------------------------------------------

# Keys the spec understands. Unknown keys are kept (harmless) but never required.
KNOWN_KEYS = {
    "name", "topology", "generator", "verifier", "gate", "stop", "budget",
    "accepted_open_loop", "quorum", "aggregate", "anchor_files", "state_store",
    "recall", "writeback", "state_concurrency", "stuck", "advisor",
    "redaction", "consent", "egress", "verifier_inputs", "verifier_blind",
}

_KV_RE = re.compile(r"^\s*([A-Za-z_][A-Za-z0-9_-]*)\s*:\s*(.*)$")


def _strip_quotes(v: str) -> str:
    v = v.strip()
    if len(v) >= 2 and v[0] == v[-1] and v[0] in "\"'":
        return v[1:-1]
    return v


def _parse_flat(lines: list[str], base_line: int) -> Spec:
    """Parse a flat `key: value` block into a Spec. `base_line` is the 1-based
    file line number of lines[0], so field_lines point back into the source."""
    spec = Spec(start_line=base_line)
    for i, raw in enumerate(lines):
        line = raw.rstrip("\n")
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        m = _KV_RE.match(line)
        if not m:
            continue
        key = m.group(1).strip().lower()
        val = _strip_quotes(m.group(2))
        spec.fields[key] = val
        spec.field_lines[key] = base_line + i
        if key == "name":
            spec.name = val
    return spec


def _specs_from_json(text: str, source: str) -> list[Spec]:
    data = json.loads(text)
    items = data if isinstance(data, list) else [data]
    out: list[Spec] = []
    for item in items:
        if not isinstance(item, dict):
            raise ValueError("loop spec JSON must be an object or a list of objects")
        spec = Spec(start_line=1, source=source)
        for k, v in item.items():
            kk = str(k).strip().lower()
            spec.fields[kk] = "" if v is None else str(v)
            spec.field_lines[kk] = 1
        spec.name = spec.get("name")
        out.append(spec)
    return out


_FENCE_OPEN_RE = re.compile(r"^[ \t]*```+\s*loop\b", re.I)
_FENCE_CLOSE_RE = re.compile(r"^[ \t]*```+\s*$")


def _specs_from_markdown(text: str, source: str) -> list[Spec]:
    """Extract every fenced ```loop … ``` block as one spec each."""
    lines = text.splitlines()
    out: list[Spec] = []
    i = 0
    while i < len(lines):
        if _FENCE_OPEN_RE.match(lines[i]):
            block: list[str] = []
            start = i + 2  # 1-based line of the first content line
            j = i + 1
            while j < len(lines) and not _FENCE_CLOSE_RE.match(lines[j]):
                block.append(lines[j])
                j += 1
            spec = _parse_flat(block, base_line=start)
            spec.source = source
            out.append(spec)
            i = j + 1
        else:
            i += 1
    return out


def _looks_like_flat_spec(text: str) -> bool:
    keys = set()
    for line in text.splitlines():
        m = _KV_RE.match(line)
        if m:
            keys.add(m.group(1).lower())
    return bool(keys & {"gate", "generator", "verifier", "topology", "stop", "budget"})


def parse_specs(text: str, source: str) -> list[Spec]:
    """Discover loop specs from raw text. Order of preference:
    .json → JSON; fenced ```loop blocks → one spec each; otherwise, if the text
    looks like a flat spec (has spec keys at column 0), treat the whole thing as
    one spec (covers .yaml/.yml and a bare stdin spec)."""
    low = source.lower()
    if low.endswith(".json"):
        specs = _specs_from_json(text, source)
    elif low.endswith((".md", ".markdown")) or _FENCE_OPEN_RE.search(text) or "```loop" in text.lower():
        specs = _specs_from_markdown(text, source)
        # A markdown file with no fenced loop block but flat keys at top level
        # is still lintable (e.g. someone wrote the spec without fencing it).
        if not specs and _looks_like_flat_spec(text):
            specs = [_parse_flat(text.splitlines(), base_line=1)]
            specs[0].source = source
    elif _looks_like_flat_spec(text):
        spec = _parse_flat(text.splitlines(), base_line=1)
        spec.source = source
        specs = [spec]
    else:
        specs = []
    for s in specs:
        s.source = source
    return specs


# --- Rule heuristics ------------------------------------------------------

# R1 allowlist: a gate PASSES only if it names a CHECKABLE signal — a command, a
# test id, a command-anchored code file, an assertion against a CODE-LIKE operand,
# an exit code, or an explicit marker. ALLOWLIST, not a prose denylist: "the
# reviewer agrees" and "tone == the CEO's voice" name no real check and FAIL.
# A bare '==' between two prose words, or a '.py' name-dropped mid-sentence, must
# NOT launder a subjective gate (the false-negatives the PROMPTER live-test found).
_CODELIKE = (r"(?:\d+(?:\.\d+)?|true|false|none|null|nil|pass|fail|0x[0-9a-f]+|\$\w+|"
             r"\"[^\"]*\"|'[^']*'|[A-Za-z_][\w-]*_[\w.-]+|[A-Za-z_]\w*\.[A-Za-z_]\w*)")
# STRONG signals: an unambiguous machine check (path, ./, assertion, exit code,
# shell shape, explicit marker). These pass R1 even alongside prose.
_STRONG_GATE = [
    re.compile(r"\b(make|bash|sh|zsh|python3?|node|ruby|perl)\s+\S", re.I),
    # a COMMAND-ANCHORED code/data file: after ./, an absolute path, or a separator
    # — NOT a bare 'config.py' dropped mid-prose (that used to launder a vacuous gate).
    re.compile(r"(?:^|[\s;|&])\.?/[\w./-]+\.(py|sh|js|ts|tsx|mjs|cjs|json|ya?ml|toml|rs|go|rb)\b", re.I),
    re.compile(r"(?:^|\s)\./\S+"),                       # ./run-checks
    # an assertion against a CODE-LIKE operand (NOT a bare '==' between prose words)
    re.compile(rf"(?:{_CODELIKE}\s*(?:==|!=|>=|<=)|(?:==|!=|>=|<=)\s*{_CODELIKE})", re.I),
    re.compile(r"\$\?|\$\(|::"),
    re.compile(r"\bassert\b|\bexit\s*code\b|\bexit\s+\d", re.I),
    # diff/grep is a real check only with a real operand — a flag (-c) or a token
    # carrying a '/' or '.' (a path/file). "diff between the draft and the brief"
    # name-drops the word 'diff' and must NOT pass.
    re.compile(r"\b(diff|grep)\b[^\n]*?(?:\s-\w|[\w-]*[./][\w./-]+)", re.I),
    re.compile(r"\b(regex|schema|cmd|command)\s*[:=]", re.I),
]
# RUNNER words + WEAK tokens: a real signal in a command, but decorative inside a
# subjective sentence ("the cypress vines look healthy", "returns 1 thumbs-up").
# They gate ONLY when the surrounding prose is not subjective (see _has_machine_gate).
_RUNNER_WORD = [
    re.compile(r"\b(pytest|unittest|jest|vitest|mocha|tox|nox|ruff|eslint|mypy|tsc|"
               r"npm|pnpm|yarn|cargo|gradle|gradlew|mvn|dotnet|deno|bats|rspec|phpunit|"
               r"newman|playwright|cypress|k6|behave|rake|ginkgo|hurl|jasmine|ava|junit)\b", re.I),
    re.compile(r"\b(go|cargo)\s+test\b", re.I),
]
_WEAK_MACHINE_GATE = [
    re.compile(r"\b(returns?|status)\s+\d", re.I),
]
# Subjective-prose markers — when present, a runner/weak token is just decoration,
# so the gate is the human's taste, not a machine signal.
_SUBJECTIVE = re.compile(
    r"\b(reads?|looks?|feels?|sounds?|seems?)\s+"
    r"(well|right|good|great|correct|clean|complete|done|finished|nice|fine|healthy|polished|"
    r"compelling|elegant\w*|beautiful\w*|smooth\w*|crisp\w*|slick|solid|strong)\b"
    r"|\b(good\s+enough|high\s+enough|out\s+of\s+\d+|thumbs?[\s-]?up|happy|satisfi\w+|polished|"
    r"compelling|on[\s-]brand|the\s+vibe|vibes?|quality|acceptable|smell\s+test|slaps|"
    r"chef'?s?[\s-]?kiss|elegantly|beautifully|nicely|cleanly)\b", re.I)

# A human DECISION is also a concrete gate — the article endorses "a handoff to a
# human with the run data attached" and both source harnesses escalate to a human
# (autonomy-loop's FOR-REVIEW.md, HarnessCode's PAUSE_FOR_HUMAN). BUT an AUTONOMOUS
# agent "approving" its own output by feel is NOT a gate — that is the LLM-judge
# hole R1 exists to refuse — so the approver must be a human/owner/named person,
# never an agent/model. Decision verbs go beyond approve (select/pick/decide/…).
_AGENT_TOKEN = re.compile(r"\b(agents?|subagents?|models?|llms?|ai|bots?|automation|pipeline|"
                          r"\bci\b|claude|gpt|opus|sonnet|haiku|gemini|llama|mistral)\b", re.I)
_HUMAN_TOKEN = re.compile(r"\b(humans?|owner|operator|person|people|user|users|"
                          r"me|you|your|team|manager|lead|maintainer|admin|stakeholder|"
                          r"exec\w*|ceo|cto|founder|saar)\b", re.I)
_DECISION_VERB = re.compile(r"\b(approv\w+|sign[\s-]?off|signs?\s+off|signed\s+off|escalat\w+|"
                            r"decid\w+|decision|select\w+|pick\w+|choos\w+|chose|confirm\w+|"
                            r"accept\w+|reject\w+|green[\s-]?light|approval)\b", re.I)

_UNBOUNDED = re.compile(r"\b(unbounded|infinite|none|no\s*limit|unlimited|never|forever)\b", re.I)
_QUORUM = re.compile(r"\b(quorum|aggregat\w*|merge|reviewer|vote|consensus|majority|reduce)\b", re.I)
_SCHEDULED = re.compile(
    r"\b(cron|schedule[sd]?|scheduled|nightly|daily|weekly|hourly|timer|"
    r"webhook|event\s+loop|file\s+watcher|watch(?:es|er)?|inbox|"
    r"monitoring\s+(?:job|automation|agent|loop))\b", re.I)
_LONG_RUNNING = re.compile(
    r"\b(long[-\s]?running|daemon|persistent|continuously|continuous|always[-\s]?on|"
    r"background\s+(?:job|worker|loop|agent)|service\s+loop|until\s+(?:interrupted|cancelled|stopped))\b",
    re.I,
)
_MEMORY_CONTRACT_FIELDS = ("anchor_files", "state_store", "recall", "writeback")
_STATE_CONCURRENCY_ALLOWED = {"single_writer", "optimistic_revision", "worktree_isolated"}

# A real budget cap is a NUMBER bound to a cap unit (iterations / tokens / a
# duration) — not a stray digit in a prose sentence ("run until inbox has 0 unread").
_BUDGET_CAP = re.compile(
    r"\b(?:max[_\s-]?)?(?:iterations?|iters?|tokens?|turns?|rounds?|attempts?|steps?|calls?|"
    r"loops?|passes|retries|tries|revisions?|revs?)\b\s*[:=]?\s*\d+(?:\.\d+)?"                 # unit then number
    r"|\d+(?:\.\d+)?\s*(?:k\s*)?(?:iterations?|iters?|tokens?|turns?|rounds?|attempts?|steps?|"
    r"calls?|loops?|passes|retries|tries|revisions?|revs?)\b"                                 # number then unit
    r"|\d+(?:\.\d+)?\s*(?:s|sec|secs|seconds?|m|min|mins|minutes?|h|hr|hrs|hours?)\b",  # a duration
    re.I)

# A DISTRIBUTIVE cap ("50 iterations per page", "500 tokens at a time", "5 retries
# per file") bounds a SUB-unit, not loop length — total work is unbounded when the
# outer set is unbounded. It is a real cap only if a separate TOTAL/overall cap is
# also named.
_DISTRIBUTIVE = re.compile(
    r"\bper\s+(?:page|file|item|record|row|request|req|doc|document|task|chunk|entry|"
    r"user|message|email|ticket|line|call|batch|record|page)s?\b"
    r"|\bper-\w+|\bat a time\b|\b(?:each|apiece)\b", re.I)
_TOTAL = re.compile(r"\b(total|overall|across|aggregate|combined|cumulative|in all)\b", re.I)

# Self-grading: generator and verifier are the SAME actor. Three signals, in
# precision order: (a) identical actor strings (_norm); (b) the same MODEL SLUG
# on both sides — and a DIFFERENT slug (opus vs sonnet) is strong evidence of two
# actors that OVERRIDES any word collision; (c) a shared proper name that ACTS —
# a Capitalized non-common token immediately followed by a role-verb ("Alfred
# drafts" / "Alfred reviews"). A capitalized QUALIFIER before a noun ("Payments
# service", "Senior Marketing") or a shared domain word ("Keep/Update/Replace")
# is NOT an actor name, so distinct teams/roles that share vocabulary stay distinct.
# Keep in sync with the vendor lanes in skills/_shared/model_roster.py (LANE_*:
# gpt/claude/gemini/glm/local) + their model families — a panel sourced from the
# roster can name any of them, and R3 must catch the same vendor on both sides.
# `glm` and `codex` were missing, so GLM/Codex self-grades slipped R3 while
# opus/gpt/gemini were caught; test_loop_lint guards this set against roster drift.
_MODEL_SLUGS = frozenset("""opus sonnet haiku claude gpt codex fable gemini gemma llama mistral mixtral
qwen deepseek grok glm o1 o3 o4 mimo ollama""".split())
# Generic / role / common-domain words that, even when Capitalized in a role
# phrase, are NOT a person's name — so they must not trigger a self-grading match.
_GENERIC_ACTORS = frozenset("""human agent agents model models llm ai bot worker person people someone
role roles subagent subagents pass passes""".split())
_COMMON_ROLE_NOUNS = frozenset("""brief briefing plan planning report reporting draft drafting review
reviewing check checking spec specs doc docs documentation writer reader checker reviewer planner
coder builder tester auditor judge critic generator verifier worker pass loop gate output result
results pipeline stage phase step final main sub task tasks code test tests sprint feature prompt
prompts data file files the a an it""".split())
# Role-verbs: a proper name is an ACTOR when it is the subject of one of these
# ("Alfred drafts"). Distinguishes a name from a Capitalized qualifier ("Payments
# service"). Includes possession/authority verbs (owns/maintains/signs/leads) —
# "Alfred owns the draft" / "Alfred signs the review" is still self-grading.
_NAME_VERBS = frozenset("""drafts draft writes write produces produce generates generate authors author
creates create makes make codes code builds build implements implement proposes propose composes compose
designs design plans plan reviews review checks check verifies verify validates validate audits audit
tests test grades grade judges judge evaluates evaluate inspects inspect approves approve assesses assess
critiques critique refutes refute reads read reconciles reconcile recomputes recompute applies apply
runs run ships ship owns own maintains maintain signs sign leads lead handles handle manages manage
oversees oversee curates curate delivers deliver edits edit fixes fix merges merge""".split())
# Generic AUTONOMOUS-actor head nouns. When the SAME such noun heads an identical
# subject phrase on both sides ("the writer agent" / "the same writer agent …",
# "our model produces" / "our model checks") with NO distinguishing model-slug or
# proper name and NO human in the loop, the two roles are one autonomous actor —
# self-grading (the natural-language false negative the audit surfaced). Human
# tokens are deliberately ABSENT: "a human writes" / "a human checks" is the
# endorsed human-review gate, never self-grading (R1/R7), and is exempted below.
_FLAGGABLE_GENERIC = frozenset("""agent agents subagent subagents model models llm llms ai bot bots
automation pipeline writer drafter author coder builder generator producer reviewer checker verifier
validator auditor judge critic grader evaluator tester worker assistant it they""".split())
# Subject-phrase determiners/ordinals dropped before comparing the two subjects,
# so "the same writer agent" and "the writer agent" compare equal.
_SUBJ_DROP = frozenset("""the a an our its their your my his her this that these those said same other
another single one first second third next previous own""".split())
# A preposition (like a role-verb) ends the SUBJECT phrase, so a trailing
# qualifier ("… on a second pass", "… in staging") is not read as the head noun.
_SUBJ_PREP = frozenset("on in at of for to via with by from through over after before during per across "
                       "into onto under within against around about".split())


def _norm(s: str) -> str:
    """Normalize an actor string for exact self-grading comparison."""
    s = _strip_quotes(s).casefold().strip()
    s = re.sub(r"\s+", " ", s)
    s = s.strip(".,;:!?-_ ")
    return s


def _slugs(s: str) -> frozenset[str]:
    """Model identifiers named in an actor phrase, returned as WHOLE tokens that
    contain a known model slug. We split on -/_ only to TEST membership, so a
    hyphenated id ('claude-opus', 'gpt-4o') is recognized and a laundered
    self-grade can't slip R3 on spelling alone — but the whole token is what's
    returned, so distinct tiers stay distinct: 'claude-opus' vs 'claude-sonnet'
    do NOT collide on the shared 'claude' family word (they are two actors)."""
    out = set()
    for tok in re.findall(r"[A-Za-z][A-Za-z0-9_-]*", s):
        if any(p.lower() in _MODEL_SLUGS for p in re.split(r"[-_]", tok)):
            out.add(tok.lower())
    return frozenset(out)


# What may follow an ACTING proper name: a clause boundary (comma, paren,
# conjunction, possessive, semicolon, end). NOT '/' — "Keep/Update/Replace" is a
# domain enum, not "Name / next". A name followed by a plain noun ("Payments
# service") is a qualifier, not an actor.
_NAME_BOUNDARY = re.compile(r"\s*(?:[,(;:]|and\b|or\b|'s\b|$)", re.I)

# A Capitalized token that is the OBJECT of a transport/infra preposition
# ("claude on Bedrock", "opus via Acme", "gpt through Portkey") names the
# infrastructure the actor runs on, NOT the actor. It must not be read as a
# shared proper name, or two DISTINCT models on the same platform collide on the
# platform word and trip R3 (the false positive GLM-5.2's review surfaced).
_INFRA_PREP = re.compile(
    r"(?:^|\b)(on|via|through|thru|using|with|over|atop|behind|across|"
    r"by\s+way\s+of|hosted\s+on|served\s+by|routed\s+through)\s*$", re.I)


def _subject_names(s: str) -> frozenset[str]:
    """Proper names that ACT — a Capitalized, non-common token that is the subject
    of a role-verb ("Alfred drafts", "Alfred owns") OR stands at a clause boundary
    ("Alfred, our lead, …" / "Alfred and a peer …" / "Alfred (opus) …"). A
    capitalized qualifier before a noun ("Payments service", "Senior Marketing")
    is NOT an actor name, so distinct teams/roles sharing vocabulary stay distinct."""
    names = set()
    for m in re.finditer(r"\b([A-Z][A-Za-z0-9'-]+)\b", s):
        low = m.group(1).lower()
        if len(low) < 2 or low in _MODEL_SLUGS or low in _GENERIC_ACTORS or low in _COMMON_ROLE_NOUNS:
            continue
        if m.start() > 0 and s[m.start() - 1] == "/":
            continue                              # part of a slash enum (Keep/Update/Replace), not a name
        if _INFRA_PREP.search(s[:m.start()]):
            continue                              # object of "on/via/through" — infra, not an actor
        rest = s[m.end():]
        if _NAME_BOUNDARY.match(rest):            # name then a clause boundary
            names.add(low)
            continue
        nxt = re.match(r"\s+([A-Za-z][\w'-]*)", rest)   # name then a role-verb
        if nxt and nxt.group(1).lower() in _NAME_VERBS:
            names.add(low)
    return frozenset(names)


def _same_actor(generator: str, verifier: str) -> bool:
    """True if generator and verifier are the same actor. A shared acting proper
    name ("Alfred (opus)" / "Alfred (sonnet)") is checked FIRST — a human in both
    roles is self-grading regardless of model. Then a shared model slug. Different
    slugs alone, with no shared name, are two distinct actors."""
    if _subject_names(generator) & _subject_names(verifier):
        return True                               # same human/agent name acts on both sides
    return bool(_slugs(generator) & _slugs(verifier))   # same model named on both sides


def _subject_words(s: str) -> list[str]:
    """The actor's SUBJECT phrase as lowercased content words: everything up to
    the first role-verb or preposition, with determiners/ordinals dropped. So
    "the same writer agent on a second pass" → ['writer', 'agent'] and
    "our model produces the draft" → ['model']."""
    toks = re.findall(r"[A-Za-z][A-Za-z0-9'-]*", _strip_quotes(s))
    subj: list[str] = []
    for t in toks:
        tl = t.lower()
        if tl in _NAME_VERBS or tl in _SUBJ_PREP:
            break                                 # subject ends at the first verb/preposition
        subj.append(tl)
    if not subj:
        subj = [t.lower() for t in toks]          # no verb/prep: the whole phrase is the subject
    return [t for t in subj if t not in _SUBJ_DROP]


def _generic_self_grade(generator: str, verifier: str) -> bool:
    """True when both actors are the SAME generic autonomous actor described
    without a distinguishing model-slug or proper name — the natural-language
    self-grade ("the writer agent"/"the same writer agent", "our model
    produces"/"our model checks") that exact-string and slug/name matching miss.
    Guards keep it precise: a distinct slug (opus vs sonnet) or proper name means
    two actors; a human in either role is the endorsed review gate, not self-
    grading; and the full subject phrase must match (so "planning agent" vs
    "execution agent" — same head, different work — stays distinct)."""
    if _slugs(generator) or _slugs(verifier):
        return False                              # a named model distinguishes the actors
    if _subject_names(generator) or _subject_names(verifier):
        return False                              # a proper name is handled by _same_actor
    if _HUMAN_TOKEN.search(generator) or _HUMAN_TOKEN.search(verifier):
        return False                              # human-in-the-loop is a valid separate gate
    wg, wv = _subject_words(generator), _subject_words(verifier)
    if not wg or wg != wv:
        return False                              # different subject phrase ⇒ different actor.
        # ORDERED equality, not set: "model agent" vs "agent model" share a word set
        # but name different head roles — a set match there is a false positive
        # (the reorder hole the white-box audit surfaced).
    return wg[-1] in _FLAGGABLE_GENERIC           # head is an autonomous-actor noun


def _has_machine_gate(gate: str) -> bool:
    if any(rx.search(gate) for rx in _STRONG_GATE):
        return True                       # unambiguous command/assertion wins over prose
    if _SUBJECTIVE.search(gate):
        return False                      # subjective prose: a runner/weak token is decoration
    return any(rx.search(gate) for rx in _RUNNER_WORD) \
        or any(rx.search(gate) for rx in _WEAK_MACHINE_GATE)


def _has_human_gate(gate: str) -> bool:
    # An AUTONOMOUS agent "approving" is not a human gate (the LLM-judge hole).
    if _AGENT_TOKEN.search(gate):
        return False
    return bool(_DECISION_VERB.search(gate) and _HUMAN_TOKEN.search(gate))


# A gate can be COMMAND-SHAPED (passes the _STRONG_GATE allowlist) yet never return
# non-zero — so it always "passes" and gates nothing. Two classes the shape check
# waves through: (a) a help/version/usage flag as the whole check ('./tool --help' —
# exits 0 by definition); (b) a bare printer/lister with no assertion ('cat f',
# 'echo ok', 'ls dir'). Fire ONLY when NO real assertion exists anywhere in the gate
# (no &&/||, no pipe, no test/grep -q/exit-code/comparison) — so 'cmd | grep -q OK'
# or '... && test -f out' (real checks) are NOT flagged.
# (Upstreamed from the product-images sibling fork; pairs with R1's shape allowlist.)
_NOOP_FLAG = re.compile(r"(?:^|[\s=])(?:--help|-h|--usage|--version|-V)\b", re.I)
_NOOP_ONLY_CMD = re.compile(r"^\s*(?:true|:|echo|printf|cat|ls|pwd)\b", re.I)
_REAL_CHECK = re.compile(
    r"&&|\|\||(?:^|\s)\|(?:\s|$)|\bgrep\b[^\n]*\s-\w*q|\btest\b|\[\s|\[\[|"
    r"\bexit\s+\d|\bassert\b|==|!=|>=|<=|-eq|-ne|-gt|-lt|\$\?", re.I)
# An unfilled <placeholder> sitting in the gate's PASS/FAIL LOGIC (a ternary
# condition or an assertion operand) means the CHECK ITSELF is unspecified — the
# agent could fill it with a tautology ('True'). DATA placeholders that only say
# WHAT to operate on ('--name-contains "<part>"') are fine and not flagged.
_LOGIC_PLACEHOLDER = re.compile(
    r"<[^>]*(?:assert|condition|cond|predicate|expr|metric|check|bool)[^>]*>"
    r"|\bif\s+<[^>]+>\s+else\b"
    r"|(?:==|!=|>=|<=)\s*<[^>]+>|<[^>]+>\s*(?:==|!=|>=|<=)", re.I)


def _is_noop_gate(gate: str) -> bool:
    """True if the gate is command-shaped but can't fail (a help/version flag or a
    bare printer/lister with no real assertion anywhere)."""
    if _REAL_CHECK.search(gate):
        return False
    return bool(_NOOP_FLAG.search(gate) or _NOOP_ONLY_CMD.match(gate))


def _has_logic_placeholder(gate: str) -> bool:
    """True if an unfilled <...> placeholder sits in the gate's pass/fail logic
    (the check is unspecified), vs a data arg (which is fine)."""
    return bool(_LOGIC_PLACEHOLDER.search(gate))


def _budget_cap_value(budget: str) -> float | None:
    """The numeric cap if the budget names a real cap bound to a unit, else None
    (unbounded / a stray digit in prose / a distributive sub-cap over an unbounded
    set with no separate total)."""
    if not budget or _UNBOUNDED.search(budget):
        return None
    if _DISTRIBUTIVE.search(budget) and not _TOTAL.search(budget):
        return None                       # caps a sub-unit, not loop length
    m = _BUDGET_CAP.search(budget)
    if not m:
        return None
    digits = re.search(r"\d+(?:\.\d+)?", m.group(0))
    return float(digits.group()) if digits else None


def _budget_is_capped(budget: str) -> bool:
    return _budget_cap_value(budget) is not None


def _topology_tokens(topology: str) -> set[str]:
    return {t for t in re.split(r"[^a-z]+", topology.lower()) if t}


def _is_true(v: str) -> bool:
    return _strip_quotes(v).strip().lower() in {"true", "yes", "1", "on"}


def _state_concurrency_ok(v: str) -> bool:
    """True when `state_concurrency` names one of the documented strategies."""
    norm = re.sub(r"[\s-]+", "_", _strip_quotes(v).strip().lower())
    return norm in _STATE_CONCURRENCY_ALLOWED


# An IRREVERSIBLE action — something an autonomous loop should not do without a
# human in the loop (the article's "human review before anything irreversible" +
# the security tax). A verb allowlist (it is a tripwire, not a proof — a novel
# synonym will slip; the high-blast-radius ones are covered after 1 adversarial
# round). Verbs/phrases, not bare nouns.
_IRREVERSIBLE = re.compile(
    r"\b(deploys?|deploying|deployment|promotes?\s+to\s+prod\w*|releases?\s+to\s+prod\w*|"
    r"publishe?s?|npm\s+publish|tags?\s+(?:a\s+|the\s+)?(?:release|version)|cuts?\s+(?:a\s+|the\s+)?release|"
    r"merges?\s+to\s+(?:main|master|prod\w*)|force[\s-]?merges?|pushe?s?\s+to\s+(?:main|master|prod\w*)|"
    r"force[\s-]?pushe?s?|deletes?\s+(?:the\s+)?(?:remote\s+)?branch|"
    r"migrat\w+|(?:drops?|truncates?)\s+(?:the\s+)?(?:table|database|db)\b|rm\s+-rf|"
    r"overwrites?\s+(?:the\s+)?prod\w*|prod\w*\s+data\b|"
    r"charges?\s+(?:the\s+)?(?:card|customer)|refunds?|payouts?|"
    r"wires?\s+(?:the\s+)?(?:money|funds|payment)|transfers?\s+(?:the\s+)?(?:money|funds)|"
    r"initiat\w+\s+(?:a\s+)?(?:wire|transfer|payout)|sends?\s+(?:the\s+)?(?:money|funds|payment)|"
    r"revokes?\s+(?:the\s+)?(?:api\s+)?(?:key|token|credential|cert\w*|access)|"
    r"rotates?\s+(?:secret|credential|key)s?|"
    r"sends?\s+(?:the\s+)?(?:email|mail)[\s-]?blast|email[\s-]?blast|"
    r"ships?\s+to\s+prod\w*)\b", re.I)
# Reversibility context — if a matched verb is qualified by one of these WITHIN ~16
# chars, it is a dry-run/preview/test/config-edit OF the action, not the action.
# Only UNAMBIGUOUS qualifiers: bare "tests"/"lint"/"validate" are excluded because
# "lints and deploys to prod" genuinely deploys (that would be a false negative).
_REVERSIBLE_CTX = re.compile(
    r"\b(dry[\s-]?run|preview|staging|sandbox|ephemeral|simulat\w*|unit\s+tests?)\b"
    r"|--dry-run|\.ya?ml\b|\.json\b|\.toml\b", re.I)


def _irreversible_action(text: str) -> "re.Match | None":
    """The first genuine irreversible action in `text`, or None. Skips a verb that
    sits in a path (/deploy/) or is qualified by a reversibility marker."""
    for m in _IRREVERSIBLE.finditer(text):
        if m.start() > 0 and text[m.start() - 1] == "/":
            continue
        if _REVERSIBLE_CTX.search(text[max(0, m.start() - 16): m.end() + 16]):
            continue
        return m
    return None


# Optional determiner + up to two adjective words between an active verb and its
# object noun, so "closes the duplicate issue" / "adds a wontfix label" match while
# "closed issues" (no active verb) does not. Active-verb gating, not this gap, is
# what kills the read-only false positives.
_DET = r"(?:(?:the|a|an|this|that|its|their|your)\s+)?(?:\w+\s+){0,2}"

# A SIDE-EFFECTING world action — something an UNATTENDED loop mutates outside
# itself: a comment, an issue/PR state, a label, a merge/commit/push, an email/
# message, a published/deployed/charged side effect. Broader than _IRREVERSIBLE
# (which is only the catastrophic subset): R10 catches the mundane-but-unbounded
# case (a moderation bot that closes/labels/comments with no cap). A tripwire,
# not a proof — object-anchored so generic verbs (edit/update/write) inside a
# generator description don't trip it; a novel surface will slip until adversarially
# extended. cf. GitHub Agentic Workflows `safe-outputs:` (allowed actions + caps).
# Active-verb forms only (3rd-person `-s` / gerund `-ing`). Bare and past-participle
# forms are deliberately EXCLUDED because they collide with read-only noun/adjective
# phrases that describe state rather than an action — "the commit hash", "0 open
# issues", "count merged PRs", "deleted files" must NOT trip an output-surface warning.
_SIDE_EFFECTING = re.compile(
    r"\b("
    r"posts?\s+" + _DET + r"comments?|posting\s+" + _DET + r"comments?|comments?\s+on\b|"
    r"repl(?:ies|ying)\s+to\b|"
    r"clos(?:es|ing)\s+" + _DET + r"(?:issue|pr|pull[\s-]?request|ticket)|"
    r"reopen(?:s|ing)\b|"
    r"add(?:s|ing)?\s+" + _DET + r"labels?|labell?(?:s|ing)\s+" + _DET + r"(?:issue|pr|pull[\s-]?request)|"
    r"merg(?:es|ing)\s+" + _DET + r"(?:pr|pull[\s-]?request|branch)|"
    r"commits\b|committing\b|"
    r"push(?:es|ing)\s+(?:to\b|a\s|the\s)|"
    r"open(?:s|ing)\s+" + _DET + r"(?:pr|pull[\s-]?request|issue)|"
    r"creat(?:es|ing)\s+" + _DET + r"(?:issue|pr|pull[\s-]?request|ticket|branch|file|record)|"
    r"delet(?:es|ing)\s+" + _DET + r"(?:issue|comment|file|branch|record|row)|"
    r"sends?\s+(?:\w+\s+){0,3}(?:email|message|dm|slack|notification|reply)|"
    r"sending\s+(?:\w+\s+){0,3}(?:email|message|dm|notification)|"
    r"emails?\s+(?:the\s+)?(?:team|user|owner|list|subscribers?|customers?)|"
    r"publish(?:es|ing)\b|deploys\b|deploying\b|deploy\s+to\b|"
    r"charg(?:es|ing)\s+(?:the\s+)?(?:card|customer)|refund(?:s|ing)\b"
    r")\b", re.I)
# An `output_actions` value that permits everything is not an allowlist.
_UNBOUNDED_ALLOWLIST = re.compile(r"(\*|\ball\b|\banything\b|\beverything\b|\bunrestricted\b|\bunbounded\b)", re.I)


def _side_effecting_action(text: str) -> "re.Match | None":
    """The first side-effecting world action in `text`, or None. Same path /
    reversibility skips as _irreversible_action (a dry-run/preview is not an act)."""
    for m in _SIDE_EFFECTING.finditer(text):
        if m.start() > 0 and text[m.start() - 1] == "/":
            continue
        if _REVERSIBLE_CTX.search(text[max(0, m.start() - 16): m.end() + 16]):
            continue
        return m
    return None


# --- Checks ---------------------------------------------------------------

def check_spec(report: Report, spec: Spec, rule_filter: int | None, *, strict_memory: bool = False) -> None:
    src = spec.source
    label = spec.name or f"(unnamed @ line {spec.start_line})"

    def want(n: int) -> bool:
        return rule_filter in (None, n)

    gate = spec.get("gate")
    stop = spec.get("stop")
    budget = spec.get("budget")
    generator = spec.get("generator")
    verifier = spec.get("verifier")
    topology = spec.get("topology")
    toks = _topology_tokens(topology)
    is_open = "open" in toks
    is_fleet = "fleet" in toks
    is_outer = "outer" in toks
    is_closed = "closed" in toks or (not is_open and bool(toks))
    all_fields = " ".join(spec.fields.values())
    is_scheduled = bool(_SCHEDULED.search(all_fields))
    is_long_running = bool(_LONG_RUNNING.search(all_fields))
    needs_memory_contract = is_outer or is_fleet or is_scheduled or is_long_running
    memory_severity: Severity = "FAIL" if strict_memory else "WARN"

    # R1 NO-GATE
    if want(1):
        if not gate:
            report.add(Finding(1, "FAIL", f"spec '{label}' has no `gate`",
                               src, spec.line_of("gate") or spec.start_line,
                               "A loop with no pass/fail gate is theatre. Give a machine-checkable "
                               "gate (a command / test id / assertion). cf. verify-before-completion."))
        elif not _has_machine_gate(gate) and not _has_human_gate(gate):
            report.add(Finding(1, "FAIL", f"spec '{label}' gate is prose, not a checkable signal",
                               src, spec.line_of("gate"),
                               f"gate={gate!r}: no command / test id / assertion / exit-code / path, and no "
                               "explicit human approval (approve / sign-off / escalate). 'looks correct' / "
                               "'the reviewer agrees' do not gate a loop — name the check or the approver."))
        elif _is_noop_gate(gate):
            report.add(Finding(1, "FAIL", f"spec '{label}' gate is a no-op that can't fail",
                               src, spec.line_of("gate"),
                               f"gate={gate!r}: a --help/--version flag or a bare printer always exits 0 — it can "
                               "never block the loop. Name a check that returns non-zero on the bad case "
                               "(an assertion, grep -q, test, a non-zero exit)."))
        elif _has_logic_placeholder(gate):
            report.add(Finding(1, "WARN", f"spec '{label}' gate has an unfilled placeholder in its pass/fail logic",
                               src, spec.line_of("gate"),
                               f"gate={gate!r}: a <placeholder> in the assertion/condition leaves the check itself "
                               "unspecified — it could be filled with a tautology (`True`). Substitute the concrete "
                               "assertion before running; data placeholders (paths/names) are fine."))

    # R2 NO-STOP-OR-BUDGET
    if want(2):
        if not stop:
            report.add(Finding(2, "FAIL", f"spec '{label}' has no `stop` condition",
                               src, spec.line_of("stop") or spec.start_line,
                               "Declare the completion condition the loop runs until."))
        cap = _budget_cap_value(budget)
        if cap is None:
            report.add(Finding(2, "FAIL", f"spec '{label}' has no numeric `budget` cap",
                               src, spec.line_of("budget") or spec.start_line,
                               f"budget={budget!r}: an unbounded loop is a spin. Give a numeric cap "
                               "(max_iterations / max_tokens / max_wallclock)."))
        elif cap == 0:
            report.add(Finding(2, "WARN", f"spec '{label}' budget cap is 0 — the loop never runs",
                               src, spec.line_of("budget") or spec.start_line,
                               f"budget={budget!r}: a cap of 0 means the loop body executes zero times. "
                               "Set a positive iteration / token / wall-clock cap."))

    # R3 SELF-GRADING
    if want(3):
        if generator and verifier and (_norm(generator) == _norm(verifier)
                                        or _same_actor(generator, verifier)
                                        or _generic_self_grade(generator, verifier)):
            report.add(Finding(3, "FAIL", f"spec '{label}' generator and verifier are the same actor (self-grading)",
                               src, spec.line_of("verifier"),
                               f"generator={generator!r}, verifier={verifier!r} resolve to the same actor. An "
                               "agent grading its own homework grades generously — the verifier must be a "
                               "separate actor (a different model/agent, ideally a fresh context or worktree)."))
        elif is_closed and not verifier:
            report.add(Finding(3, "FAIL", f"spec '{label}' is a closed loop with no `verifier`",
                               src, spec.line_of("verifier") or spec.start_line,
                               "A closed loop ships on its gate; name the SEPARATE actor that runs it."))

    # R4 OPEN-NO-ACK
    if want(4) and is_open and not _is_true(spec.get("accepted_open_loop")):
        report.add(Finding(4, "WARN", f"spec '{label}' is open-loop without `accepted_open_loop: true`",
                           src, spec.line_of("topology"),
                           "Open loops drift and burn budget on loose criteria. If 'no feedback gate' "
                           "is intentional, set accepted_open_loop: true to declare it."))

    # R5 FLEET-NO-QUORUM
    if want(5) and is_fleet:
        has_quorum = bool(spec.get("quorum") or spec.get("aggregate")) or \
            _QUORUM.search(" ".join([gate, verifier, stop]))
        if not has_quorum:
            report.add(Finding(5, "WARN", f"spec '{label}' is a fleet with no aggregation/quorum gate",
                               src, spec.line_of("topology"),
                               "Parallel results must converge through a quorum/aggregate/reviewer gate "
                               "before they bubble up — otherwise the fleet has no verified result."))

    # R6 NO-TOPOLOGY
    if want(6) and not topology:
        report.add(Finding(6, "WARN", f"spec '{label}' does not declare a `topology`",
                           src, spec.start_line,
                           "Choose the shape: open|closed · inner|outer · single|fleet. "
                           "Not choosing is the over-orchestration default."))

    # R7 IRREVERSIBLE-NO-HUMAN — an autonomous loop that merges/deploys/migrates/
    # charges with no human in the loop (the security tax: an unattended loop is an
    # unattended attack surface). A human gate or a human verifier silences it.
    if want(7):
        # scan each action field SEPARATELY (not the name, and not joined — joining
        # lets a gate's "pytest tests/" bleed into the stop's window and wrongly
        # suppress). A label like "deploy-config-linter" takes no action.
        m = next((mm for mm in (_irreversible_action(f) for f in (stop, gate, generator)) if mm), None)
        if m and not _has_human_gate(gate) and not _HUMAN_TOKEN.search(verifier):
            report.add(Finding(7, "WARN", f"spec '{label}' takes an irreversible action with no human gate",
                               src, spec.line_of("gate") or spec.start_line,
                               f"the loop names an irreversible action ({m.group(0)!r}) but no human approves "
                               "before it runs. Require a human sign-off (a human verifier, or an approve/"
                               "sign-off gate) before merge / deploy / migrate / charge; scope its permissions."))

    # R8 NO-MEMORY-CONTRACT — context rot starts to matter for loops that are
    # outer, scheduled/event-triggered, long-running, or parallel. Do not fail
    # simple inner fix loops by default; --strict-memory turns durable-state gaps
    # into a hard gate where pass state must survive the context window.
    if want(8) and needs_memory_contract:
        missing = [k for k in _MEMORY_CONTRACT_FIELDS if not spec.get(k)]
        if missing:
            report.add(Finding(8, memory_severity, f"spec '{label}' lacks a loop memory contract",
                               src, spec.line_of("topology") or spec.start_line,
                               "scheduled/fleet/outer/long-running loops need recall-before-pass and "
                               "write-after-pass. "
                               f"Missing: {', '.join(missing)}. Add anchor_files, state_store, recall, "
                               "and writeback so each pass resumes from durable state instead of memory."))

    # R9 FLEET-STATE-NO-CONCURRENCY — when a fleet writes shared pass state, name
    # the merge strategy. Advisory by default because some fleets isolate state
    # outside the spec; --strict-memory makes missing strategy a hard gate.
    if want(9) and is_fleet and spec.get("state_store"):
        sc = spec.get("state_concurrency")
        if not sc or not _state_concurrency_ok(sc):
            detail = ("missing state_concurrency" if not sc
                      else f"state_concurrency={sc!r} is not one of "
                           "single_writer / optimistic_revision / worktree_isolated")
            report.add(Finding(9, memory_severity, f"spec '{label}' has fleet state with no concurrency strategy",
                               src, spec.line_of("state_concurrency") or spec.line_of("state_store"),
                               f"{detail}. Shared state needs a single writer, optimistic revision checks, "
                               "or worktree-isolated state before aggregation."))

    # R10 OUTPUT-SURFACE-UNBOUNDED — an UNATTENDED loop (scheduled/event/outer/
    # fleet/long-running) that mutates the outside world must declare a bounded
    # output surface: an `output_actions` allowlist (what it MAY do) with per-action
    # caps, enforced by the harness (default-deny), NOT asked for in the prompt.
    # Inverts R7's catastrophic blocklist to catch the mundane-but-unbounded case
    # (a bot that can close/label/comment at scale). Scoped to needs_memory_contract
    # so a watched inner fix loop stays lightweight — the human IS its output gate.
    # Ported from GitHub Agentic Workflows `safe-outputs:` (allowed actions + max).
    if want(10) and needs_memory_contract:
        m = next((mm for mm in (_side_effecting_action(f) for f in (generator, stop, gate)) if mm), None)
        if m:
            oa = spec.get("output_actions")
            if not oa:
                report.add(Finding(10, "WARN", f"spec '{label}' has an unbounded output surface",
                                   src, spec.line_of("generator") or spec.start_line,
                                   f"an unattended loop takes a side-effecting action ({m.group(0)!r}) but "
                                   "declares no `output_actions` allowlist. Enumerate the actions it MAY take, "
                                   "each with a per-action cap (default-deny, harness-enforced), so a drifted "
                                   "run can't act at scale — a prompt-level 'don't' is not a control."))
            elif _UNBOUNDED_ALLOWLIST.search(oa):
                report.add(Finding(10, "WARN", f"spec '{label}' output_actions allowlist is unbounded",
                                   src, spec.line_of("output_actions") or spec.start_line,
                                   f"output_actions={oa!r}: an allowlist of '*'/'all' permits any action and is "
                                   "not a control. Name the specific actions allowed, each with a cap."))

    # R11 STUCK-NO-ADVISOR — a loop that declares a `stuck` policy should source
    # its next-hypothesis from an `advisor`: a DIVERGENT, preferably cross-vendor
    # panel (skills/_shared/model_roster.py) that proposes structurally-different
    # approaches, rather than the already-stuck agent retrying harder against its
    # own blind spot. And the advisor must stay SEPARATE from the verifier — the
    # advisor proposes (feeds the generator), the verifier judges (IS the gate);
    # one actor doing both judges a fix it suggested, which is self-grading by
    # another door. Opt-in (fires only once `stuck` is declared) so plain inner
    # fix loops stay lightweight, exactly like R8/R9/R10.
    if want(11):
        stuck = spec.get("stuck")
        advisor = spec.get("advisor")
        if stuck and not advisor:
            report.add(Finding(11, "WARN", f"spec '{label}' declares a stuck policy but names no `advisor`",
                               src, spec.line_of("stuck") or spec.start_line,
                               "on stuck, a fresh perspective beats retrying harder. Name an `advisor` panel "
                               "(cross-vendor, read-only) from skills/_shared/model_roster.py to propose "
                               "structurally-different approaches — the divergent counterpart to the verifier. "
                               "Advisors propose new approaches/tools/methods; they never gate."))
        if advisor and verifier and (_norm(advisor) == _norm(verifier) or _same_actor(advisor, verifier)):
            report.add(Finding(11, "WARN", f"spec '{label}' advisor and verifier are the same actor",
                               src, spec.line_of("advisor"),
                               f"advisor={advisor!r}, verifier={verifier!r} resolve to the same actor. The advisor "
                               "is DIVERGENT (proposes approaches, feeds the generator); the verifier is CONVERGENT "
                               "(judges pass/fail, IS the gate). One actor doing both judges a fix it proposed — "
                               "keep them separate vendors/agents (model_roster excludes the orchestrator's lane)."))

    # R12 CROSS-VENDOR EGRESS — if the advisor/verifier panel sends repo content to a
    # third-party model, demand the two privacy controls. R12a (redaction) always;
    # R12b (consent) only for unattended loops, where no human is present to approve
    # the first egress. Fires only when an egress signal is actually present, so a
    # same-host / local-only loop is never nagged.
    if want(12):
        egress_fields = [spec.get("advisor"), verifier, spec.get("egress")]
        if any(f and _EGRESS.search(f) for f in egress_fields):
            if not spec.get("redaction"):
                report.add(Finding(12, "WARN", f"spec '{label}' egresses cross-vendor with no `redaction` declared",
                                   src, spec.line_of("advisor") or spec.line_of("verifier") or spec.start_line,
                                   "the advisor/verifier panel sends repo-derived content to a third-party model "
                                   "but the spec declares no `redaction` surface. Name what is scrubbed before egress "
                                   "(secrets / .env / keys / PII); the enforced scrub is in skills/_shared/"
                                   "model_roster.py (render_prompt), but declare it so the data surface is auditable."))
            if needs_memory_contract and not spec.get("consent"):
                report.add(Finding(12, "WARN", f"spec '{label}' is an unattended loop that egresses with no `consent` gate",
                                   src, spec.line_of("consent") or spec.start_line,
                                   "an unattended loop crosses vendor boundaries with no human present to approve the "
                                   "first egress. Declare a `consent` gate (model_roster --run requires "
                                   "--consent / MODEL_ROSTER_EGRESS_CONSENT=1) so cross-vendor send is authorized, "
                                   "not a silent default."))

    # R13 VERIFIER-BLINDNESS — a SEPARATE verifier is necessary but not sufficient:
    # it must also be BLIND to the generator's reasoning/self-justification, or it
    # inherits the same bias (SKILL.md line 80). This is the skill's deepest rule
    # and — until now — the only major doctrine with no declarable spec field, while
    # egress/concurrency/memory all have one. R13 closes that declare-to-audit
    # asymmetry. Static lint cannot PROVE information isolation, so (like R12's
    # redaction) it makes the surface DECLARABLE: an LLM/agent verifier on a loop
    # where blindness matters (unattended, or a cross-vendor panel) must say what it
    # sees. A machine-gate verifier (pytest) is blind by construction and never trips
    # it; a self-grading verifier is R3's job, not R13's. Opt-in scope mirrors R8/
    # R10/R12 so plain inner fix loops are never nagged.
    if want(13) and generator and verifier and _AGENT_TOKEN.search(verifier) \
            and not _has_machine_gate(verifier):   # a "pytest agent" verifier is the machine gate — blind by construction
        same_actor = (_norm(generator) == _norm(verifier)
                      or _same_actor(generator, verifier)
                      or _generic_self_grade(generator, verifier))
        blindness_matters = needs_memory_contract or bool(_EGRESS.search(verifier))
        if not same_actor and blindness_matters:
            vblind = spec.get("verifier_blind")
            vinputs = spec.get("verifier_inputs")
            declares_nonblind = (bool(vblind) and not _is_true(vblind)) \
                or (bool(vinputs) and bool(_NONBLIND_INPUT.search(vinputs))) \
                or _leaks_reasoning(verifier)   # verifier string itself pulls in the reasoning
            declares_blind = (bool(vblind) and _is_true(vblind)) \
                or (bool(vinputs) and not _NONBLIND_INPUT.search(vinputs)) \
                or bool(_BLIND_DECLARED.search(verifier))
            if declares_nonblind:
                report.add(Finding(13, "WARN", f"spec '{label}' verifier is NOT blind to the generator's reasoning",
                                   src, spec.line_of("verifier_blind") or spec.line_of("verifier_inputs"),
                                   "the verifier reads the generator's reasoning/self-justification and inherits the "
                                   "same bias. A separate actor is necessary but not sufficient — the verifier must "
                                   "see only the task + the outputs (SKILL.md: design the verifier). Set "
                                   "verifier_blind: true and restrict verifier_inputs to task, outputs."))
            elif not declares_blind:
                report.add(Finding(13, "WARN", f"spec '{label}' does not declare verifier blindness",
                                   src, spec.line_of("verifier") or spec.start_line,
                                   "an LLM verifier on an unattended/cross-vendor loop must be BLIND to the "
                                   "generator's reasoning, or it inherits the same bias even as a separate actor. "
                                   "Declare the surface so it is auditable: verifier_blind: true, or "
                                   "verifier_inputs: task, outputs — the declare-to-audit field egress/"
                                   "concurrency/memory already have. (A 'fresh context' / 'blind' verifier "
                                   "satisfies this in prose.)"))


def lint(text: str, source: str, rule_filter: int | None = None, *, strict_memory: bool = False) -> Report:
    report = Report(root=source)
    specs = parse_specs(text, source)
    report.n_specs = len(specs)
    if not specs:
        report.add(Finding(0, "WARN", "no loop spec found",
                           source, 0,
                           "Expected a fenced ```loop block, a .yaml/.json spec, or flat `key: value` "
                           "lines (gate/stop/budget/generator/verifier/topology)."))
        report.finalize()
        return report
    for spec in specs:
        check_spec(report, spec, rule_filter, strict_memory=strict_memory)
    report.finalize()
    return report


# --- Diagram (Mermaid) ----------------------------------------------------
# Render a spec as a generator→gate→verifier loop, GROUNDED BY CONSTRUCTION:
# every node/edge is derived from the parsed Spec (never invented), and the
# lint findings are overlaid so a missing gate / self-grading / unbounded loop
# is *visible*, not buried in a text report. Output is Mermaid text — the
# renderer (GitHub, Obsidian, VS Code, mermaid.js) owns the look; we emit only
# the structure. Zero dependencies; pure string building.

# Mermaid breaks on these inside a node label; strip rather than escape (a
# label is a glance, not a transcript). Quotes/brackets/pipes/backticks are the
# syntactically dangerous set.
_MM_BAD = re.compile(r"[\"\[\]{}()|<>`]")


def _mm_label(text: str, maxlen: int = 44) -> str:
    s = re.sub(r"\s+", " ", (text or "").strip())
    s = _MM_BAD.sub("", s)
    if len(s) > maxlen:
        s = s[: maxlen - 1] + "…"
    return s or "(none)"


def to_mermaid(spec: Spec, findings: list[Finding]) -> str:
    """A Mermaid flowchart of one loop spec with its lint findings overlaid.
    `findings` must be THIS spec's findings (run check_spec into a fresh
    Report per spec) so the node styling matches."""
    g = _mm_label(spec.get("generator"))
    gate = _mm_label(spec.get("gate"))
    v = _mm_label(spec.get("verifier"))
    stop = _mm_label(spec.get("stop"))
    budget = _mm_label(spec.get("budget"))
    topo = _mm_label(spec.get("topology"), 40)
    name = _mm_label(spec.name or spec.source or "loop", 60)
    advisor = spec.get("advisor")

    out: list[str] = []
    out.append(f"%% loop-lint diagram — {name}")
    out.append("flowchart LR")
    out.append(f'  TOPO["topology: {topo}"]')
    out.append(f'  G["gen: {g}"]')
    out.append(f'  K{{"gate: {gate}"}}')
    out.append(f'  V["verify: {v}"]')
    out.append(f'  S(["stop: {stop}"])')
    out.append(f'  B[/"budget: {budget}"/]')
    out.append("  TOPO -.-> G")
    out.append("  G --> K")
    out.append("  K -->|pass| V")
    out.append("  K -->|fail| G")
    out.append("  V -->|accept| S")
    out.append("  V -->|reject| G")
    out.append("  B -.caps.-> G")
    # The advisor is a DIVERGENT side-input: on stuck it feeds fresh approaches
    # back into the generator — it is never on the gate/verify path.
    if advisor:
        out.append(f'  ADV[["advisor: {_mm_label(advisor)}"]]')
        out.append("  G -.stuck.-> ADV")
        out.append("  ADV -.fresh approach.-> G")

    if findings:
        out.append("  subgraph lint[lint findings]")
        for i, f in enumerate(findings):
            cls = "fail" if f.severity == "FAIL" else "warn"
            out.append(f'    F{i}["R{f.rule} {f.severity}: {_mm_label(f.title, 52)}"]:::{cls}')
        out.append("  end")
    else:
        out.append('  OK0["OK — gate · stop · budget · separate verifier"]:::ok')

    # Inline emphasis: colour each structural node by the WORST severity of any
    # finding that indicts it, so the node colour matches the lint severity (an
    # R2 cap==0 WARN must paint amber, not FAIL-red). Per-NODE, not per-rule, so
    # a node hit by two rules of different severity can't get two conflicting
    # `class` lines (FAIL dominates WARN).
    # R11 paints the generator: a stuck loop with no advisor leaves the generator
    # re-deriving alone (G always exists; the ADV node may not, so don't key on it).
    rule_nodes = {1: ("K",), 2: ("S", "B"), 3: ("G", "V"), 5: ("V",),
                  6: ("TOPO",), 8: ("TOPO",), 9: ("V",), 11: ("G",), 12: ("V",)}
    node_sev: dict[str, str] = {}
    for f in findings:
        for n in rule_nodes.get(f.rule, ()):
            if node_sev.get(n) != "FAIL":
                node_sev[n] = f.severity
    fails = sorted(n for n, s in node_sev.items() if s == "FAIL")
    warns = sorted(n for n, s in node_sev.items() if s == "WARN")
    if fails:
        out.append(f"  class {','.join(fails)} fail")
    if warns:
        out.append(f"  class {','.join(warns)} warn")
    out.append("  classDef fail stroke:#c0392b,stroke-width:2px,color:#c0392b;")
    out.append("  classDef warn stroke:#b9770e,stroke-width:2px,color:#b9770e;")
    out.append("  classDef ok stroke:#1e8449,stroke-width:1px,color:#1e8449;")
    return "\n".join(out)


# --- Resolved snapshot ----------------------------------------------------
# An IMMUTABLE AUDIT SNAPSHOT of a spec — not a resume checkpoint. Borrowed from
# ksimback/looper's loop.resolved.json, deliberately narrowed: looper compiles a
# runnable artifact; we only freeze the spec + its lint verdict so a long-lived
# (outer/fleet/scheduled) loop has a replay/drift surface ("rerun the exact spec we
# verified last Tuesday"). It does NOT make loop_lint an orchestrator: there is no
# runner, and the file carries no run state. The boundary is enforced by what we
# emit — fields + verdict, never a resume cursor.

def _is_unattended(spec: Spec) -> bool:
    toks = _topology_tokens(spec.get("topology"))
    all_fields = " ".join(spec.fields.values())
    return ("fleet" in toks or "outer" in toks
            or bool(_SCHEDULED.search(all_fields)) or bool(_LONG_RUNNING.search(all_fields)))


def resolve_snapshot(spec: Spec, *, strict_memory: bool = False) -> dict:
    """Freeze one spec into an immutable audit snapshot: normalized fields + the
    lint verdict at freeze time. No timestamp (Date.now is unavailable in this
    runtime and would also break reproducibility — stamp it outside if needed)."""
    per = Report(root=spec.source)
    check_spec(per, spec, None, strict_memory=strict_memory)
    per.finalize()
    verdict = "fail" if per.summary["FAIL"] else ("warn" if per.summary["WARN"] else "clean")
    return {
        "kind": "loop.resolved",
        "note": "immutable audit snapshot of the spec + lint verdict at freeze time. "
                "NOT a resume checkpoint: it carries no run state and no runner.",
        "name": spec.name,
        "source": spec.source,
        "unattended": _is_unattended(spec),
        "fields": dict(sorted(spec.fields.items())),
        "lint": {
            "verdict": verdict,
            "summary": per.summary,
            "findings": [asdict(f) for f in per.findings],
        },
    }


def diagrams(text: str, source: str, rule_filter: int | None = None, *, strict_memory: bool = False) -> list[str]:
    """One Mermaid diagram per spec in `text`, each with its own findings
    overlaid. Raises ValueError/JSONDecodeError on an unparseable spec (same as
    lint)."""
    specs = parse_specs(text, source)
    out: list[str] = []
    for spec in specs:
        per = Report(root=source)
        check_spec(per, spec, rule_filter, strict_memory=strict_memory)
        per.finalize()
        out.append(to_mermaid(spec, per.findings))
    return out


# --- Driver ---------------------------------------------------------------

def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="loop-lint",
                                 description="Static linter for an agentic loop spec.")
    ap.add_argument("path", help="loop-spec file (.md with a ```loop block / .yaml / .json), or '-' for stdin")
    ap.add_argument("--json", action="store_true", help="emit the typed report as JSON")
    ap.add_argument("--diagram", action="store_true",
                    help="emit a Mermaid diagram of each spec with lint findings overlaid "
                         "(grounded in the parsed spec; wrap in a ```mermaid fence to render)")
    ap.add_argument("--rule", type=int, choices=[1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13],
                    help="restrict to one rule")
    ap.add_argument("--strict-memory", action="store_true",
                    help="promote R8/R9 loop-memory findings to FAIL for scheduled/fleet/outer/long-running loops")
    ap.add_argument("--resolve", action="store_true",
                    help="emit an immutable audit snapshot (loop.resolved JSON) of each spec + its lint verdict — "
                         "a replay/drift surface for outer/fleet/scheduled loops, NOT a resume checkpoint. "
                         "Exit code stays the lint verdict so it composes in CI.")
    args = ap.parse_args(argv)

    if args.path == "-":
        text, source = sys.stdin.read(), "<stdin>"
    else:
        p = Path(args.path)
        if not p.exists():
            print(f"error: not found: {p}", file=sys.stderr)
            return 3
        try:
            text = p.read_text(errors="ignore")
        except OSError as e:
            print(f"error: cannot read {p}: {e}", file=sys.stderr)
            return 3
        source = str(p)

    try:
        report = lint(text, source, rule_filter=args.rule, strict_memory=args.strict_memory)
    except (ValueError, json.JSONDecodeError) as e:
        print(f"error: unparseable loop spec in {source}: {e}", file=sys.stderr)
        return 3

    if args.resolve:
        # Freeze each spec to an immutable audit snapshot; lint verdict stays the
        # exit code so `loop_lint --resolve spec.md` is still a CI gate. Non-fleet/
        # outer/scheduled specs get a snapshot too, but flagged unattended:false so a
        # caller knows the replay surface only earns its keep for long-lived loops.
        snaps = [resolve_snapshot(s, strict_memory=args.strict_memory)
                 for s in parse_specs(text, source)]
        print(json.dumps(snaps if len(snaps) != 1 else snaps[0], indent=2) if snaps
              else json.dumps({"error": "no loop spec found", "source": source}, indent=2))
    elif args.diagram:
        # Render the parsed spec(s); keep the lint verdict as the exit code so
        # `loop_lint --diagram spec.md` is still a CI-composable gate.
        blocks = diagrams(text, source, rule_filter=args.rule, strict_memory=args.strict_memory)
        if not blocks:
            print(f"%% loop-lint: no loop spec found in {source}")
        print("\n\n".join(blocks))
    elif args.json:
        print(json.dumps({
            "root": report.root,
            "n_specs": report.n_specs,
            "summary": report.summary,
            "findings": [asdict(f) for f in report.findings],
        }, indent=2))
    else:
        print(f"loop-lint: {source}  ({report.n_specs} spec{'s' if report.n_specs != 1 else ''})")
        if not report.findings:
            print("  OK — gate + stop + budget + separate verifier, every spec")
        for f in report.findings:
            print(f"  [{f.severity}] R{f.rule}: {f.title}")
            if f.file and f.line:
                print(f"      at {f.file}:{f.line}")
            if f.detail:
                print(f"      → {f.detail}")
        print(f"summary: {report.summary['FAIL']} fail · {report.summary['WARN']} warn")

    if report.summary["FAIL"] > 0:
        return 2
    if report.summary["WARN"] > 0:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
