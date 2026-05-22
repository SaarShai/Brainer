#!/usr/bin/env python3
"""Compound compression pipeline.

Stages:
  1. caveman-prose — regex rules drop filler, pleasantries, and articles that can be dropped.
  2. llmlingua-2  — token-level perplexity compression via small BERT scorer.
  3. prefix-report — identify cache-eligible static prefix (heuristic).
  4. structured-hint — append terse-output constraint.

Preserves: code blocks (```...```), inline code (`...`), URLs, paths (/x/y), numbers.

Usage: python3 pipeline.py <input.txt> [--rate 0.5]
"""
import argparse
import re
import sys
import warnings
warnings.filterwarnings("ignore")

import tiktoken

FILLER = r"\b(just|really|basically|actually|simply|please|kindly|essentially|literally|definitely|certainly|obviously|of course|in order to|in terms of|at the end of the day|needless to say|it is worth noting that|it should be noted that|as a matter of fact)\b"
PLEASANTRIES = r"\b(sure|certainly|of course|happy to help|I'd be happy to|feel free to|thanks for|thank you for|let me know if|hope this helps)\b[^.!?]*[.!?]?"
ARTICLES = r"\b(the|a|an)\s+"

CODE_FENCE = re.compile(r"```.*?```", re.DOTALL)
INLINE_CODE = re.compile(r"`[^`]+`")
URL = re.compile(r"https?://\S+")
PATH = re.compile(r"(?:\.{0,2}/[\w./\-]+|/[\w./\-]+)")

def protect(text):
    """Swap code/URLs/paths with placeholders; return (masked, mapping)."""
    mapping = {}
    def sub(m):
        key = f"XPROTECT{len(mapping)}XEND"
        mapping[key] = m.group(0)
        return key
    for pat in (CODE_FENCE, INLINE_CODE, URL, PATH):
        text = pat.sub(sub, text)
    return text, mapping

def unprotect(text, mapping):
    for k, v in mapping.items():
        text = text.replace(k, v)
    return text

def caveman_prose(text, drop_articles=True):
    masked, mapping = protect(text)
    masked = re.sub(PLEASANTRIES, "", masked, flags=re.IGNORECASE)
    masked = re.sub(FILLER, "", masked, flags=re.IGNORECASE)
    if drop_articles:
        masked = re.sub(ARTICLES, "", masked, flags=re.IGNORECASE)
    masked = re.sub(r"\s+", " ", masked)
    masked = re.sub(r"\s+([.,;:!?])", r"\1", masked)
    return unprotect(masked, mapping).strip()

def llmlingua_compress(text, rate=0.5):
    from llmlingua import PromptCompressor
    global _PC
    try:
        _PC
    except NameError:
        _PC = PromptCompressor(
            model_name="microsoft/llmlingua-2-bert-base-multilingual-cased-meetingbank",
            use_llmlingua2=True,
            device_map="cpu",
        )
    masked, mapping = protect(text)
    out = _PC.compress_prompt(masked, rate=rate, force_tokens=['\n', '.', '!', '?', ','])
    compressed = out.get("compressed_prompt", masked) if isinstance(out, dict) else masked
    return unprotect(compressed, mapping)

def detect_prefix(text):
    """Rough heuristic: count leading lines that look static (rules, schema, examples)."""
    lines = text.splitlines()
    cutoff = 0
    for i, ln in enumerate(lines):
        if re.search(r"\b(user|request|question|task|input)[:>]", ln, re.IGNORECASE):
            cutoff = i
            break
    return cutoff, len(lines)

def count_tokens(text, model="cl100k_base"):
    enc = tiktoken.get_encoding(model)
    return len(enc.encode(text))

def run_pipeline(text, rate=0.5, drop_articles=True, use_llmlingua=True):
    stages = []
    orig = count_tokens(text)
    stages.append(("original", text, orig, 1.0))

    s1 = caveman_prose(text, drop_articles=drop_articles)
    t1 = count_tokens(s1)
    stages.append(("caveman", s1, t1, t1/orig))

    if use_llmlingua:
        s2 = llmlingua_compress(s1, rate=rate)
        t2 = count_tokens(s2)
        stages.append(("+llmlingua", s2, t2, t2/orig))
    else:
        s2 = s1

    pfx_line, total_lines = detect_prefix(s2)
    cacheable_frac = pfx_line / total_lines if total_lines else 0
    stages.append(("+prefix-cache-savings", s2, int(t1*(1-cacheable_frac) + t1*cacheable_frac*0.1), None))
    # prefix cache = 90% discount on static prefix

    return stages

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("input", help="input file path or '-' for stdin")
    ap.add_argument("--rate", type=float, default=0.5, help="llmlingua keep rate (lower=more compression)")
    ap.add_argument("--no-articles", action="store_true", help="keep articles")
    ap.add_argument("--no-llmlingua", action="store_true", help="skip llmlingua")
    ap.add_argument("--show", action="store_true", help="print compressed output")
    args = ap.parse_args()

    text = sys.stdin.read() if args.input == "-" else open(args.input).read()

    stages = run_pipeline(text, rate=args.rate,
                          drop_articles=not args.no_articles,
                          use_llmlingua=not args.no_llmlingua)

    print(f"\n{'stage':<28} {'tokens':>8} {'ratio':>8} {'cum-savings':>12}")
    print("-" * 62)
    base = stages[0][2]
    for name, out, tok, ratio in stages:
        r = f"{tok/base:.2%}" if ratio is not None else "—"
        sav = f"{1-tok/base:.2%}" if ratio is not None else "—"
        print(f"{name:<28} {tok:>8} {r:>8} {sav:>12}")

    if args.show:
        print("\n--- compressed output ---")
        print(stages[-2][1] if len(stages) >= 2 else stages[-1][1])

if __name__ == "__main__":
    main()
