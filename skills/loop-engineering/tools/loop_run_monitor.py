#!/usr/bin/env python3
"""loop-run-monitor — RUNTIME health gate for an agentic loop.

loop_lint.py is a STATIC check: it refuses a bad loop SPEC before the loop runs
(no gate / self-grading / unbounded). This is the complementary RUNTIME check:
it consumes an iteration TRACE the loop emits as it runs and mechanically detects
that the loop is STUCK — spinning without making progress — so the harness can
break the loop instead of burning the whole budget on a dead end.

The loop-engineering SKILL.md describes three runtime-health controls in prose
(stuck-detection, forced-entropy, cost-per-accepted-change) but only
`repeated_tool_error` was mechanical. This makes the other two executable.

A loop is STUCK (exit 2) when ANY of these mechanical triggers fires:

  S1 SAME-COMMAND     — the same command issued ``--cmd-window`` (default 3)
                        consecutive iterations (re-running the identical action
                        and expecting a different result).
  S2 REPEATED-ERROR   — the same error string on ``--err-window`` (default 2)
                        consecutive iterations (the loop is looping on one
                        failure — the existing `repeated_tool_error` symptom,
                        now consuming the trace directly).
  S3 NO-PROGRESS      — the steering metric did not move across ``--metric-window``
                        (default 2) consecutive iterations (no entropy / no
                        forward motion — forced-entropy or stop should kick in).

It ALSO reports cost-per-accepted-change: accepted changes vs total iterations
and total cost from the trace. A loop that spends a lot per accepted change is a
candidate for a cheaper inner loop or a better gate — this surfaces the number
(WARN over ``--max-cost-per-accept``) rather than guessing.

Exit code IS the verdict: 0 healthy · 1 any WARN (e.g. cost too high, no accepts
yet) · 2 STUCK (a stuck trigger fired) · 3 usage/unparseable.

House style mirrors loop_lint.py / cache_lint.py: stdlib only, typed
Finding/Report dataclasses, --json, exit-code verdict, no third-party deps.

----------------------------------------------------------------------------
TRACE SCHEMA (the small documented contract this tool consumes)
----------------------------------------------------------------------------
A trace is JSON: either a list of iteration objects, or an object with an
``iterations`` list (an optional top-level ``budget`` is ignored here — the
static budget cap is loop_lint's job). Read from a file path or ``-`` (stdin).

Each iteration object (all fields OPTIONAL — a sparse trace still lints; only
the fields present are checked):

  {
    "i":       0,                  # iteration index (informational)
    "command": "pytest -q",        # the action taken this iteration (S1)
    "error":   "AssertionError: x",# the error this iteration, "" / null if none (S2)
    "metric":  3,                   # the steering metric this iteration (S3);
                                    #   number (tests passing, % done, score…).
                                    #   None / absent => "unknown", not a stall.
    "accepted": false,             # did this iteration produce an ACCEPTED change?
    "cost":    1200,                # cost units for this iteration (tokens / $ / s);
                                    #   summed for cost-per-accepted-change.
    "state_revision": "abc123",     # optional loop-state revision/hash read by this pass
    "recalled": true,               # optional: pre-pass recall ran
    "wrote_state": true,            # optional: post-pass writeback ran
    "verdict": "fail"               # optional verifier verdict: pass/fail/blocked/...
  }

Minimal example (healthy): [{"command":"a","metric":1},{"command":"b","metric":2}]
Minimal example (stuck S1): [{"command":"a"},{"command":"a"},{"command":"a"}]
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Literal

Severity = Literal["OK", "WARN", "STUCK"]

# Defaults for the three windows (consecutive-iteration counts that trip a stuck
# trigger). Overridable on the CLI so a tight inner loop and a long outer loop
# can tune them independently.
DEFAULT_CMD_WINDOW = 3
DEFAULT_ERR_WINDOW = 2
DEFAULT_METRIC_WINDOW = 2


@dataclass
class Finding:
    code: str          # S1 / S2 / S3 / COST / ACCEPT
    severity: Severity
    title: str
    detail: str = ""
    at: int = -1       # iteration index the trigger fired at (-1 if N/A)


@dataclass
class Iteration:
    i: int = -1
    command: str = ""
    error: str = ""
    metric: float | None = None
    accepted: bool = False
    cost: float = 0.0


@dataclass
class Report:
    source: str
    n_iters: int = 0
    n_accepted: int = 0
    total_cost: float = 0.0
    cost_per_accept: float | None = None   # None when there are zero accepts
    findings: list[Finding] = field(default_factory=list)
    summary: dict[str, int] = field(default_factory=dict)

    def add(self, f: Finding) -> None:
        self.findings.append(f)

    def finalize(self) -> None:
        self.summary = {
            "WARN": sum(1 for f in self.findings if f.severity == "WARN"),
            "STUCK": sum(1 for f in self.findings if f.severity == "STUCK"),
        }


# --- Trace parsing --------------------------------------------------------

def _as_iters(data: Any) -> list[dict]:
    """Pull the iteration list out of a trace (a bare list, or {iterations:[...]})."""
    if isinstance(data, list):
        items = data
    elif isinstance(data, dict) and isinstance(data.get("iterations"), list):
        items = data["iterations"]
    else:
        raise ValueError("trace must be a JSON list of iterations, or an object "
                         "with an 'iterations' list")
    out: list[dict] = []
    for it in items:
        if not isinstance(it, dict):
            raise ValueError("each iteration must be a JSON object")
        out.append(it)
    return out


def _num_or_none(v: Any) -> float | None:
    """A metric/cost field coerced to float, or None if absent / not numeric.
    A non-numeric metric (a string label) is treated as None (unknown), never
    as a stall — S3 only fires on two equal NUMERIC metrics."""
    if v is None:
        return None
    if isinstance(v, bool):  # avoid True/False coercing to 1/0
        return None
    if isinstance(v, (int, float)):
        return float(v)
    return None


def parse_trace(text: str, source: str) -> list[Iteration]:
    data = json.loads(text)
    out: list[Iteration] = []
    for idx, raw in enumerate(_as_iters(data)):
        out.append(Iteration(
            i=int(raw["i"]) if isinstance(raw.get("i"), (int, float)) and not isinstance(raw.get("i"), bool) else idx,
            command=str(raw.get("command") or "").strip(),
            error=str(raw.get("error") or "").strip(),
            metric=_num_or_none(raw.get("metric")),
            accepted=bool(raw.get("accepted", False)),
            cost=_num_or_none(raw.get("cost")) or 0.0,
        ))
    return out


# --- Stuck triggers -------------------------------------------------------

def _trailing_run(values: list[str]) -> int:
    """Length of the run of identical NON-EMPTY values at the END of the list.
    Empty strings break the run (a missing command/error is not a repeat)."""
    if not values or not values[-1]:
        return 0
    last = values[-1]
    n = 0
    for v in reversed(values):
        if v == last and v:
            n += 1
        else:
            break
    return n


def _check_same_command(iters: list[Iteration], window: int) -> Finding | None:
    cmds = [it.command for it in iters]
    run = _trailing_run(cmds)
    if run >= window:
        return Finding("S1", "STUCK",
                       f"same command {run}× in a row (>= {window})",
                       f"command={cmds[-1]!r} reissued {run} consecutive iterations — "
                       "re-running the identical action expecting a different result.",
                       at=iters[-1].i)
    return None


def _check_repeated_error(iters: list[Iteration], window: int) -> Finding | None:
    errs = [it.error for it in iters]
    run = _trailing_run(errs)
    if run >= window:
        return Finding("S2", "STUCK",
                       f"same error {run}× in a row (>= {window})",
                       f"error={errs[-1]!r} on {run} consecutive iterations — the loop is "
                       "looping on one failure; break and re-plan instead of retrying.",
                       at=iters[-1].i)
    return None


def _check_no_progress(iters: list[Iteration], window: int) -> Finding | None:
    """The steering metric did not move across ``window`` consecutive iterations.
    Only NUMERIC metrics count; a window with any None metric is 'unknown' and
    does not trip (we never call progress on missing data)."""
    metrics = [it.metric for it in iters]
    if len(metrics) < window:
        return None
    tail = metrics[-window:]
    if any(m is None for m in tail):
        return None
    if len(set(tail)) == 1:
        return Finding("S3", "STUCK",
                       f"metric flat across {window} iterations (no progress)",
                       f"metric stuck at {tail[-1]} for {window} consecutive iterations — "
                       "no forward motion; force entropy (change approach) or stop.",
                       at=iters[-1].i)
    return None


# --- Driver ---------------------------------------------------------------

def monitor(text: str, source: str, *,
            cmd_window: int = DEFAULT_CMD_WINDOW,
            err_window: int = DEFAULT_ERR_WINDOW,
            metric_window: int = DEFAULT_METRIC_WINDOW,
            max_cost_per_accept: float | None = None) -> Report:
    iters = parse_trace(text, source)
    report = Report(source=source, n_iters=len(iters))

    if not iters:
        report.add(Finding("EMPTY", "WARN", "trace has no iterations",
                           "Nothing to monitor — emit at least one iteration object."))
        report.finalize()
        return report

    # Cost-per-accepted-change.
    report.n_accepted = sum(1 for it in iters if it.accepted)
    report.total_cost = round(sum(it.cost for it in iters), 6)
    if report.n_accepted > 0:
        # Prefer cost when the trace carries cost; otherwise fall back to
        # iterations-per-accept so the metric is always meaningful.
        basis = report.total_cost if report.total_cost > 0 else float(report.n_iters)
        report.cost_per_accept = round(basis / report.n_accepted, 4)
    else:
        report.cost_per_accept = None

    # Stuck triggers.
    for chk, win in ((_check_same_command, cmd_window),
                     (_check_repeated_error, err_window),
                     (_check_no_progress, metric_window)):
        f = chk(iters, win)
        if f:
            report.add(f)

    # Cost / acceptance WARNs (advisory — they do not break the loop, but they
    # surface a loop that spends without producing accepted change).
    if report.n_accepted == 0:
        report.add(Finding("ACCEPT", "WARN",
                           f"no accepted changes across {report.n_iters} iterations",
                           "The loop has produced no accepted change yet — verify the gate "
                           "can ever pass, or the loop is spending for nothing."))
    if (max_cost_per_accept is not None and report.cost_per_accept is not None
            and report.cost_per_accept > max_cost_per_accept):
        report.add(Finding("COST", "WARN",
                           f"cost-per-accepted-change {report.cost_per_accept} > {max_cost_per_accept}",
                           f"total_cost={report.total_cost} over {report.n_accepted} accepted "
                           "changes — consider a cheaper inner loop or a tighter gate."))

    report.finalize()
    return report


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(
        prog="loop-run-monitor",
        description="Runtime stuck-detector + cost-per-accepted-change for an agentic loop trace.")
    ap.add_argument("path", help="iteration-trace JSON file, or '-' for stdin")
    ap.add_argument("--json", action="store_true", help="emit the typed report as JSON")
    ap.add_argument("--cmd-window", type=int, default=DEFAULT_CMD_WINDOW,
                    help=f"same-command run length that trips STUCK (default {DEFAULT_CMD_WINDOW})")
    ap.add_argument("--err-window", type=int, default=DEFAULT_ERR_WINDOW,
                    help=f"same-error run length that trips STUCK (default {DEFAULT_ERR_WINDOW})")
    ap.add_argument("--metric-window", type=int, default=DEFAULT_METRIC_WINDOW,
                    help=f"flat-metric run length that trips STUCK (default {DEFAULT_METRIC_WINDOW})")
    ap.add_argument("--max-cost-per-accept", type=float, default=None,
                    help="WARN when cost-per-accepted-change exceeds this threshold")
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
        report = monitor(text, source,
                         cmd_window=args.cmd_window,
                         err_window=args.err_window,
                         metric_window=args.metric_window,
                         max_cost_per_accept=args.max_cost_per_accept)
    except (ValueError, json.JSONDecodeError) as e:
        print(f"error: unparseable trace in {source}: {e}", file=sys.stderr)
        return 3

    if args.json:
        print(json.dumps({
            "source": report.source,
            "n_iters": report.n_iters,
            "n_accepted": report.n_accepted,
            "total_cost": report.total_cost,
            "cost_per_accept": report.cost_per_accept,
            "summary": report.summary,
            "findings": [asdict(f) for f in report.findings],
        }, indent=2))
    else:
        print(f"loop-run-monitor: {report.source}  ({report.n_iters} iteration"
              f"{'s' if report.n_iters != 1 else ''})")
        cpa = report.cost_per_accept if report.cost_per_accept is not None else "n/a (0 accepted)"
        print(f"  accepted={report.n_accepted}  total_cost={report.total_cost}  "
              f"cost_per_accepted_change={cpa}")
        if not report.findings:
            print("  OK — no stuck trigger fired")
        for f in report.findings:
            print(f"  [{f.severity}] {f.code}: {f.title}")
            if f.at >= 0:
                print(f"      at iteration {f.at}")
            if f.detail:
                print(f"      → {f.detail}")
        print(f"summary: {report.summary['STUCK']} stuck · {report.summary['WARN']} warn")

    if report.summary["STUCK"] > 0:
        return 2
    if report.summary["WARN"] > 0:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
