#!/usr/bin/env python3
"""loop-lint — static linter for an agentic loop spec.

The article thesis: a loop is a GENERATOR wired to a VERIFIER, and the verifier
is the bottleneck. So a loop you cannot describe as {gate, stop, budget,
generator != verifier} is not a loop — it is an open-ended spin. This linter
refuses such specs BEFORE the loop runs, turning the doctrine into a mechanical
gate (per Brainer's "no prose rule where a mechanical gate can stand").

It validates a loop spec against three FAIL rules and three WARN rules:

  R1 NO-GATE          (FAIL) — gate absent, or prose with no machine-checkable
                               pass/fail signal (allowlist: a command / test id /
                               path / assertion / exit-code / regex / schema ref).
  R2 NO-STOP-OR-BUDGET(FAIL) — stop condition missing, or budget cap missing /
                               unbounded (no numeric iteration|token|wallclock cap).
  R3 SELF-GRADING     (FAIL) — generator == verifier (an agent grading its own
                               homework), or a closed loop with an empty verifier.
  R4 OPEN-NO-ACK      (WARN) — open topology without `accepted_open_loop: true`
                               (declare that "no feedback" is intentional).
  R5 FLEET-NO-QUORUM  (WARN) — fleet topology with no aggregation/quorum gate.
  R6 NO-TOPOLOGY      (WARN) — topology not declared (you did not choose a shape).

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
    "accepted_open_loop", "quorum", "aggregate",
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

# R1 allowlist: a gate PASSES only if it names a machine-checkable signal. This
# is an ALLOWLIST, not a prose denylist — "the reviewer agrees" has no token and
# FAILs (the denylist false-negative the adversarial review flagged). Mirrors
# verify-before-completion's "fast, deterministic, agent-runnable pass/fail".
_MACHINE_GATE = [
    # command runners / build tools (word-boundary so prose nouns don't match)
    re.compile(r"\b(pytest|unittest|jest|vitest|mocha|tox|nox|ruff|eslint|mypy|tsc|"
               r"npm|pnpm|yarn|cargo|gradle|mvn|dotnet|deno|bats|rspec|phpunit)\b", re.I),
    re.compile(r"\b(go|cargo)\s+test\b", re.I),
    re.compile(r"\b(make|bash|sh|zsh|python3?|node|ruby|perl)\s+\S", re.I),
    # an executable path or a code/data file the gate reads
    re.compile(r"(^|\s)\.?/?[\w./-]+\.(py|sh|js|ts|tsx|mjs|cjs|json|ya?ml|toml|rs|go|rb)\b", re.I),
    re.compile(r"(^|\s)\./\S+"),                       # ./run-checks
    # assertion / exit-code / operator / substitution / pytest-nodeid shapes
    re.compile(r"==|!=|>=|<=|\$\?|\$\(|::"),
    re.compile(r"\bassert\b|\bexit\s*code\b|\bexit\s+\d|\breturns?\s+\d|\bstatus\s+\d", re.I),
    re.compile(r"\b(diff|grep)\s+\S", re.I),
    # explicit machine markers
    re.compile(r"\b(regex|schema|cmd|command)\s*[:=]", re.I),
]

# A human decision is ALSO a concrete pass/fail gate — the article endorses "a
# handoff to a human with the run data attached" and both source harnesses use
# human escalation (autonomy-loop's FOR-REVIEW.md, HarnessCode's PAUSE_FOR_HUMAN).
# So an explicit human-approval gate is NOT gateless; it just isn't autonomous.
# Discriminator vs vacuous prose: an explicit approval/sign-off/escalation verb,
# not "looks correct" / "the reviewer agrees".
_HUMAN_GATE = re.compile(
    r"\b(approv\w+|sign[\s-]?off|signs?\s+off|signed\s+off|escalat\w+|"
    r"human\s+(review|sign|approv\w+|decision|gate)|for[\s-]?review|owner\s+approv\w+)\b", re.I)

_UNBOUNDED = re.compile(r"\b(unbounded|infinite|none|no\s*limit|unlimited|never|forever)\b", re.I)
_QUORUM = re.compile(r"\b(quorum|aggregat\w*|merge|reviewer|vote|consensus|majority|reduce)\b", re.I)

# Words stripped to expose the ACTOR IDENTITY behind a role phrase, so that
# "Alfred drafts the briefing" and "Alfred reviews the briefing" are recognized
# as the SAME actor (self-grading) even though the literal strings differ.
_ROLE_VERBS = frozenset("""drafts draft writes write produces produce generates generate authors author
creates create makes make codes code builds build implements implement proposes propose composes compose
designs design plans plan reviews review checks check verifies verify validates validate audits audit
tests test grades grade judges judge evaluates evaluate inspects inspect approves approve runs run
reads read assesses assess critiques critique refutes refute""".split())
_STOP_WORDS = frozenset("""the a an then and of its his her their our own work output draft result results
on for it to in with that this each per one two three then who""".split())
# Identities so generic they don't establish independence ("a human"/"an agent"
# on both sides is not a *specific* shared actor, so it must not false-fire).
_GENERIC_ACTORS = frozenset("""human agent agents model models llm ai bot worker person people someone
role roles subagent subagents pass passes""".split())


def _norm(s: str) -> str:
    """Normalize an actor string for exact self-grading comparison."""
    s = _strip_quotes(s).casefold().strip()
    s = re.sub(r"\s+", " ", s)
    s = s.strip(".,;:!?-_ ")
    return s


def _actor_identity(s: str) -> frozenset[str]:
    """The set of identity tokens in an actor phrase, with role-verbs/stopwords
    removed. {Alfred drafts the briefing} -> {alfred, briefing}."""
    toks = re.findall(r"[a-z0-9][a-z0-9_-]*", s.casefold())
    return frozenset(t for t in toks if t not in _ROLE_VERBS and t not in _STOP_WORDS)


def _same_actor(generator: str, verifier: str) -> bool:
    """True if generator and verifier resolve to the SAME specific actor — same
    identity tokens, with at least one non-generic token (a real name/model, not
    a bare 'human'/'agent' on both sides)."""
    g, v = _actor_identity(generator), _actor_identity(verifier)
    return bool(g) and g == v and any(t not in _GENERIC_ACTORS for t in g)


def _has_machine_gate(gate: str) -> bool:
    return any(rx.search(gate) for rx in _MACHINE_GATE)


def _has_human_gate(gate: str) -> bool:
    return bool(_HUMAN_GATE.search(gate))


def _budget_is_capped(budget: str) -> bool:
    if not budget or _UNBOUNDED.search(budget):
        return False
    return bool(re.search(r"\d", budget))  # a real cap carries a number


def _topology_tokens(topology: str) -> set[str]:
    return {t for t in re.split(r"[^a-z]+", topology.lower()) if t}


def _is_true(v: str) -> bool:
    return _strip_quotes(v).strip().lower() in {"true", "yes", "1", "on"}


# --- Checks ---------------------------------------------------------------

def check_spec(report: Report, spec: Spec, rule_filter: int | None) -> None:
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
    is_closed = "closed" in toks or (not is_open and bool(toks))

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
        if not _budget_is_capped(budget):
            report.add(Finding(2, "FAIL", f"spec '{label}' has no numeric `budget` cap",
                               src, spec.line_of("budget") or spec.start_line,
                               f"budget={budget!r}: an unbounded loop is a spin. Give a numeric cap "
                               "(max_iterations / max_tokens / max_wallclock)."))

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


def lint(text: str, source: str, rule_filter: int | None = None) -> Report:
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
        check_spec(report, spec, rule_filter)
    report.finalize()
    return report


# --- Driver ---------------------------------------------------------------

def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="loop-lint",
                                 description="Static linter for an agentic loop spec.")
    ap.add_argument("path", help="loop-spec file (.md with a ```loop block / .yaml / .json), or '-' for stdin")
    ap.add_argument("--json", action="store_true", help="emit the typed report as JSON")
    ap.add_argument("--rule", type=int, choices=[1, 2, 3, 4, 5, 6], help="restrict to one rule")
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
        report = lint(text, source, rule_filter=args.rule)
    except (ValueError, json.JSONDecodeError) as e:
        print(f"error: unparseable loop spec in {source}: {e}", file=sys.stderr)
        return 3

    if args.json:
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
