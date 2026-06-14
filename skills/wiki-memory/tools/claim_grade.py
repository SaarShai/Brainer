from __future__ import annotations

"""Claim grading — classify a knowledge claim by EPISTEMIC TYPE.

The shared primitive for three epistemic jobs the wiki lacked at claim (sentence)
granularity, distinct from the page-level `type:` enum:
  - quality-of-claim typing (data vs opinion vs decision)
  - type-aware contradiction surfacing (data×data = hard; opinion×opinion = divergence)
  - the observation -> hypothesis -> rule maturity ladder

Design (borrowed + pruned from a 2026-06 research pass — Toulmin-lite structural
tagging, fact/opinion lexical signals, ADR conventions; deliberately NOT adopting
NLI models, numeric truth-scores, or >5 types):
  - Deterministic: regex + lexical markers, no ML, no deps. Fast enough to lint with.
  - Type is ORTHOGONAL to truth. A confident, well-formed, WRONG claim still grades
    `observation`. We never emit a 0-1 "truth" score (the measured anti-pattern).
  - FIVE fine types only (anti-bloat): observation | decision | rule | hypothesis | opinion.
  - A coarse roll-up serves the contradiction layer:
        data      <- observation              (empirical; conflicts are HARD)
        directive <- decision, rule            (chosen/normative)
        judgment  <- hypothesis, opinion       (tentative/subjective; divergence is EXPECTED)

`grade_claim(text)` returns {type, klass, has_evidence, has_hedge, markers}.
"""

import re

CLAIM_TYPES = ("observation", "decision", "rule", "hypothesis", "opinion")
# `unknown` is the abstention sentinel (no epistemic marker fired) — NOT a 6th
# type. Blind-validation (2026-06) showed forcing unmarked prose into a type
# (esp. default->observation on directive-heavy SOPs) tanks precision; honest
# abstention + high precision on what we DO emit serves the downstream
# contradiction/synthesis layers better than false confidence.
KLASS = {"observation": "data",
         "decision": "directive", "rule": "directive",
         "hypothesis": "judgment", "opinion": "judgment",
         "unknown": "unclassified"}

# --- marker inventories (word-boundary, case-insensitive) -------------------
# Uncertainty / tentativeness -> hypothesis signal.
_HEDGE = re.compile(
    r"\b(might|maybe|may\b|could|perhaps|possibly|probably|likely|seems?|"
    r"appears?|suspect|guess|presumably|unsure|tentativ\w*|conjectur\w*|"
    r"hypothesi\w*|i think|i bet|not sure|unclear whether|to be confirmed|\btbc\b)\b",
    re.I)

# An explicit choice/commitment was made -> decision. Split FIRM (committed, a
# hedge cannot demote it) from SOFT (tentative/future, a hedge -> hypothesis).
_DECISION_FIRM = re.compile(
    r"\b(decided?|decision\b|chose|chosen|choosing|opted|settled on|"
    r"deprecat(?:ed|ing)?|rejected .{0,80}? in fav(?:o)?ur of|picked|"
    r"standardiz(?:ed|ing) on)\b",
    re.I)
_DECISION_SOFT = re.compile(
    r"\b(going with|went with|adopt(?:ed|ing)?|switch(?:ed|ing)? to|"
    r"migrat(?:ed|ing) to|we (?:will|now) use)\b",
    re.I)

# First-person taste ("I prefer X over Y") is an OPINION, and must beat the
# generic 'prefer ... over' directive rule below.
_FP_TASTE = re.compile(r"\bi (?:like|love|hate|dislike|prefer|find)\b", re.I)

# Bare-imperative directive ("Resolve conflicts ...", "Use before ...") — a rule
# phrased in imperative mood without an always/never/must marker. High-precision
# curated verb list, anchored at start. Checked AFTER evidence so "Run took 4.2s"
# (past tense + measurement) stays an observation.
_IMPERATIVE_VERBS = (
    "resolve ensure avoid keep use prefer treat record check confirm verify store "
    "gate route skip ask stop drop favour favor cite retrieve list distinguish define "
    "capture decide flag mark note name pick choose default prioritise prioritize scope "
    "limit restrict require document validate track surface propose suggest recommend "
    "separate group cluster merge split hold log return raise handle prevent allow deny "
    "grant expand reduce simplify prune batch cache lint label tag sort filter escalate "
    "downshift write read run set add remove update start begin finish wait map fold "
    "be make do give take call send pull push apply enforce respect honour honor"
).split()
# Bare-imperative directive: a base verb at the sentence start OR right after a
# clause boundary (leading "In coach mode, hold it" / "Prompt generation: retrieve
# X"), NOT followed by a noun-indicator (of/is/are/was/were/:) which would mean
# the verb is a noun ("List of sources", "Check is green"). Checked AFTER evidence
# so measured claims stay observation. The clause-boundary head is bounded to a
# short prefix to keep precision (a verb deep in a sentence is usually not the act).
_IMPERATIVE = re.compile(
    r"(?:^|^.{0,40}?[,:]\s+)(?:" + "|".join(_IMPERATIVE_VERBS) + r")\b"
    r"(?!\s+(?:of|is|are|was|were)\b)(?!\s*:)",
    re.I)

