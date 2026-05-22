"""Skip-detector heuristics for content types where compression damages quality.

Written directly after qwen3.5:35b failed on atomic code tasks (empty outputs).
These extend skip_detector.py with pattern-specific gates informed by
adversarial bench failures: version-string comparisons, temporal shifts,
unit puns, code content, dense numeric comparisons.
"""
from __future__ import annotations
import re


_VER_RE = re.compile(r"\b\d+\.\d+(?:\.\d+){1,3}\b")

def has_version_comparison(text: str) -> bool:
    return len(_VER_RE.findall(text)) >= 2


_DAYS = r"Mon|Tue(?:sday)?|Wed(?:nesday)?|Thu(?:rsday)?|Fri(?:day)?|Sat(?:urday)?|Sun(?:day)?|Monday"
_MONTHS = r"Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec"
_TEMPORAL_PATTERNS = [
    re.compile(r"\b(?:moved|changed|extended|shifted|postponed|rescheduled)\s+from\s+\S.+?\s+to\s+\S", re.I),
    re.compile(rf"\bfrom\s+({_DAYS})\s+to\s+({_DAYS})\b", re.I),
    re.compile(rf"\bfrom\s+({_MONTHS})\w*\s+to\s+({_MONTHS})", re.I),
    re.compile(r"\bwas\s+[\w\s]{1,30}\s+(?:now|currently)\b", re.I),
    re.compile(r"\b(?:originally|previously)\s+[\w\s]{1,30}\s+(?:now|currently)\b", re.I),
]

def is_temporal_comparative(text: str) -> bool:
    return any(p.search(text) for p in _TEMPORAL_PATTERNS)


_NUM_UNIT_RE = re.compile(
    r"\b(\d+(?:\.\d+)?)\s*("
    r"gallons?|gal|liters?|l|miles?|mi|km|kilometers?|feet|ft|inches?|in|meters?|m|cm|mm"
    r"|kg|kilograms?|pounds?|lb|lbs|ounces?|oz|grams?|g"
    r"|USD|EUR|GBP|\$|€|£"
    r"|hours?|minutes?|seconds?|days?|weeks?|months?|years?"
    r")\b",
    re.I,
)

def has_unit_comparison(text: str) -> bool:
    if len(_NUM_UNIT_RE.findall(text)) < 2: return False
    sentences = re.split(r"[.!?]\s+", text)
    return any(len(_NUM_UNIT_RE.findall(s)) >= 2 for s in sentences)


def numeric_density(text: str) -> float:
    total = len([c for c in text if not c.isspace()])
    if total == 0: return 0.0
    return len([c for c in text if c.isdigit()]) / total


_CODE_FENCE = re.compile(r"```[\s\S]*?```")
_CODE_KEYWORDS = re.compile(
    r"\b(def|class|function|import|return|const|let|var|struct|impl|fn|async|await|try|catch|if|else|for|while)\b"
)

def looks_like_code(text: str) -> bool:
    if _CODE_FENCE.search(text): return True
    kw_hits = len(_CODE_KEYWORDS.findall(text))
    words = max(len(re.findall(r"\w+", text)), 1)
    if kw_hits / words > 0.08: return True
    lines = text.splitlines()
    if len(lines) >= 3:
        indented = sum(1 for ln in lines if ln.startswith("    ") or ln.startswith("\t"))
        if indented / len(lines) > 0.3: return True
    brack = sum(text.count(c) for c in "{}[]();")
    if brack / max(len(text), 1) > 0.02: return True
    return False


def extended_skip_reasons(text: str) -> list[str]:
    reasons = []
    if has_version_comparison(text): reasons.append("version-comparison")
    if is_temporal_comparative(text): reasons.append("temporal-shift")
    if has_unit_comparison(text): reasons.append("unit-pun-risk")
    if looks_like_code(text): reasons.append("code-content")
    if numeric_density(text) > 0.08: reasons.append("high-numeric-density")
    return reasons


def should_compress_extended(text: str) -> dict:
    reasons = extended_skip_reasons(text)
    return {"skip": bool(reasons), "reason": ", ".join(reasons) if reasons else ""}
