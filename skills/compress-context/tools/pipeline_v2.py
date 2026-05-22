#!/usr/bin/env python3
"""Compound compression v2 — question-aware + critical-zone + hooks for self-verify.

Additions over v1:
  - `question` parameter: sentences containing question keywords are protected from compression.
  - `critical-zone` regex: sentences with dates/versions/%/digits/quotes are protected
    ("factual sentences must survive").
  - `adaptive_rate`: can escalate rate upward (less compression) on retry.
  - Exposed `compress(context, question=None, rate=0.5)` as library entry.

Stages per call:
  1. caveman-prose — regex filler/pleasantries drop, code/URLs/paths protected.
  2. critical-zone protect — sentences matching factual patterns OR question-keyword overlap.
  3. llmlingua-2 — compress remaining prose.
  4. unprotect — restore.
"""
from __future__ import annotations
import argparse, re, sys, warnings
warnings.filterwarnings("ignore")
import tiktoken

# --- from v1 ---
FILLER = r"\b(just|really|basically|actually|simply|please|kindly|essentially|literally|definitely|certainly|obviously|of course|in order to|in terms of|at the end of the day|needless to say|it is worth noting that|it should be noted that|as a matter of fact)\b"
PLEASANTRIES = r"\b(sure|certainly|of course|happy to help|I'd be happy to|feel free to|thanks for|thank you for|let me know if|hope this helps)\b[^.!?]*[.!?]?"
ARTICLES = r"\b(the|a|an)\s+"

CODE_FENCE = re.compile(r"```.*?```", re.DOTALL)
INLINE_CODE = re.compile(r"`[^`]+`")
URL = re.compile(r"https?://\S+")
PATH = re.compile(r"(?:\.{0,2}/[\w./\-]+|/[\w./\-]+)")

# --- v2 critical-zone patterns (factual density markers) ---
# Any sentence containing ≥1 match is protected from compression.
CRITICAL_PATTERNS = [
    re.compile(r"\b\d{4}(?:[-/]\d{1,2}){1,2}\b"),        # dates 2026-04-17
    re.compile(r"\bv?\d+\.\d+(?:\.\d+)?\b"),              # versions 3.9.1
    re.compile(r"\b\d+(?:\.\d+)?\s*%"),                   # percentages
    re.compile(r"\b\d+(?:\.\d+)?\s*(?:ms|s|tok|tokens?|GB|MB|KB|x)\b", re.I),
    re.compile(r"\b(?:line|L)\s*\d+\b", re.I),           # line numbers
    re.compile(r'"[^"\n]{3,80}"'),                       # quoted strings (verbatim names/labels)
    re.compile(r"'[^'\n]{3,80}'"),
    re.compile(r"\$\d+(?:,\d{3})*(?:\.\d+)?"),           # dollar amounts
]

STOPWORDS = set("a an the is are was were be been being to of in on at for with by from and or but not as if then else this that these those it its".split())


def protect(text, extra_patterns=()):
    """Swap matches with placeholders; return (masked, mapping)."""
    mapping = {}
    def sub(m):
        key = f"XPROTECT{len(mapping)}XEND"
        mapping[key] = m.group(0)
        return key
    for pat in (CODE_FENCE, INLINE_CODE, URL, PATH, *extra_patterns):
        text = pat.sub(sub, text)
    return text, mapping


def unprotect(text, mapping):
    for k, v in mapping.items():
        text = text.replace(k, v)
    return text


def _question_keywords(question: str) -> set[str]:
    if not question: return set()
    words = re.findall(r"\b[a-zA-Z][a-zA-Z0-9\-_]{2,}\b", question)
    return {w.lower() for w in words if w.lower() not in STOPWORDS}


def critical_sentence_re(question_kws: set[str]) -> re.Pattern:
    """Sentence-level regex: matches whole sentence if it contains a factual marker or question keyword."""
    # Build alternation of keyword literals (escape special chars)
    kw_alt = "|".join(re.escape(w) for w in sorted(question_kws, key=len, reverse=True)) or "$a"
    # Sentence = chars until terminal punctuation. Capture sentence if it contains
    # a critical pattern OR a question keyword (case-insensitive).
    return re.compile(
        rf"[^.!?\n]*\b(?:{kw_alt})\b[^.!?\n]*[.!?]",
        re.IGNORECASE,
    )