# General normative / conditional directive -> rule.
# NB: gaps between anchors are BOUNDED (.{0,N}?) — an unbounded `.+`/`.*` between
# word anchors backtracks catastrophically (ReDoS): a 73KB un-punctuated "if ..."
# paragraph hung claim-audit ~10s+ (found by stress test). Real claims are short.
_RULE = re.compile(
    r"(\b(always|never|must(?:\s+not)?|should(?:\s+not)?|shall|ought to|"
    r"avoid|ensure|require[ds]?|do not|don'?t|prefer\b.{0,60}?\bover\b|"
    r"only (?:ever|when)|rule:|policy:|convention:)\b)"
    r"|(\bif\b.{1,80}?\bthen\b)|(\bwhen\b.{1,80}?\b(?:do|use|run|prefer|avoid)\b)",
    re.I)

# Empirical / measured / dated / located -> observation (data).
_EVIDENCE = re.compile(
    r"(\b(measured|observed|recorded|logged|benchmarked|profiled|"
    r"ran\b.{0,60}?\b(?:and|got|returned|showed)|returned|reported|"
    r"passed|failed|errored|crashed|timed out|reproduc\w+|"
    r"lives? (?:at|in)|located (?:at|in)|defined (?:at|in)|found (?:at|in))\b)"
    r"|(\b\d+(?:\.\d+)?\s*(?:ms|s\b|sec|%|x\b|tokens?|lines?|tests?|cases?|"
    r"files?|bytes?|kb|mb|gb|commits?|times|iterations?))"
    r"|(\b(?:v|version\s*)\d+(?:\.\d+)+)"
    r"|(\b\d{4}-\d{2}-\d{2}\b)"
    r"|([\w./-]+\.(?:py|js|ts|md|sh|json|yaml|yml|toml)(?::\d+)?\b)",  # path/locator ref
    re.I)

# Subjective evaluation w/o measurement -> opinion.
_OPINION = re.compile(
    r"\b(cleaner|nicer|prettier|uglier?|ugly|elegan\w*|clunky|awkward|"
    r"beautiful|gross|messy|tasteful|gorgeous|hideous|"
    r"better|worse|best\b|nicest|feels (?:right|wrong|off|better|cleaner)|"
    r"i (?:like|love|hate|dislike|prefer)\b|more readable|less readable)\b",
    re.I)

# Causal/inference markers are NOT decision markers — guard the classic
# false positive ("the test failed BECAUSE the path was wrong" is an observation).
_CAUSAL = re.compile(r"\b(because|since|therefore|thus|hence|due to|so that|in order to)\b", re.I)


def _strip_noise(text: str) -> str:
    # drop fenced code + inline code + wikilink/markdown-link chrome so markers
    # in code examples / link labels don't trigger.
    text = re.sub(r"```.*?```", " ", text, flags=re.S)
    text = re.sub(r"`[^`]*`", " ", text)
    text = re.sub(r"\[\[[^\]]*\]\]", " ", text)
    return text


def grade_claim(text: str) -> dict:
    """Grade a single claim. Returns type/klass/flags/markers.

    Precedence is deliberate and tuned against test_claim_grade.py — the DOMINANT
    epistemic act wins, most-committal first, with hedging able to demote a soft
    decision/rule to a hypothesis:
      explicit-decision > rule > (hedge -> hypothesis) > observation > opinion > soft-decision
    """
    # Defensive: coerce non-str (a future in-process caller may hand int/bytes);
    # cap length — a "claim" is a sentence, markers appear early, and scanning a
    # 200KB blob is both wrong and a ReDoS surface. Both found by stress test.
    if not isinstance(text, str):
        text = "" if text is None else str(text)
    raw = text.strip()
    clean = _strip_noise(raw)[:2000]
    markers: list[str] = []

    # Mostly-non-alphabetic input (pure numbers/punctuation) is noise, not data —
    # abstain rather than grade it `observation` on a bare number match.
    letters = sum(c.isalpha() for c in raw)
    if raw and letters / len(raw) < 0.3:
        return {"type": "unknown", "klass": KLASS["unknown"],
                "has_evidence": False, "has_hedge": False, "markers": ["abstain:non-alpha"]}

    hedge = bool(_HEDGE.search(clean))
    evidence = bool(_EVIDENCE.search(clean))
    firm_decision = bool(_DECISION_FIRM.search(clean))
    soft_decision = bool(_DECISION_SOFT.search(clean))
    fp_taste = bool(_FP_TASTE.search(clean))
    rule = bool(_RULE.search(clean))
    opinion = bool(_OPINION.search(clean))

    if hedge:
        markers.append("hedge")
    if evidence:
        markers.append("evidence")

    def out(t: str) -> dict:
        return {"type": t, "klass": KLASS[t],
                "has_evidence": evidence, "has_hedge": hedge,
                "markers": markers}

    # 1. Firm decision (committed choice) — a hedge elsewhere cannot demote it.
    if firm_decision:
        markers.append("decision:firm")
        return out("decision")
    # 2. Hedged with no firm commitment -> hypothesis (tentative). Demotes a SOFT
    #    decision: "we MIGHT adopt X" is a hypothesis, not a decision.
    if hedge:
        markers.append("hypothesis")
        return out("hypothesis")
    # 3. Soft decision (tentative/future verb), no hedge -> decision.
    if soft_decision:
        markers.append("decision:soft")
        return out("decision")
    # 4. First-person taste ("I prefer X over Y") -> opinion, BEFORE the rule
    #    check so it beats the generic 'prefer ... over' directive.
    if fp_taste:
        markers.append("opinion:first-person")
        return out("opinion")
    # 5. Normative / conditional directive -> rule.
    if rule:
        markers.append("rule")
        return out("rule")
    # 6. Empirical / measured / dated -> observation. Causal markers do NOT
    #    make it a decision (false-positive guard). Evidence beats the bare
    #    imperative below ("Run took 4.2s" is an observation, not a directive).
    if evidence:
        markers.append("observation")
        return out("observation")
    # 7. Bare-imperative directive (no measurement) -> rule.
    if _IMPERATIVE.search(clean.lstrip()):
        markers.append("rule:imperative")
        return out("rule")
    # 8. Subjective evaluation w/o evidence -> opinion.
    if opinion:
        markers.append("opinion")
        return out("opinion")
    # 9. No epistemic marker fired -> ABSTAIN (unknown). Honest: do not force
    #    unmarked prose into a type. Downstream layers treat unknown as
    #    "not actionable" (no hard contradiction, not promoted).
    markers.append("abstain")
    return out("unknown")


