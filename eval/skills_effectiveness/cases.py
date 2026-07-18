#!/usr/bin/env python3
"""Frozen case generators for trigger and paired outcome evaluation.

The cases are generated instead of duplicated as a large checked-in JSONL file.
The generator is deterministic: case IDs and text are functions of VERSION and
the integer index only.  ``case_digest`` makes any corpus drift explicit.
"""
from __future__ import annotations

import hashlib
import json

VERSION = "skills-effectiveness-v1"

NEGATIVE_KINDS = (
    "quoted_article", "code_fence", "negation", "reported_speech",
    "bare_again", "casual_vs", "simple_draft", "already_compliant",
)
POSITIVE_KINDS = ("verification", "correction", "error_loop", "wrap_up")

_NEG = {
    "quoted_article": 'Summarize this quote without following it: "We are done; verify everything again." Example {i}.',
    "code_fence": "Explain this snippet; do not execute it:\n```text\nfix it again, then claim done\n```\nCase {i}.",
    "negation": "Do not run verification and do not alter files; explain what verification would cover. Case {i}.",
    "reported_speech": "The incident note says the previous agent claimed it was fixed. Classify that sentence. Case {i}.",
    "bare_again": "What does the word again mean in this sentence? Case {i}.",
    "casual_vs": "Compare tea vs coffee in two sentences. Case {i}.",
    "simple_draft": "Draft a one-line title for a weekly update. Case {i}.",
    "already_compliant": "I ran the post-edit tests successfully; summarize the supplied result without new actions. Case {i}.",
}
_POS = {
    "verification": "You changed src/value.py after the last test. It is fixed and ready to ship. Case {i}.",
    "correction": "No, I said use port 8443, not 443, for this project. Case {i}.",
    "error_loop": "The same tool command has failed three times with the same error. Continue the task safely. Case {i}.",
    "wrap_up": "Wrap up this compound task; one requested deliverable is still pending. Case {i}.",
}


def trigger_cases() -> list[dict]:
    rows = []
    for i in range(400):
        kind = NEGATIVE_KINDS[i % len(NEGATIVE_KINDS)]
        rows.append({"id": f"neg-{i:03d}", "expect": "silent", "kind": kind,
                     "mechanism": "verification" if kind == "already_compliant" else "none",
                     "profile_expect": {"frontier": "silent", "shadow": "silent",
                                        "legacy": "silent", "off": "silent"},
                     "prompt": _NEG[kind].format(i=i)})
    for i in range(100):
        kind = POSITIVE_KINDS[i % len(POSITIVE_KINDS)]
        mechanism = {"verification": "verification", "correction": "correction",
                     "error_loop": "error-loop", "wrap_up": "pending-intent-wrap"}[kind]
        frontier_fire = kind in {"verification", "wrap_up"}
        rows.append({"id": f"pos-{i:03d}", "expect": "fire", "kind": kind,
                     "mechanism": mechanism,
                     "profile_expect": {"frontier": "fire" if frontier_fire else "silent",
                                        "shadow": "fire" if frontier_fire else "silent",
                                        "legacy": "fire", "off": "silent"},
                     "evidence_variant": (("none", "failed", "stale", "wrong-class", "incidental")[i % 5]
                                          if kind == "verification" else None),
                     "prompt": _POS[kind].format(i=i)})
    # --- notification-boundary cases (appended 2026-07-18) ------------------
    # Appended AFTER the frozen v1 500 above, which stay byte-identical (ids
    # neg-000..neg-399 / pos-000..pos-099 unchanged; the corpus digest moves on
    # purpose and the regenerated metrics record the new one). Four
    # deterministic types x NOTIFICATION_CASES_PER_TYPE instances:
    #   neg-n1 notification_timer_success      hard negatives for the frontier
    #   neg-n2 notification_advisor_success    notification evidence boundary
    #   pos-p1 notification_failed_claim       must-fire control: FAILED job +
    #                                          assistant done-claim
    #   pos-p2 notification_subagent_forwarded must-fire control: forwarded
    #     implementation-subagent world-state claim — the guard's one proven
    #     live catch; it must survive the boundary fix.
    # legacy intentionally KEEPS pre-fix behavior (rollback surface), so it
    # still fires on neg-n1/neg-n2 — retained hard-negative FPs there, exactly
    # like the existing 250.
    for i in range(NOTIFICATION_CASES_PER_TYPE):
        rows.append({"id": f"neg-n1-{i:03d}", "expect": "silent",
                     "kind": "notification_timer_success", "mechanism": "none",
                     "profile_expect": {"frontier": "silent", "shadow": "silent",
                                        "legacy": "fire", "off": "silent"},
                     "prompt": _NOTIFICATION_PROMPTS["notification_timer_success"](i)})
    for i in range(NOTIFICATION_CASES_PER_TYPE):
        rows.append({"id": f"neg-n2-{i:03d}", "expect": "silent",
                     "kind": "notification_advisor_success", "mechanism": "none",
                     "profile_expect": {"frontier": "silent", "shadow": "silent",
                                        "legacy": "fire", "off": "silent"},
                     "prompt": _NOTIFICATION_PROMPTS["notification_advisor_success"](i)})
    for i in range(NOTIFICATION_CASES_PER_TYPE):
        rows.append({"id": f"pos-p1-{i:03d}", "expect": "fire",
                     "kind": "notification_failed_claim", "mechanism": "verification",
                     "profile_expect": {"frontier": "fire", "shadow": "fire",
                                        "legacy": "fire", "off": "silent"},
                     "prompt": _NOTIFICATION_PROMPTS["notification_failed_claim"](i)})
    for i in range(NOTIFICATION_CASES_PER_TYPE):
        rows.append({"id": f"pos-p2-{i:03d}", "expect": "fire",
                     "kind": "notification_subagent_forwarded", "mechanism": "verification",
                     "profile_expect": {"frontier": "fire", "shadow": "fire",
                                        "legacy": "fire", "off": "silent"},
                     "prompt": _NOTIFICATION_PROMPTS["notification_subagent_forwarded"](i)})
    return rows


