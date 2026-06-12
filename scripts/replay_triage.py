#!/usr/bin/env python3
"""Replay every prompt that historically received a triage directive through
the CURRENT classifier. The regression direction that matters: a directive the
main model had to override costs more than silence, so each code change should
monotonically shrink (or hold) the set of still-routed prompts — and must never
re-introduce local-model targets, sub-0.7-confidence emissions, or length-gate
bypasses.

Usage: python3 scripts/replay_triage.py [transcript_glob]
Exit 0 = no violations; 1 = violations found.
"""
from __future__ import annotations
import glob, json, os, sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "skills", "prompt-triage", "tools"))
os.environ.setdefault("AGENTS_TRIAGE_NO_OLLAMA", "1")  # deterministic by default
from classify import emit_context  # noqa: E402

DEFAULT_GLOB = os.path.expanduser(
    "~/.claude/projects/-Users-za-Documents-Brainer/*.jsonl")


def historically_triaged_prompts(pattern: str) -> list[str]:
    prompts: list[str] = []
    for f in glob.glob(pattern):
        pending = None
        for line in open(f, errors="replace"):
            try:
                d = json.loads(line)
            except Exception:
                continue
            if d.get("type") == "user":
                c = d.get("message", {}).get("content")
                if isinstance(c, str) and "[agents-triage]" not in c:
                    pending = c
            if pending and "[agents-triage]" in json.dumps(d):
                prompts.append(pending)
                pending = None
    return prompts


def main() -> int:
    pattern = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_GLOB
    prompts = historically_triaged_prompts(pattern)
    emitted, violations = [], []
    for p in prompts:
        d = emit_context(p, use_ollama_fallback=False)
        if not d:
            continue
        emitted.append(p)
        r = json.loads(d.splitlines()[1])
        if r.get("model", "").startswith("local:") or r.get("agent") == "local-ollama":
            violations.append(("local-model", p[:80], r))
        if float(r.get("confidence", 0)) < 0.7:
            violations.append(("low-confidence", p[:80], r))
        if len(p) > 1500:
            violations.append(("length-gate-bypass", len(p), r))
    print(f"replayed {len(prompts)} historically-triaged prompts: "
          f"{len(emitted)} still routed, {len(prompts) - len(emitted)} silent, "
          f"{len(violations)} violations")
    for p in emitted:
        print(f"  still-routed: {p[:90]!r}")
    for v in violations:
        print(f"  VIOLATION: {v}")
    return 1 if violations else 0


if __name__ == "__main__":
    sys.exit(main())