_HEADING_RE = re.compile(r"^\s*#{1,6}\s")
_TABLE_RE = re.compile(r"^\s*\|")
_FRONTMATTER_KV_RE = re.compile(r"^\s*[A-Za-z_][\w\- ]{0,30}:\s*\S")


def _strip_frontmatter(text: str) -> str:
    # drop a leading YAML frontmatter block (--- ... ---) so its key: value lines
    # aren't graded as claims.
    m = re.match(r"^﻿?---\r?\n.*?\r?\n---\r?\n", text, flags=re.S)
    return text[m.end():] if m else text


def grade_text(text: str) -> dict:
    """Grade every sentence-ish span in a markdown block; return per-claim grades
    + a klass histogram. Skips non-claim chrome: YAML frontmatter, headings,
    table rows, and bare `key: value` lines (so a page's structure isn't graded
    as data)."""
    if not isinstance(text, str):
        text = "" if text is None else str(text)
    # cap body length so a pathological page doesn't make the page-level lenses
    # (claim-audit/maturity/contradict-scan/health) crawl — markers appear early,
    # and grade_claim already caps each span (review C7).
    body = _strip_frontmatter(text)[:200000]
    clean = _strip_noise(body)
    spans = re.split(r"(?<=[.!?])\s+|\n[-*]\s+|\n{2,}", clean)
    claims = []
    hist = {"data": 0, "directive": 0, "judgment": 0, "unclassified": 0}
    for s in spans:
        s = s.strip(" -*\t")
        if len(s) < 12:
            continue
        first_line = s.splitlines()[0] if s else s
        if _HEADING_RE.match(first_line) or _TABLE_RE.match(first_line):
            continue
        # bare frontmatter-style `key: value` with no sentence punctuation/space-y prose
        if _FRONTMATTER_KV_RE.match(s) and " " not in s.split(":", 1)[0] and len(s) < 60 and "." not in s:
            continue
        # not a claim: too short, or an enumeration fragment (a Title-Case
        # comma list like "Request, Success, Priority"). Grading these as data
        # would dishonestly inflate the histogram.
        if len(s.split()) < 5:
            continue
        caps_items = [x.strip() for x in s.split(",") if x.strip()]
        if len(caps_items) >= 3 and all(re.match(r"[A-Z][\w-]*$", x.split()[0]) for x in caps_items if x.split()):
            continue
        g = grade_claim(s)
        claims.append({"claim": s[:200], **{k: g[k] for k in ("type", "klass")}})
        hist[g["klass"]] += 1
    return {"claims": claims, "n": len(claims), "klass_histogram": hist}


def _main(argv=None) -> int:
    import argparse
    import json
    import sys
    ap = argparse.ArgumentParser(description="Grade a claim by epistemic type.")
    ap.add_argument("text", nargs="?", help="Claim text (or read stdin / --file).")
    ap.add_argument("--file", help="Grade every claim in a markdown/text file.")
    args = ap.parse_args(argv)
    if args.file:
        from pathlib import Path
        print(json.dumps(grade_text(Path(args.file).read_text(encoding="utf-8", errors="replace")), indent=1))
    else:
        text = args.text if args.text is not None else sys.stdin.read()
        print(json.dumps(grade_claim(text), indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