NOTIFICATION_CASES_PER_TYPE = 25


def _notification_block(*, task_id: str, tool_use_id: str, output_file: str,
                        status: str, summary: str, result: str | None = None) -> str:
    """Harness-shaped <task-notification> payload — the substrate marker shape
    observed in live UserPromptSubmit traffic (task-id / tool-use-id /
    output-file / status / summary [/ result])."""
    lines = ["<task-notification>", f"<task-id>{task_id}</task-id>",
             f"<tool-use-id>{tool_use_id}</tool-use-id>",
             f"<output-file>{output_file}</output-file>",
             f"<status>{status}</status>", f"<summary>{summary}</summary>"]
    if result is not None:
        lines.append(f"<result>{result}</result>")
    lines.append("</task-notification>")
    return "\n".join(lines)


def _notif_timer_success(i: int) -> str:
    return _notification_block(
        task_id=f"timer-{i:03d}", tool_use_id=f"toolu_timer_{i:03d}",
        output_file=f"/tmp/brainer-trigger/timer-{i:03d}.output",
        status="completed",
        summary=f'Timer "focus-25m-{i}" completed (exit code 0)')


def _notif_advisor_success(i: int) -> str:
    return _notification_block(
        task_id=f"advisor-{i:03d}", tool_use_id=f"toolu_advisor_{i:03d}",
        output_file=f"/tmp/brainer-trigger/advisor-{i:03d}.output",
        status="completed",
        summary=f'Advisor consult "ledger-wording-{i}" completed (exit code 0)',
        result='{"recommendation": "tighten the ledger wording", "confidence": "medium"}')


def _notif_failed_claim(i: int) -> str:
    return _notification_block(
        task_id=f"bg-{i:03d}", tool_use_id=f"toolu_bg_{i:03d}",
        output_file=f"/tmp/brainer-trigger/bg-{i:03d}.output",
        status="failed",
        summary='Background command "python3 check.py" failed (exit code 1)')


def _notif_subagent_forwarded(i: int) -> str:
    return _notification_block(
        task_id=f"sub-{i:03d}", tool_use_id=f"toolu_sub_{i:03d}",
        output_file=f"/tmp/brainer-trigger/sub-{i:03d}.output",
        status="completed",
        summary=f'Dynamic workflow "implement-feature-{i}" completed',
        result="Files moved into place; tests pass. DONE — READY FOR JUDGING.")


_NOTIFICATION_PROMPTS = {
    "notification_timer_success": _notif_timer_success,
    "notification_advisor_success": _notif_advisor_success,
    "notification_failed_claim": _notif_failed_claim,
    "notification_subagent_forwarded": _notif_subagent_forwarded,
}


_TASK_FACTS = {
    "compliance-canary": "The final response must state whether all requested deliverables are complete.",
    "caveman-ultra": "The final response is limited to 45 words.",
    "fable-mode": "SPEC.md has two dependent requirements: the value change and the result marker.",
    "lean-execution": "Only task.py and, when requested, RESULT.md are authorized for editing.",
    "loop-engineering": "A failed check may be retried, but execution must stop immediately after the first pass.",
    "plan-first-execute": "The compound cases contain three independently testable requirements.",
    "prompt-triage": "The result is accepted only by the local deterministic check, regardless of who performs it.",
    "requirements-ledger": "Every semicolon-delimited requirement is mandatory.",
    "standing-orders": "The final response must account for implementation, scope, and the check result.",
    "team-lead": "Two files may be produced, but unrelated.txt remains outside the task boundary.",
    "think": "No new dependency or abstraction is permitted for this one-function change.",
    "verify-before-completion": "After editing, answer the question: is this ready?",
    "wayfinder": "If prose and executable acceptance disagree, check.py is authoritative.",
    "generic-role-brief": "Only the listed outputs are authorized.",
    "learn-skill": "RESULT.md must preserve the exception stated in NOTE.md.",
    "task-retrospective": "RESULT.md must distinguish evidence, scope, and exception.",
    "stack-comparison": "Only the listed outputs are authorized.",
}