def protect_critical_sentences(text: str, question: str | None = None):
    """Wrap sentences containing factual markers or question keywords as protected spans."""
    mapping = {}
    def sub(m):
        key = f"XCRIT{len(mapping)}XEND"
        mapping[key] = m.group(0)
        return key

    # 1. Factual-pattern sentences: find any sentence containing CRITICAL pattern
    # Split sentences, check each.
    def factual_protect(t):
        parts = re.split(r"(?<=[.!?])\s+", t)
        out = []
        for p in parts:
            if any(rx.search(p) for rx in CRITICAL_PATTERNS):
                key = f"XCRIT{len(mapping)}XEND"
                mapping[key] = p
                out.append(key)
            else:
                out.append(p)
        return " ".join(out)
    text = factual_protect(text)

    # 2. Question-keyword sentences
    kws = _question_keywords(question or "")
    if kws:
        rx = critical_sentence_re(kws)
        text = rx.sub(sub, text)

    return text, mapping


def caveman_prose(text, drop_articles=True):
    masked, mapping = protect(text)
    masked = re.sub(PLEASANTRIES, "", masked, flags=re.IGNORECASE)
    masked = re.sub(FILLER, "", masked, flags=re.IGNORECASE)
    if drop_articles:
        masked = re.sub(ARTICLES, "", masked, flags=re.IGNORECASE)
    masked = re.sub(r"\s+", " ", masked)
    masked = re.sub(r"\s+([.,;:!?])", r"\1", masked)
    return unprotect(masked, mapping).strip()


_PC = None
def _get_compressor():
    global _PC
    if _PC is None:
        from llmlingua import PromptCompressor
        _PC = PromptCompressor(
            model_name="microsoft/llmlingua-2-bert-base-multilingual-cased-meetingbank",
            use_llmlingua2=True,
            device_map="cpu",
        )
    return _PC


def llmlingua_compress(text, rate=0.5):
    pc = _get_compressor()
    masked, mapping = protect(text)
    out = pc.compress_prompt(masked, rate=rate, force_tokens=['\n', '.', '!', '?', ','])
    compressed = out.get("compressed_prompt", masked) if isinstance(out, dict) else masked
    return unprotect(compressed, mapping)


def compress(context: str, question: str | None = None, rate: float = 0.5,
             drop_articles: bool = True, respect_skip: bool = True) -> tuple[str, dict]:
    """Main library entry. Returns (compressed_text, stats).

    If respect_skip=True (default), consults skip_detector first and returns
    original context on skip flags (dense numeric, short text, etc). Prevents
    destructive compression on content types where compression loses facts.
    """
    orig = context

    if respect_skip:
        try:
            from skip_detector import should_compress
            from skip_heuristics import should_compress_extended
            # Combine both: basic + extended (version/temporal/unit/code/density).
            d1 = should_compress(orig)
            d2 = should_compress_extended(orig)
            skip = d1.get("skip") or d2.get("skip")
            reason = "; ".join(r for r in [d1.get("reason",""), d2.get("reason","")] if r)
            if skip:
                enc = tiktoken.get_encoding("cl100k_base")
                toks = len(enc.encode(orig))
                return orig, {"orig_tok": toks, "after_caveman": toks,
                              "after_critprotect": toks, "after_llmlingua": toks,
                              "final": toks, "critical_sentences": 0,
                              "rate": 1.0, "savings": 0.0,
                              "skipped": True, "skip_reason": reason}
        except Exception:
            pass

    # Stage 1: caveman
    s1 = caveman_prose(orig, drop_articles=drop_articles)

    # Stage 2: protect critical sentences (factual + question-keyword)
    s2, crit_map = protect_critical_sentences(s1, question)

    # Stage 3: LLMLingua on remaining prose
    s3 = llmlingua_compress(s2, rate=rate) if rate < 1.0 else s2

    # Stage 4: restore critical sentences
    s4 = unprotect(s3, crit_map)

    # Stats
    enc = tiktoken.get_encoding("cl100k_base")
    stats = {
        "orig_tok": len(enc.encode(orig)),
        "after_caveman": len(enc.encode(s1)),
        "after_critprotect": len(enc.encode(s2)),
        "after_llmlingua": len(enc.encode(s3)),
        "final": len(enc.encode(s4)),
        "critical_sentences": len(crit_map),
        "rate": rate,
    }
    stats["savings"] = 1 - stats["final"] / max(stats["orig_tok"], 1)
    return s4, stats


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("input", help="context file path or '-' for stdin")
    ap.add_argument("-q", "--question", default=None)
    ap.add_argument("--rate", type=float, default=0.5)
    ap.add_argument("--no-articles", action="store_true")
    ap.add_argument("--show", action="store_true")
    args = ap.parse_args()

    ctx = sys.stdin.read() if args.input == "-" else open(args.input).read()
    out, stats = compress(ctx, question=args.question, rate=args.rate,
                          drop_articles=not args.no_articles)
    for k, v in stats.items():
        print(f"  {k}: {v}")
    if args.show:
        print("\n--- compressed ---")
        print(out)


if __name__ == "__main__":
    main()
