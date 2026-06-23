#!/usr/bin/env python3
"""Plain-python tests (no pytest dep) for gen_hooks_map.installer_events.
Exit code = verdict. Regression guard for the bug where ensure()-wired events
(PreCompact/SessionEnd) were dropped because only hooks.setdefault was matched.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import gen_hooks_map as g

FAILS: list[str] = []


def check(name, got, want):
    if got != want:
        FAILS.append(f"{name}: got {got!r} want {want!r}")
        print(f"  [FAIL] {name}: got {got!r} want {want!r}")
    else:
        print(f"  [PASS] {name}")


def main() -> int:
    # 1. the exact bug: ensure() + setdefault must BOTH be captured (context-keeper shape)
    ck = 'ensure("PreCompact", hook_cmd)\nensure("SessionEnd", archive_cmd)\nrules = hooks.setdefault("Stop", [])\n'
    check("context-keeper shape", g.installer_events(ck), ["PreCompact", "SessionEnd", "Stop"])

    # 2. setdefault-only installers unchanged (compliance-canary / prompt-triage)
    check("setdefault only", g.installer_events('hooks.setdefault("UserPromptSubmit", [])'), ["UserPromptSubmit"])

    # 3. non-event string args are filtered out (intersect with HOOK_EVENTS)
    check("non-event filtered", g.installer_events('ensure("hooks", x)\nensure("Stop", y)'), ["Stop"])

    # 4. no wiring -> empty (falls back to broad scan in caller; e.g. brainer-audit)
    check("no wiring", g.installer_events('echo "no hooks here"'), [])

    # 5. live inventory: context-keeper reports its full event set, not just Stop
    rows = {r["skill"]: r for r in g.skill_hook_inventory()}
    if "context-keeper" not in rows:
        FAILS.append("context-keeper not in inventory")
        print("  [FAIL] context-keeper not in inventory")
    else:
        evs = rows["context-keeper"]["events"]
        for want in ("PreCompact", "SessionEnd", "Stop"):
            check(f"live context-keeper has {want}", want in evs, True)

    print()
    if FAILS:
        print(f"FAILED: {len(FAILS)}")
        for x in FAILS:
            print("  -", x)
        return 1
    print("ALL PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