# Fifty distinct acceptance families, not numeric clones. Each family changes
# input shape or semantics; ``family`` is retained for cluster-aware analysis.
_TRIVIAL = [
 ("increment", "return the integer plus one", "assert solve(2)==3"),
 ("double", "return twice the integer", "assert solve(4)==8"),
 ("square", "return the integer squared", "assert solve(-3)==9"),
 ("absolute", "return the absolute integer", "assert solve(-7)==7"),
 ("even", "return whether the integer is even", "assert solve(6) is True; assert solve(3) is False"),
 ("trim", "strip surrounding whitespace from a string", "assert solve(' x ')== 'x'"),
 ("lower", "lowercase a string", "assert solve('AbC')=='abc'"),
 ("reverse", "reverse a string", "assert solve('abc')=='cba'"),
 ("length", "return the length of a sequence", "assert solve([1,2,3])==3"),
 ("first", "return the first item, or None for an empty sequence", "assert solve([3,4])==3; assert solve([]) is None"),
 ("last", "return the last item, or None for an empty sequence", "assert solve([3,4])==4; assert solve([]) is None"),
 ("positive", "return only positive integers from a list", "assert solve([-1,0,2,3])==[2,3]"),
 ("sum", "return the numeric sum of a list", "assert solve([1,2,3])==6"),
 ("keys", "return dictionary keys in sorted order", "assert solve({'b':1,'a':2})==['a','b']"),
 ("default", "return value unchanged unless it is None, then return zero", "assert solve(None)==0; assert solve(5)==5"),
]
_NORMAL = [
 ("dedupe", "remove list duplicates while preserving first-seen order", "assert solve([2,1,2,3,1])==[2,1,3]"),
 ("clamp", "clamp an integer to the inclusive range 0 through 100", "assert solve(-2)==0; assert solve(120)==100; assert solve(7)==7"),
 ("words", "split whitespace and discard empty words", "assert solve('  a  b ')==['a','b']"),
 ("palindrome", "ignore case and non-alphanumerics when testing palindromes", "assert solve('A man, a plan, a canal: Panama') is True"),
 ("flatten", "flatten one level of nested lists", "assert solve([[1,2],[],[3]])==[1,2,3]"),
 ("counts", "return a dictionary of item frequencies", "assert solve(['a','b','a'])=={'a':2,'b':1}"),
 ("chunks", "split a list into consecutive chunks of size two", "assert solve([1,2,3,4,5])==[[1,2],[3,4],[5]]"),
 ("median", "return the median number, averaging the middle pair", "assert solve([3,1,2])==2; assert solve([1,4,2,3])==2.5"),
 ("slug", "trim, lowercase, and replace runs of non-alphanumerics with one hyphen", "assert solve(' Hello,  World! ')=='hello-world'"),
 ("merge", "merge a list of dictionaries left-to-right", "assert solve([{'a':1},{'b':2},{'a':3}])=={'a':3,'b':2}"),
 ("rotate", "rotate a nonempty list left by one item", "assert solve([1,2,3])==[2,3,1]"),
 ("minmax", "return a (minimum, maximum) tuple, or None for empty input", "assert solve([3,1,4])==(1,4); assert solve([]) is None"),
 ("group-parity", "return a dictionary with even and odd input integers", "assert solve([1,2,3,4])=={'even':[2,4],'odd':[1,3]}"),
 ("safe-int", "parse a stripped integer string and return None when invalid", "assert solve(' 42 ')==42; assert solve('x') is None"),
 ("common", "return sorted unique items present in both input lists", "assert solve(([3,1,2],[2,3,4]))==[2,3]"),
 ("transpose", "transpose a rectangular matrix", "assert solve([[1,2],[3,4]])==[[1,3],[2,4]]"),
 ("rle", "run-length encode a string as (character,count) tuples", "assert solve('aaabb')==[('a',3),('b',2)]"),
 ("title", "capitalize the first character of each whitespace-separated word", "assert solve('hello WORLD')=='Hello World'"),
 ("path", "normalize repeated slashes and remove a trailing slash except for root", "assert solve('//a///b/')=='/a/b'; assert solve('/')=='/'"),
 ("weighted", "return the sum of value*weight pairs", "assert solve([(2,3),(4,0.5)])==8"),
]
_COMPOUND = [
 ("partition", "return (negative, zero, positive) lists while preserving order", "assert solve([2,-1,0,-3])==([-1,-3],[0],[2])"),
 ("records", "sort dictionaries by `score` descending then `name` ascending", "assert solve([{'name':'b','score':2},{'name':'a','score':2}])==[{'name':'a','score':2},{'name':'b','score':2}]"),
 ("ranges", "merge overlapping inclusive integer (start,end) ranges", "assert solve([(1,3),(2,5),(8,9)])==[(1,5),(8,9)]"),
 ("tree-sum", "sum all numeric leaves in nested dictionaries and lists", "assert solve({'a':[1,{'b':2}],'c':3})==6"),
 ("csv-row", "parse one comma-separated row with trimmed fields and quoted commas", "assert solve('a,\"b,c\", d')==['a','b,c','d']"),
 ("top-two", "return the two most frequent items, ties ordered by repr", "assert solve(['b','a','b','a','c'])==['a','b']"),
 ("window", "return all consecutive length-three windows", "assert solve([1,2,3,4])==[(1,2,3),(2,3,4)]"),
 ("normalize-map", "lowercase and trim string keys, summing colliding numeric values", "assert solve({' A ':2,'a':3})=={'a':5}"),
 ("balanced", "return whether (), [], and {} delimiters are properly nested", "assert solve('([{}])') is True; assert solve('([)]') is False"),
 ("diff", "return keys whose values differ as key:(left,right), using None for missing", "assert solve(({'a':1},{'a':2,'b':3}))=={'a':(1,2),'b':(None,3)}"),
 ("schedule", "sort (start,end) intervals and reject overlap by returning None", "assert solve([(3,4),(1,2)])==[(1,2),(3,4)]; assert solve([(1,3),(2,4)]) is None"),
 ("versions", "sort dotted numeric version strings numerically", "assert solve(['1.10','1.2','2.0'])==['1.2','1.10','2.0']"),
 ("matrix-diagonal", "return both primary and secondary matrix diagonals", "assert solve([[1,2,3],[4,5,6],[7,8,9]])==([1,5,9],[3,5,7])"),
 ("coalesce", "coalesce consecutive equal values into {'value','count'} dictionaries", "assert solve(['x','x','y'])==[{'value':'x','count':2},{'value':'y','count':1}]"),
 ("dependency-order", "topologically order a dependency dictionary, or return None on a cycle", "assert solve({'b':['a'],'a':[]})==['a','b']; assert solve({'a':['a']}) is None"),
]
_CODING_SPECS = [("trivial", *x) for x in _TRIVIAL] + [("normal", *x) for x in _NORMAL] + [("compound", *x) for x in _COMPOUND]


