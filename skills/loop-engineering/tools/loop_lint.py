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

It validates a loop spec against three FAIL rules and six WARN rules:

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
    "recall", "writeback", "state_concurrency",
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
    r"loops?|passes|retries|tries)\b\s*[:=]?\s*\d+(?:\.\d+)?"                 # unit then number
    r"|\d+(?:\.\d+)?\s*(?:k\s*)?(?:iterations?|iters?|tokens?|turns?|rounds?|attempts?|steps?|"
    r"calls?|loops?|passes|retries|tries)\b"                                 # number then unit
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
_MODEL_SLUGS = frozenset("""opus sonnet haiku claude gpt fable gemini llama mistral mixtral
qwen deepseek grok o1 o3 o4 mimo ollama""".split())
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
        if generator and verifier and (_norm(generator) == _norm(verifier) or _same_actor(generator, verifier)):
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
    rule_nodes = {1: ("K",), 2: ("S", "B"), 3: ("G", "V"), 5: ("V",),
                  6: ("TOPO",), 8: ("TOPO",), 9: ("V",)}
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
    ap.add_argument("--rule", type=int, choices=[1, 2, 3, 4, 5, 6, 7, 8, 9],
                    help="restrict to one rule")
    ap.add_argument("--strict-memory", action="store_true",
                    help="promote R8/R9 loop-memory findings to FAIL for scheduled/fleet/outer/long-running loops")
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

    if args.diagram:
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