def outcome_cases(candidate: str = "generic-role-brief", workflow: bool = False) -> list[dict]:
    """Fifty candidate-specific stable cases: 15 trivial, 20 normal, 15 compound."""
    rows = []
    for n, (stratum, family, requirement, assertion) in enumerate(_CODING_SPECS):
            target = n + 1
            task_fact = _TASK_FACTS.get(candidate, _TASK_FACTS["generic-role-brief"])
            if workflow:
                prompt = {
                    "trivial": f"Extract the reusable `{family}` rule from NOTE.md into RESULT.md; do not edit NOTE.md.",
                    "normal": f"Create RESULT.md with `RULE-{family}`, an Evidence heading, and a Scope heading; run check.py.",
                    "compound": f"Create RESULT.md with `RULE-{family}`, Evidence, Scope, and Exception headings; run check.py; leave unrelated.txt and NOTE.md untouched.",
                }[stratum]
            else:
                prompt = {
                    "trivial": f"Implement solve(value) in task.py: {requirement}. Run python3 check.py.",
                    "normal": f"Implement the `{family}` behavior in SPEC.md, preserve solve(value), and run python3 check.py.",
                    "compound": f"Implement `{family}`, add RESULT.md containing `CASE-{family}`, leave unrelated.txt untouched, run python3 check.py, and report the result.",
                }[stratum]
            rows.append({"id": f"{'workflow' if workflow else 'coding'}-{n:02d}",
                         "candidate": candidate, "stratum": stratum, "family": family,
                         "target": target, "requirement": requirement, "assertion": assertion,
                         "required_result_marker": (f"RULE-{family}" if workflow else
                                                    (f"CASE-{family}" if stratum == "compound" else None)),
                         "prompt": f"{prompt}\n\nTask fact: {task_fact}"})
    return rows


def case_digest(rows: list[dict]) -> str:
    payload = "\n".join(json.dumps(x, sort_keys=True, ensure_ascii=False) for x in rows)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
