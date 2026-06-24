#!/usr/bin/env python3
"""compliance-canary UserPromptSubmit hook — the single drift watcher.

Two ORTHOGONAL anti-drift mechanisms in ONE hook process (skill-pulse was
folded in here 2026-06-16 — one reactive hook instead of two, the leaner
target the eval notes had flagged):

  1. SYMPTOMATIC probes (every turn) — detect per-skill drift symptoms in
     recent assistant messages / tool results and inject a targeted,
     evidence-quoting corrective. Silent until a symptom shows.
  2. PERIODIC re-anchor (every Nth turn) — unconditionally re-state the
     active skills' rules before they fade from attention. Paper-calibrated
     cadence (arXiv 2510.07777). Covers rules that have NO symptom probe.

One process, one dir-walk, one transcript read, one state file, one injected
<system-reminder>. The re-anchor YIELDS to fired probes on a shared turn
(symptom correction is higher-signal and itself re-anchors) — a single global
budget, so the two mechanisms never double-nag.

Per-skill probes are declared in `<.claude/skills>/<name>/drift_probes.json`:

  [
    {"kind": "forbidden_regex", "pattern": "(?i)\\b(certainly|absolutely)\\b",
     "id": "filler", "severity": "warn"},
    {"kind": "word_count_per_message", "threshold": 80, "window": 3,
     "id": "creep",
     "warrant_pattern": r"(?i)\b(explain|elaborate|detail|in[ -]?depth|deep[ -]?dive|walk me through|comprehensive|thorough(ly)?|step[ -]by[ -]step|summar(y|ize|ise)|overview|report|break ?down|compare|pros and cons|brainstorm|think (of|about|through)|tell me (what|how|why|about|everything)|list( me)? (\d|at least|the|all|every)|\d+ (ways|ideas|options|reasons|examples|things)|why (does|do|is|are|did))\b"},
    {"kind": "claim_without_evidence",
     "claim_pattern": "(?i)\\b(done|fixed|passes)\\b",
     "verify_tools": ["Bash"],
     "verify_keywords": ["test", "pytest", "make", "build", "check"]}
  ]

Anti-spam: each probe's last-fire turn is tracked; same probe won't
re-fire within COOLDOWN_TURNS of its last trigger.

Contract: always exit 0. A failing UserPromptSubmit hook would stall
the user.
"""
from __future__ import annotations

import fcntl
import hashlib
import json
import os
import re
import signal
import sys
import time
from contextlib import contextmanager
from pathlib import Path


COOLDOWN_TURNS_DEFAULT = 3
MSG_WINDOW_DEFAULT = 3            # number of recent assistant messages to scan
TRANSCRIPT_LINE_CAP = 400         # max trailing lines read from transcript
MAX_PROBES_TRIGGERED = 4          # cap symptomatic payload
GC_AGE_SECONDS = 7 * 24 * 3600
GC_SCAN_MAX = 500

# Periodic re-anchor (absorbed skill-pulse). Cadence is paper-calibrated:
# arXiv 2510.07777 tested reminder injections at turns 4 + 7 of 10-turn convos.
CADENCE_DEFAULT = 4
CADENCE_FLOOR = 2                 # a cadence below 2 re-anchors every turn — noise
MAX_SKILLS_IN_PULSE = 8          # cap re-anchor payload
MAX_REMINDER_CHARS = 280         # cap one re-anchor line (a runaway pulse_reminder)

# Hard wall-clock budget for the probe phase. drift_probes.json regexes are
# author-supplied; a catastrophic-backtracking pattern (e.g. `(a+)+$`) would
# otherwise wedge the user's prompt — and this is the single mandatory drift
# hook, so a wedge is the worst failure. A length cap does NOT help exponential
# backtracking; only a timeout does. On budget exceed we emit nothing and exit 0
# (the always-exit-0 contract holds; the regex just doesn't run this turn).
PROBE_TIMEOUT_SECONDS = 1.5

# Strip fenced + inline code from assistant text before running detectors —
# otherwise a literal string like `print("Certainly!")` triggers caveman's
# filler regex. Detectors should fire on the model's *prose*, not on code
# the model is quoting.
_CODE_BLOCK_RE = re.compile(r"```[\s\S]*?```")
_INLINE_CODE_RE = re.compile(r"`[^`\n]+`")


def strip_code(text: str) -> str:
    text = _CODE_BLOCK_RE.sub(" ", text)
    text = _INLINE_CODE_RE.sub(" ", text)
    return text


def _as_int(value, default: int = 0) -> int:
    """Coerce a persisted/state value to int without ever raising — a corrupted
    or null field must NOT crash the hook (the always-exit-0 contract)."""
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def log_err(msg: str) -> None:
    ts = time.strftime("%FT%TZ", time.gmtime())
    sys.stderr.write(f"{ts} compliance-canary: {msg}\n")


def state_dir() -> Path:
    override = os.environ.get("COMPLIANCE_CANARY_STATE_DIR")
    if override:
        return Path(override)
    # Anchor to CLAUDE_PROJECT_DIR — process cwd isn't stable across hook
    # invocations, and a cwd-relative path silently fragments per-session
    # state across directories the agent has cd'd into.
    project = os.environ.get("CLAUDE_PROJECT_DIR")
    base = Path(project) if project else Path.cwd()
    return base / ".brainer" / "compliance-canary"


def state_path(session_id: str) -> Path:
    # 16-hex SHA prefix: collision-safe even when distinct sessions share the
    # same 8-char id prefix (previous bug — overwrote each other's state).
    sid = session_id or "unknown"
    sid_hash = hashlib.sha256(sid.encode("utf-8", errors="replace")).hexdigest()[:16]
    return state_dir() / f"{sid_hash}.json"


def skills_root() -> Path:
    # SKILL_PULSE_SKILLS_ROOT honored as a back-compat alias (skill-pulse merged
    # into this hook 2026-06-16).
    override = (os.environ.get("COMPLIANCE_CANARY_SKILLS_ROOT")
                or os.environ.get("SKILL_PULSE_SKILLS_ROOT"))
    if override:
        return Path(override)
    return Path(".claude/skills")


@contextmanager
def state_lock(path: Path):
    lock_path = path.with_suffix(path.suffix + ".lock")
    fh = None
    # Setup (mkdir/open/flock) is best-effort: on failure we log and proceed
    # lockless rather than blocking the user's prompt. This is a SEPARATE try
    # from the yield — a body exception must propagate cleanly, not be caught
    # here (which would double-yield and corrupt the generator protocol,
    # raising RuntimeError and breaking the always-exit-0 contract).
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        fh = open(lock_path, "a+")
        try:
            fcntl.flock(fh.fileno(), fcntl.LOCK_EX)
        except (OSError, AttributeError) as e:
            log_err(f"lock-skip path={lock_path} err={e!r}")
    except Exception as e:
        log_err(f"lock-open-fail path={lock_path} err={e!r}")
        if fh is not None:
            try:
                fh.close()
            except Exception:
                pass
            fh = None
    try:
        yield
    finally:
        if fh is not None:
            try:
                fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
            except Exception:
                pass
            fh.close()


def load_state(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    except Exception as e:
        log_err(f"state-read-fail path={path} err={e!r}")
        return {}


def save_state(path: Path, state: dict) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")
    except Exception as e:
        log_err(f"state-write-fail path={path} err={e!r}")


def gc_old_state(dir_path: Path, now: float) -> int:
    if not dir_path.is_dir():
        return 0
    removed = 0
    try:
        with os.scandir(dir_path) as it:
            for i, entry in enumerate(it):
                if i >= GC_SCAN_MAX:
                    break
                if not entry.is_file():
                    continue
                if not (entry.name.endswith(".json") or entry.name.endswith(".json.lock")):
                    continue
                try:
                    if now - entry.stat().st_mtime > GC_AGE_SECONDS:
                        os.unlink(entry.path)
                        removed += 1
                except OSError:
                    pass
    except OSError as e:
        log_err(f"gc-scandir-fail dir={dir_path} err={e!r}")
    return removed


# -------------------------- probe discovery --------------------------------

def discover_probes(root: Path) -> list[dict]:
    """Walk .claude/skills/*/drift_probes.json. Each probe dict gets
    `_skill` and `_probe_id` fields injected for later display + suppression."""
    if not root.is_dir():
        return []
    out: list[dict] = []
    try:
        for entry in sorted(root.iterdir()):
            if not entry.is_dir():
                continue
            probes_file = entry / "drift_probes.json"
            if not probes_file.is_file():
                continue
            try:
                data = json.loads(probes_file.read_text(encoding="utf-8"))
            except Exception as e:
                log_err(f"probes-parse-fail path={probes_file} err={e!r}")
                continue
            if not isinstance(data, list):
                log_err(f"probes-not-list path={probes_file}")
                continue
            for i, probe in enumerate(data):
                if not isinstance(probe, dict):
                    continue
                pid = probe.get("id") or probe.get("kind", f"p{i}")
                probe["_skill"] = entry.name
                probe["_probe_id"] = f"{entry.name}:{pid}"
                out.append(probe)
    except OSError as e:
        log_err(f"discover-fail root={root} err={e!r}")
    return out


# -------------------------- periodic re-anchor (absorbed skill-pulse) -------
# The probes above are SYMPTOMATIC. This second mechanism is UNCONDITIONAL: on
# every Nth turn it re-states the active skills' `pulse_reminder:` rules so they
# stay in effective attention. Curated, not noisy — a skill participates only if
# its frontmatter declares `pulse_reminder:` (or it's force-listed via env).

# `﻿?` tolerates a UTF-8 BOM before the opening fence — without it a
# BOM-prefixed SKILL.md silently yields {} and the skill drops from the
# re-anchor (the fix-one-copy-not-the-sibling divergence class).
_FRONTMATTER_RE = re.compile(r"^﻿?---\s*\n(.*?)\n---\s*\n", re.DOTALL)


def parse_frontmatter(text: str) -> dict:
    """Minimal `key: value` frontmatter parser (no PyYAML dep). Handles plain
    and quoted scalars — all this catalog's SKILL.md files use."""
    m = _FRONTMATTER_RE.match(text)
    if not m:
        return {}
    out: dict = {}
    for raw in m.group(1).splitlines():
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        if ":" not in raw:
            continue
        key, _, val = raw.partition(":")
        key = key.strip()
        val = val.strip()
        if len(val) >= 2 and val[0] == val[-1] and val[0] in ('"', "'"):
            val = val[1:-1]
        out[key] = val
    return out


def first_sentence(text: str) -> str:
    if not text:
        return ""
    # Split on sentence-final punctuation + space so decimals / "e.g." survive.
    parts = re.split(r"(?<=[.!?])\s+", text.strip(), maxsplit=1)
    return parts[0].rstrip(".") if parts else text.strip()


def discover_pulse_skills(root: Path, allowlist: set[str]) -> list[tuple[str, str]]:
    """[(name, reminder), ...] for skills to re-anchor. Included iff frontmatter
    has `pulse_reminder:`, OR the skill is named in `allowlist` (then fall back
    to the first sentence of `description`). Deduped by the `name:` field."""
    if not root.is_dir():
        return []
    seen: set[str] = set()
    out: list[tuple[str, str]] = []
    try:
        for entry in sorted(root.iterdir()):
            if not entry.is_dir():
                continue
            skill_md = entry / "SKILL.md"
            if not skill_md.is_file():
                continue
            try:
                text = skill_md.read_text(encoding="utf-8", errors="replace")
            except OSError as e:
                log_err(f"skill-read-fail path={skill_md} err={e!r}")
                continue
            fm = parse_frontmatter(text)
            name = fm.get("name") or entry.name
            if name in seen:
                continue
            reminder = fm.get("pulse_reminder")
            if reminder:
                out.append((name, reminder))
                seen.add(name)
                continue
            if name in allowlist:
                hint = first_sentence(fm.get("description", ""))
                if hint:
                    out.append((name, hint))
                    seen.add(name)
    except OSError as e:
        log_err(f"discover-pulse-fail root={root} err={e!r}")
    return out[:MAX_SKILLS_IN_PULSE]


# -------------------------- transcript reading ------------------------------

def read_transcript_tail(path: str, cap: int = TRANSCRIPT_LINE_CAP) -> list[dict]:
    """Return up to `cap` most-recent parseable JSONL events from the transcript.

    TWIN: context-keeper/tools/extract.py:iter_events shares the same
    malformed-line guard — keep both in sync. (This copy byte-tails + caps for a
    hot per-prompt path; the twin streams the whole file for a cold PreCompact.)"""
    if not path:
        return []
    p = Path(path)
    if not p.is_file():
        return []
    # Byte-tail read (codex round-3): readlines() loaded the WHOLE transcript
    # on every hook fire — O(file) memory on a hot path. Seek to the last
    # TAIL_BYTES instead; transcripts only grow, the cap only needs the tail.
    TAIL_BYTES = 8_000_000
    try:
        size = p.stat().st_size
        with open(p, "rb") as f:
            if size > TAIL_BYTES:
                f.seek(size - TAIL_BYTES)
                f.readline()  # drop the partial line at the seek point
            raw = f.read().decode("utf-8", errors="replace")
    except OSError as e:
        log_err(f"transcript-read-fail path={path} err={e!r}")
        return []
    events: list[dict] = []
    for line in raw.splitlines()[-cap:]:
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        # Parseable-but-malformed guard (codex round-3): a line like `123` or
        # {"message": "bad"} crashed detectors via .get() on non-dicts —
        # violating the always-exit-0 contract. Normalize here, once.
        if not isinstance(obj, dict):
            continue
        if "message" in obj and not isinstance(obj["message"], dict):
            obj["message"] = {}
        events.append(obj)
    return events


def recent_assistant_messages(events: list[dict], n: int) -> list[dict]:
    """Return up to n most-recent assistant text-content messages, oldest-first.
    Each: {"text": "...", "uuid": "...", "timestamp": "..."}."""
    out: list[dict] = []
    for e in reversed(events):
        if e.get("type") != "assistant":
            continue
        msg = e.get("message") or {}
        content = msg.get("content") or []
        if not isinstance(content, list):
            continue
        text_chunks = [b.get("text", "") for b in content if isinstance(b, dict) and b.get("type") == "text"]
        if not text_chunks:
            continue
        joined = "\n".join(text_chunks)
        out.append({
            "text": strip_code(joined),
            "raw_text": joined,
            "uuid": e.get("uuid", ""),
            "timestamp": e.get("timestamp", ""),
        })
        if len(out) >= n:
            break
    out.reverse()
    return out


def recent_tool_uses(events: list[dict], n: int = 10) -> list[dict]:
    """Return up to n most-recent tool_use blocks, oldest-first.
    Each: {"name": "Bash", "input": {...}}."""
    out: list[dict] = []
    for e in reversed(events):
        if e.get("type") != "assistant":
            continue
        msg = e.get("message") or {}
        for b in (msg.get("content") or [])[::-1]:
            if isinstance(b, dict) and b.get("type") == "tool_use":
                out.append({"name": b.get("name", ""), "input": b.get("input") or {}})
                if len(out) >= n:
                    break
        if len(out) >= n:
            break
    out.reverse()
    return out


def final_assistant_has_tool_use(events: list[dict]) -> bool:
    """True iff the MOST-RECENT assistant event contained a tool_use block.
    Used by the early_stop detector: a closing turn that called a tool DID work
    (no early stop); a closing turn that was pure prose may be a narrate-then-
    yield. Looks only at the last assistant event (the agent's final message)."""
    for e in reversed(events):
        if e.get("type") != "assistant":
            continue
        msg = e.get("message") or {}
        content = msg.get("content")
        if not isinstance(content, list):
            return False
        return any(isinstance(b, dict) and b.get("type") == "tool_use" for b in content)
    return False


def _tool_result_text(content) -> str:
    """tool_result content is a string OR a list of blocks ({type:text,...});
    stringifying the list literal makes regexes brittle (codex review
    2026-06-12) — join the text fields instead."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for c in content:
            if isinstance(c, dict):
                parts.append(str(c.get("text") or c.get("content") or ""))
            else:
                parts.append(str(c))
        return " ".join(p for p in parts if p)
    return str(content or "")


def recent_tool_errors(events: list[dict], n: int = 30) -> list[str]:
    """Return up to n most-recent is_error tool_result texts, oldest-first.
    Tool errors live in user-type events (content blocks {type: tool_result,
    is_error: true}) — invisible to the assistant-message detectors above."""
    out: list[str] = []
    for e in reversed(events):
        if e.get("type") != "user":
            continue
        msg = e.get("message") or {}
        content = msg.get("content")
        if not isinstance(content, list):
            continue
        for b in content[::-1]:
            if isinstance(b, dict) and b.get("type") == "tool_result" and b.get("is_error"):
                out.append(_tool_result_text(b.get("content"))[:400])
                if len(out) >= n:
                    break
        if len(out) >= n:
            break
    out.reverse()
    return out


# -------------------------- detectors --------------------------------------

def detect_forbidden_regex(probe: dict, messages: list[dict], _tool_uses, _tool_errors=None, user_prompt: str = "", traj_stats: dict | None = None) -> dict | None:
    pat_str = probe.get("pattern")
    if not pat_str:
        return None
    try:
        pat = re.compile(pat_str)
    except re.error as e:
        log_err(f"bad-regex probe={probe.get('_probe_id')} err={e!r}")
        return None
    unless = None
    unless_str = probe.get("unless_pattern")
    if unless_str:
        try:
            unless = re.compile(unless_str)
        except re.error as e:
            log_err(f"bad-unless-regex probe={probe.get('_probe_id')} err={e!r}")
    for m in messages:
        match = pat.search(m["text"])
        if match:
            if unless and unless.search(m["text"]):
                continue
            snippet = m["text"]
            i = max(0, match.start() - 20)
            j = min(len(snippet), match.end() + 20)
            return {
                "evidence": f"...{snippet[i:j]}...".replace("\n", " "),
                "matched": match.group(0),
            }
    return None


def detect_word_count_per_message(probe: dict, messages: list[dict], _tool_uses, _tool_errors=None, user_prompt: str = "", traj_stats: dict | None = None) -> dict | None:
    if not messages:
        return None
    threshold = float(probe.get("threshold", 80))
    # Clamp window to [1, len(messages)]: window=0 would make messages[-0:] the
    # WHOLE list (a silent off-by-everything), and a negative window is nonsense.
    window = max(1, min(int(probe.get("window", MSG_WINDOW_DEFAULT)), len(messages)))
    recent = messages[-window:]
    counts = [len(m["text"].split()) for m in recent]
    avg = sum(counts) / len(counts)
    if avg > threshold:
        # Request-warranted length: this warning governs the NEXT reply
        # ("tighten next reply"), so suppress it when the imminent prompt
        # explicitly asks for detail/depth/enumeration. caveman-ultra's own spec
        # is "keep replies short UNLESS detail is requested" — without this the
        # probe nags against a reply the skill itself permits (an explicit
        # "explain"/"summarize"/"think of N ways" turn). Opt-in per probe via
        # `warrant_pattern`; absent → always fires (prior behavior).
        warrant = probe.get("warrant_pattern")
        if warrant and user_prompt:
            try:
                if re.search(warrant, user_prompt):
                    return None
            except re.error as e:
                log_err(f"bad-warrant-regex probe={probe.get('_probe_id')} err={e!r}")
        return {
            "avg_words": round(avg, 1),
            "threshold": threshold,
            "window": window,
            "counts": counts,
        }
    return None


def detect_claim_without_evidence(probe: dict, messages: list[dict], tool_uses: list[dict], _tool_errors=None, user_prompt: str = "", traj_stats: dict | None = None) -> dict | None:
    if not messages:
        return None
    last_text = messages[-1]["text"]
    claim_pat_str = probe.get("claim_pattern", r"(?i)\b(done|fixed|complete|passes|verified|ready|working)\b")
    try:
        claim_pat = re.compile(claim_pat_str)
    except re.error as e:
        log_err(f"bad-claim-regex probe={probe.get('_probe_id')} err={e!r}")
        return None
    claim_match = claim_pat.search(last_text)
    if not claim_match:
        return None
    verify_tools = set(probe.get("verify_tools", ["Bash"]))
    verify_keywords = [kw.lower() for kw in probe.get(
        "verify_keywords",
        ["test", "pytest", "make", "build", "check", "lint", "curl", "verify"],
    )]
    # Word-boundary match, not plain substring: short keywords (ls, cat, wc, rg)
    # otherwise match inside unrelated words (results, category, rebuild), so an
    # incidental Bash command falsely counts as verification and the done-claim
    # warning is wrongly suppressed.
    verify_re = None
    if verify_keywords:
        verify_re = re.compile(r"\b(" + "|".join(re.escape(k) for k in verify_keywords) + r")\b")
    try:
        lookback = int(probe.get("lookback_tool_uses", 5))
    except (TypeError, ValueError):
        log_err(f"bad-lookback probe={probe.get('_probe_id')} value={probe.get('lookback_tool_uses')!r}")
        lookback = 5
    for tu in tool_uses[-lookback:]:
        if tu["name"] not in verify_tools:
            continue
        haystack_parts = []
        if tu["name"] == "Bash":
            haystack_parts.append(str(tu["input"].get("command", "")))
        else:
            haystack_parts.append(json.dumps(tu["input"]))
        haystack = " ".join(haystack_parts).lower()
        if verify_re is not None and verify_re.search(haystack):
            return None  # evidence found
    return {
        "claim": claim_match.group(0),
        "snippet": last_text[max(0, claim_match.start() - 20): claim_match.end() + 40].replace("\n", " "),
        "lookback": lookback,
    }


def detect_repeated_tool_error(probe: dict, _messages, _tool_uses, tool_errors=None, user_prompt: str = "", traj_stats: dict | None = None) -> dict | None:
    """Fire when the same tool-error signature recurs in the recent window.
    Transcript mining (2026-06-12) found one signature — 'File has not been
    read yet' — accounted for 15 of 18 tool errors across 5 sessions; the
    native harness error corrects each instance but nothing breaks the habit
    within a session. Generic: any drift_probes.json can declare a pattern."""
    if not tool_errors:
        return None
    pat_str = probe.get("pattern")
    if not pat_str:
        return None
    try:
        pat = re.compile(pat_str)
    except re.error as e:
        log_err(f"bad-regex probe={probe.get('_probe_id')} err={e!r}")
        return None
    min_count = int(probe.get("min_count", 2))
    hits = [t for t in tool_errors if pat.search(t)]
    if len(hits) >= min_count:
        return {
            "count": len(hits),
            "min_count": min_count,
            "example": hits[-1][:120].replace("\n", " "),
        }
    return None


def trajectory_stats(events: list[dict]) -> dict:
    """Tool-call vs tool-error counts over the SAME transcript tail, so a
    rate is well-defined (recent_tool_uses/errors use different caps).
    Adopted from HTC-style trajectory calibration (arXiv 2601.15778) in the
    cheapest form that pays: process-level error rate, no model, no training."""
    calls = errs = 0
    for e in events:
        msg = e.get("message") or {}
        content = msg.get("content")
        if not isinstance(content, list):
            continue
        for b in content:
            if not isinstance(b, dict):
                continue
            if e.get("type") == "assistant" and b.get("type") == "tool_use":
                calls += 1
            elif e.get("type") == "user" and b.get("type") == "tool_result" and b.get("is_error"):
                errs += 1
    return {"tool_calls": calls, "tool_errors": errs}


def detect_trajectory_drift(probe: dict, _messages, _tool_uses, _tool_errors=None,
                            user_prompt: str = "", traj_stats: dict | None = None) -> dict | None:
    """Fire when the session's tool-error RATE crosses a threshold — catches
    error-loop drift that per-signature probes (repeated_tool_error) miss
    when each retry fails differently. min_tool_calls guards cold starts."""
    if not traj_stats:
        return None
    calls = traj_stats.get("tool_calls", 0)
    errs = traj_stats.get("tool_errors", 0)
    min_calls = int(probe.get("min_tool_calls", 8))
    max_rate = float(probe.get("max_error_rate", 0.25))
    if calls < min_calls:
        return None
    rate = errs / calls
    if rate >= max_rate:
        return {"tool_calls": calls, "tool_errors": errs,
                "rate": round(rate, 3), "threshold": max_rate}
    return None


DETECTORS = {
    "forbidden_regex": detect_forbidden_regex,
    "word_count_per_message": detect_word_count_per_message,
    "claim_without_evidence": detect_claim_without_evidence,
    "repeated_tool_error": detect_repeated_tool_error,
    "trajectory_drift": detect_trajectory_drift,
}


def detect_user_correction(probe: dict, _messages, _tool_uses, _tool_errors=None,
                           user_prompt: str = "", traj_stats: dict | None = None) -> dict | None:
    """Fire when the user's CURRENT prompt is a correction ("no, use X",
    "that's wrong", "I said ..."). Closes the correction-capture gap
    (lineage: BayramAnnakov/claude-reflect, flagged in INSPIRATION.md):
    corrections are the highest-value learning source (exp1: feedback lift
    +0.667, the largest of the three) but the harvest reflex is prose-only —
    this makes the trigger mechanical, at the exact turn the correction lands."""
    if not user_prompt:
        return None
    pat_str = probe.get("pattern")
    if not pat_str:
        return None
    try:
        pat = re.compile(pat_str)
    except re.error as e:
        log_err(f"bad-regex probe={probe.get('_probe_id')} err={e!r}")
        return None
    m = pat.search(user_prompt)
    if m:
        return {"matched": m.group(0),
                "snippet": user_prompt[max(0, m.start() - 10): m.end() + 50].replace("\n", " ")}
    return None


DETECTORS["user_correction"] = detect_user_correction

# Same mechanism (regex the CURRENT user prompt) but for a PRE-TASK INTENT nudge
# rather than a correction: a skill fires the moment the prompt describes the
# situation it governs — e.g. loop-engineering on a "build a self-correcting
# automation" prompt. Measured rationale: spontaneous Skill-tool invocation is
# unreliable (blind agents don't auto-load loop-engineering even with a strong
# description), so a mechanical trigger beats hoping the model remembers.
DETECTORS["prompt_intent"] = detect_user_correction


# ---- workflow_nomination (learn-skill's nominate-not-auto-write trigger) -----
# Hermes auto-CREATES a skill after a complex (5+ tool-call) task. That is a
# memory-pollution machine without a reasoning gate. Brainer's port instead
# NOMINATES: when a non-trivial multi-step workflow completes, nudge the agent to
# `/learn` it — and let write-gate + dedup (in the /learn flow) decide if it earns
# a skill. The detector NEVER writes a skill; the system-reminder IS the nomination.
# Conservative by construction to avoid alert fatigue (GLM review): fires only at a
# WRAP-UP turn (last message is a completion claim), only past a tool-call floor,
# and only when the recent work is NON-TRIVIAL (an Edit/Write, or a Bash command
# that isn't build/test/install/lint/git/ls boilerplate).
_TRIVIAL_CMD_RE = re.compile(
    r"(?i)^\s*(?:cd\s+[^\n&|;]+(?:&&|;)\s*)*"
    r"(?:npm|yarn|pnpm|pip3?|pytest|python3?\s+-m\s+pytest|make|cargo|go|ls|ll|cat|head|"
    r"tail|echo|pwd|git|grep|rg|find|mkdir|cp|mv|rm|chmod|touch|source|node|"
    r"\./install|\./check|\./run|bash\s+skills/\S+/tools/install)\b"
)


def detect_workflow_nomination(probe: dict, messages: list[dict], tool_uses: list[dict],
                               _tool_errors=None, user_prompt: str = "",
                               traj_stats: dict | None = None) -> dict | None:
    if not traj_stats or not messages:
        return None
    calls = traj_stats.get("tool_calls", 0)
    if calls < int(probe.get("min_tool_calls", 6)):
        return None
    # Wrap-up gate: only nominate when the agent's last turn reads as a completion
    # claim — so this fires at task boundaries, not on every turn past the floor.
    last = messages[-1]["text"]
    try:
        if not re.search(_COMPLETION_CLAIM_DEFAULT, last):
            return None
    except re.error:
        return None
    # Triviality filter: needs at least one substantive action this window.
    try:
        trivial = re.compile(probe.get("trivial_pattern", "")) if probe.get("trivial_pattern") else _TRIVIAL_CMD_RE
    except re.error:
        trivial = _TRIVIAL_CMD_RE
    substantive = False
    for tu in (tool_uses or []):
        name = tu.get("name", "")
        if name in ("Edit", "Write", "NotebookEdit"):
            substantive = True
            break
        if name == "Bash":
            cmd = str((tu.get("input") or {}).get("command", ""))
            # Strip leading env-assignments / sudo so `FOO=1 npm test` or `sudo make`
            # are still recognised as boilerplate (adversarial-review false-positive).
            cmd = re.sub(r"^\s*(?:[A-Za-z_][A-Za-z0-9_]*=\S+\s+)*(?:sudo\s+)?", "", cmd)
            if cmd.strip() and not trivial.search(cmd):
                substantive = True
                break
    if not substantive:
        return None
    return {"tool_calls": calls,
            "recovered_after_errors": traj_stats.get("tool_errors", 0) > 0}


DETECTORS["workflow_nomination"] = detect_workflow_nomination


# Default patterns for early_stop (each overridable per-probe).
_EARLY_STOP_PROMISE = (
    r"(?i)\b(?:i'?ll|i will|i'?m going to|i am going to|let me|let'?s|next,?\s+i)\b"
    r"[^.?!\n]{0,70}\b(?:now|next|then|go ahead|proceed|start|begin|continue|"
    r"implement|run|create|write|add|fix|build|draft|set up|wire|tackle|"
    r"check|look|examine|review|investigate|verify|test|explore|search|read|"
    r"do (?:this|that|it))\b"
)
# A message that ALSO reports completed work → the promise is a legit "next
# steps" note, not an early stop. Suppress.
_EARLY_STOP_DONE = (
    r"(?i)\b(?:done|fixed|completed?|passes|passing|verified|shipped|committed|"
    r"implemented|merged|deployed|exit 0|all (?:pass|green|set|done)|"
    r"tests? (?:pass|green)|results?:)\b"
)
# The agent is ASKING the user (a question / permission request), not promising-
# then-yielding. That is a legitimate pause (over-pausing is an autonomy concern,
# handled in lean-execution, not an early stop). Suppress.
_EARLY_STOP_QUESTION = (
    r"(?i)(?:\?|\blet me know\b|\bwant me to\b|\bshould i\b|\bshall i\b|"
    r"\bdo you (?:want|prefer)\b|\bwould you like\b|\bwhich (?:option|approach|one)\b)"
)


def detect_early_stop(probe: dict, messages: list[dict], _tool_uses, _tool_errors=None,
                      user_prompt: str = "", traj_stats: dict | None = None) -> dict | None:
    """Fire when the agent's LAST turn ended on a forward-looking PROMISE
    ("I'll now implement…", "let me start…") with no completion claim, no
    question, and no tool call that turn — i.e. it narrated the next step
    instead of doing it. The anti-early-stop reflex: if your final paragraph is
    a plan or a promise, do that work NOW. Suppressed when the closing turn
    actually called a tool (work happened), reported completion (legit 'next
    steps'), or asked the user a question (a legitimate pause)."""
    if not messages:
        return None
    # The closing turn did real work → not an early stop.
    if traj_stats and traj_stats.get("final_assistant_has_tool_use"):
        return None
    last = messages[-1]["text"]
    if not last.strip():
        return None
    try:
        promise = re.compile(probe.get("pattern", _EARLY_STOP_PROMISE))
        done = re.compile(probe.get("done_pattern", _EARLY_STOP_DONE))
        question = re.compile(probe.get("question_pattern", _EARLY_STOP_QUESTION))
    except re.error as e:
        log_err(f"bad-regex probe={probe.get('_probe_id')} err={e!r}")
        return None
    # Only the CLOSING window — a promise after a completed-work report up top is
    # a legit "next steps" note, not an early stop.
    tail = last[-400:]
    m = promise.search(tail)
    if not m:
        return None
    if done.search(last) or question.search(tail):
        return None
    return {"matched": m.group(0).strip().replace("\n", " ")[:80],
            "snippet": tail[max(0, m.start() - 20): m.end() + 40].replace("\n", " ")}


DETECTORS["early_stop"] = detect_early_stop


# ---- completion_without_closure (the closure gate) --------------------------
# Requirement: when the agent believes the WHOLE task is finished it must
# EXPLAIN what it did against what was asked and ASK the user whether the task
# can be closed — never self-close. This is the mirror of early_stop: early_stop
# catches "promised, didn't do it"; this catches "did it, closed it myself
# without asking". Distinct from claim_without_evidence (which is about EVIDENCE)
# — this fires even when verification ran, because a verified-done still must be
# offered to the user for closure.

# A TERMINAL "whole task is finished" claim — deliberately tighter than verify-
# before-completion's claim regex (which fires on any sub-step "done"), to avoid
# nagging on mid-task milestones. Overridable per-probe via `claim_pattern`.
_COMPLETION_CLAIM_DEFAULT = (
    r"(?i)(?:\ball done\b|\btask (?:is )?(?:complete|completed|done|finished)\b|"
    r"\b(?:fully|now) (?:complete|completed|done|finished|implemented)\b|"
    r"\bthat'?s (?:it|all|everything)\b(?!\s+(?:from\b|for (?:now|today|tonight)\b))|\bwrapped up\b|"
    r"\bready to (?:go|ship|merge|review)\b|\bgood to go\b|"
    r"\b(?:this|it|everything) is (?:now )?(?:done|complete|completed|finished|ready)\b|"
    r"\bimplementation (?:is )?complete\b|\ball (?:set|green)\b|"
    r"\beverything(?:'?s| is) (?:done|working|complete)\b|"
    # A bare standalone "Done"/"Finished"/"Complete" at the START of the final
    # message — the single most common phrasing ("Done!", "Done.", "Done —
    # added the flag"). Negative-lookahead excludes mid-task "done with/the X"
    # so a sub-step report doesn't trip the terminal gate.
    r"^\s*(?:done|finished|complete|completed)\b"
    r"(?!\s+(?:with|the|implementing|fixing|adding|writing|updating|making|building|setting|wiring|on)\b))"
)
# The message already invites the user to confirm closure → contract satisfied,
# suppress. Kept conservative: a FALSE suppression (thinking it asked when it
# didn't) is the failure to avoid. Overridable per-probe via `ask_pattern`.
_CLOSURE_ASK_DEFAULT = (
    r"(?i)(?:close (?:it|this|that|the task|out)|ok(?:ay)? to close|safe to close|"
    r"can (?:i|we) close|shall i (?:close|wrap up|mark)|should i (?:close|mark)|"
    r"mark (?:this|it|that) (?:as )?(?:done|closed|complete)|anything else|"
    r"is (?:this|that) (?:everything|all you needed|complete\?)|may i close|"
    r"confirm (?:i can )?clos(?:e|ing)|"
    r"let me know if (?:there'?s|there is) (?:anything|more)|"
    r"can (?:this|it) be closed)"
)
# The agent is CONTINUING to a next step → a milestone note, not a terminal
# close; suppress. Verb-agnostic (unlike early_stop's promise regex, which lists
# specific verbs) so "Task complete. Next I will refactor…" is caught.
_CLOSURE_CONTINUE_DEFAULT = (
    r"(?i)(?:\bnext,?\s+i\b|\bthen i\b|\bnow i'?ll\b|"
    r"\bi'?ll (?:now|next|then|also|go|start|continue|move)\b|\blet me\b|"
    r"\bi'?m going to\b|\bi am going to\b|"
    r"\bi will (?:now|next|then|also|continue|start|go|refactor|implement|add|write|create)\b|"
    r"\bmoving on\b|\bnext step\b|\bafter (?:this|that),? i\b)"
)


def detect_completion_without_closure(probe: dict, messages: list[dict], _tool_uses, _tool_errors=None,
                                      user_prompt: str = "", traj_stats: dict | None = None) -> dict | None:
    """Fire when the last assistant message makes a TERMINAL completion claim
    but neither asks the user to confirm closure nor promises further work (a
    milestone note, not a close). The contract: enumerate what was asked, map
    each item to what you did, then ASK the user whether it can be closed."""
    if not messages:
        return None
    last = messages[-1]["text"]
    if not last.strip():
        return None
    try:
        claim = re.compile(probe.get("claim_pattern", _COMPLETION_CLAIM_DEFAULT))
        ask = re.compile(probe.get("ask_pattern", _CLOSURE_ASK_DEFAULT))
        promise = re.compile(probe.get("promise_pattern", _CLOSURE_CONTINUE_DEFAULT))
    except re.error as e:
        log_err(f"bad-regex probe={probe.get('_probe_id')} err={e!r}")
        return None
    m = claim.search(last)
    if not m:
        return None
    if ask.search(last):
        return None  # already inviting closure confirmation — contract met
    if promise.search(last):
        return None  # still promising more work — a milestone, not a terminal close
    return {"claim": m.group(0).strip(),
            "snippet": last[max(0, m.start() - 20): m.end() + 40].replace("\n", " ")}


DETECTORS["completion_without_closure"] = detect_completion_without_closure


# ---- Mechanism 3: request ledger (never silently drop a user request) -------
# Persistent, across-turn tracker. Each substantive user request is recorded as
# OPEN and stays open until the USER closes it ("open until completed or the
# user says so"). The hook NEVER judges semantic completion itself — it tracks
# text + turns mechanically and surfaces open items to the model (which has the
# semantics) at wrap-up turns and on cadence. Closure is user-driven: a closure
# phrase in the user's prompt prunes the ledger; the completion gate above is
# what prompts the agent to ASK for that closure. The two interlock.
LEDGER_STORE_CAP = 50      # hard cap on stored items (bound state-file size)
LEDGER_SHOW_MAX = 8        # max items surfaced in one reminder
LEDGER_TEXT_CAP = 140      # chars kept per remembered request

# Pure acknowledgements / answers — not new trackable requests. Skipped.
_LEDGER_TRIVIAL_RE = re.compile(
    r"(?i)^\s*(?:ok(?:ay)?|k|yes|yep|yeah|sure|got it|sounds good|thanks?(?: you)?|"
    r"ty|cool|nice|great|perfect|go on|go ahead|continue|proceed|please do|do it|"
    r"next|y|n|no|nope)\s*[.!]*\s*$"
)
# The user closing/dismissing work → prune the ledger (don't append).
_LEDGER_CLOSE_RE = re.compile(
    r"(?i)(?:\bclose (?:it|this|that|the task|out|them|all|everything)\b|"
    r"\byou can close\b|\bok(?:ay)? to close\b|\bsafe to close\b|\bwe can close\b|"
    r"\bmark (?:it|this|that|them) (?:as )?(?:done|closed|complete)\b|"
    r"\bthat'?s all\b|\bthat'?s everything\b|\bnothing else\b|\bno(?:thing)? further\b|"
    r"\bwe'?re done\b|\ball done\b|\bdone with (?:it|that|this|everything)\b|"
    r"\bdrop (?:it|that|this)\b|\bnever ?mind\b|\bforget (?:it|that)\b|"
    r"\bcancel (?:it|that|this)\b|\bship it\b|\byes,? close\b|\byou can stop\b)"
)
# Distinguishes "close everything" from "close the last thing".
_LEDGER_CLOSE_ALL_RE = re.compile(
    r"(?i)\b(?:all|everything|both|all of (?:it|them)|the rest)\b"
)
# NOTE: there is intentionally NO opt-out / opt-in path. The no-drop guarantee is
# UNCONDITIONAL — by user directive ("never switch off, never opt out"), nothing
# in the normal conversation flow can disable the ledger. (The only kill is the
# whole-hook operator valve COMPLIANCE_CANARY_DISABLED, which disables the entire
# drift watcher, not the ledger specifically.) A prior design had a regex-detected
# opt-out; it was removed because a misread would silently disable the very
# guarantee this feature exists to provide — the one failure mode that must not
# happen.

# The user parking an EXISTING item — visibly deferred, NOT dropped.
# CRITICAL (review B2): require an explicit deferral VERB on an item ("park that",
# "defer the X", "leave it for later", "that can wait") — NOT bare adverbials
# ("for now" / "not now" / "out of scope" / "later"), which appear incidentally in
# prompts that ALSO carry a real ask ("for now this looks fine, also add X"). And
# exclude "defer to (you|me|...)" (delegation, not parking).
_LEDGER_DEFER_RE = re.compile(
    r"(?i)(?:"
    r"\b(?:defer|park|shelve|postpone|backlog)(?!\s+to\b)\s+(?:that|this|it|the\b[^\n]{0,40})"
    r"|\bleave (?:that|this|it)\s+(?:for (?:later|now)|aside|until)\b"
    r"|\b(?:that|this|it) can wait\b"
    r"|\bput (?:that|this|it) (?:on the backlog|aside|on hold)\b"
    r")"
)
# A meta-command (close / park) carries a co-occurring NEW request only when an
# explicit conjunction introduces an imperative ("...and add X", "..., then pin
# numpy"). Detecting THAT (rather than mere prompt length) is what lets a pure
# verbose close ("perfect, that's everything — close it") terminate cleanly while
# "close it and add a test" still captures the test (review B2/M3: never drop a
# co-occurring ask, never junk-capture a pure meta-command).
_LEDGER_COMPOUND_RE = re.compile(
    r"(?i)(?:\b(?:and|also|plus|then)\b|[,;]\s)\s*(?:can you |could you |would you |please )?"
    r"(?:add|create|write|fix|update|make|implement|build|remove|delete|rename|refactor|"
    r"test|document|check|pin|install|set ?up|wire|handle|support|enable|ensure|include|"
    r"generate|run|review|investigate|answer|explain)\b"
)


def _ledger_make_id(turn: int, text: str) -> str:
    return f"r{turn}-" + hashlib.sha256(text.encode("utf-8", "replace")).hexdigest()[:6]


def update_ledger(ledger: list, prompt: str, turn: int) -> tuple[list, list, str]:
    """Pure mechanical lifecycle. Returns (new_ledger, closed_items, action).
    NEVER judges semantic completion (the model does, via the surfaced reminder
    + completion gate). An item leaves the OPEN set only when the USER says so;
    a parked item is re-statused (deferred), never deleted. A meta-command that
    ALSO contains a co-occurring imperative ("close it and add X") performs the
    meta-action AND captures the prompt, rather than dropping the new ask. There
    is NO opt-out — capture is unconditional (see note above the regexes).

    Actions: add · close-one · close-all · close-noop · skip-trivial · none · defer."""
    closed: list = []
    p = (prompt or "").strip()
    if not p:
        return ledger, closed, "none"
    has_new_ask = bool(_LEDGER_COMPOUND_RE.search(p))

    meta = None
    if _LEDGER_CLOSE_RE.search(p):
        if not ledger:
            meta = "close-noop"
        elif _LEDGER_CLOSE_ALL_RE.search(p):
            closed = list(ledger)
            ledger = []
            meta = "close-all"
        else:
            closed = [ledger[-1]]
            ledger = ledger[:-1]
            meta = "close-one"
    elif _LEDGER_DEFER_RE.search(p):
        for i in range(len(ledger) - 1, -1, -1):
            if not ledger[i].get("deferred"):
                ledger = [dict(it) for it in ledger]
                ledger[i]["deferred"] = True
                meta = "defer"
                break

    # Pure meta-command (no co-occurring imperative) → perform it, don't capture.
    if meta and not has_new_ask:
        return ledger, closed, meta
    if not meta and _LEDGER_TRIVIAL_RE.match(p):
        return ledger, closed, "skip-trivial"

    # Capture the whole prompt (a real ask, or a meta+ask compound — over-capture
    # is the safe direction; never drop). The meta effect above already applied.
    item = {"id": _ledger_make_id(turn, p), "turn": turn, "text": p[:LEDGER_TEXT_CAP]}
    ledger = (ledger + [item])[-LEDGER_STORE_CAP:]
    return ledger, closed, (meta or "add")


def has_completion_claim(events: list[dict]) -> bool:
    """True iff the most-recent assistant message reads as a TERMINAL completion
    claim (and isn't still promising more work). Drives ledger surfacing at the
    exact wrap-up turn — 'you're closing but N requests are still open'."""
    msgs = recent_assistant_messages(events, 1)
    if not msgs:
        return False
    last = msgs[-1]["text"]
    try:
        return bool(re.search(_COMPLETION_CLAIM_DEFAULT, last)) and not re.search(_EARLY_STOP_PROMISE, last)
    except re.error:
        return False


def build_ledger_lines(open_items: list, closed_now: list, completion_claim: bool, turn: int) -> list[str]:
    # Deferred items are visibly parked, not open — exclude from the "still open"
    # count so an agreed deferral never trips the wrap-up nag.
    open_items = [it for it in open_items if not it.get("deferred")]
    lines: list[str] = []
    if closed_now:
        tail = f"; {len(open_items)} still open." if open_items else " — ledger now empty."
        lines.append(
            f"compliance-canary ledger (turn {turn}): closed {len(closed_now)} request(s) "
            f"on your say-so{tail}"
        )
    if open_items and (completion_claim or not closed_now):
        if completion_claim:
            lines.append(
                f"compliance-canary ledger (turn {turn}): you appear to be wrapping up, but "
                f"{len(open_items)} user request(s) are still OPEN. Do NOT self-close. For EACH item "
                f"below, state what you did (with evidence) or why it's deferred, then ASK the user to "
                f"confirm closure:"
            )
        else:
            lines.append(
                f"compliance-canary ledger (turn {turn}): {len(open_items)} user request(s) still open "
                f"— none may be dropped. Make progress on each, or note explicitly why it's deferred:"
            )
        for it in open_items[:LEDGER_SHOW_MAX]:
            lines.append(f"- [turn {it.get('turn','?')}] {it.get('text','')}")
        extra = len(open_items) - LEDGER_SHOW_MAX
        if extra > 0:
            lines.append(f"- (+{extra} more still open)")
        # This is the hidden cross-check (coarse, 1 row/prompt). Point the agent
        # at the authoritative atomic ledger it should be curating + reconciling.
        lines.append(
            "- (these are the canary's COARSE captures — reconcile against your atomic "
            "requirements ledger; each request/question/sub-item must be accounted for)"
        )
    return lines


# Detector for the requirements-ledger skill: fire when the user has raised
# trackable requests but the agent shows no sign of MATERIALIZING the visible
# ledger (no Edit/Write to a *ledger*.md and no TaskCreate/TaskUpdate). The
# cross-check direction is deliberate: the hidden capture is COARSE (≤1 row /
# prompt), the visible ledger is ATOMIC (more rows) — so we NEVER compare counts
# for equality (atomic > coarse is correct, not drift). We only alarm on absence
# of maintenance activity. Reuses the existing request_ledger capture via
# traj_stats; adds no new transcript scan.
# Scope to the ACTUAL conversation ledger, not any *.md whose path happens to
# contain "requirements/ledger/task/todo" (review M1: docs/requirements.md or a
# project TASKS.md would otherwise turn the guard dark). Match a file under
# .brainer/ledger/ OR a ledger-specific basename.
_LEDGER_MAINT_PATH_DEFAULT = (
    r"(?i)(?:(?:^|/)\.brainer/ledger/[^/\n]+\.md$|(?:^|/)(?:requirements[ _-]?)?ledger[^/\n]*\.md$)"
)
_LEDGER_MAINT_TOOLS = ("TaskCreate", "TaskUpdate")
_LEDGER_MAINT_EDIT_TOOLS = ("Edit", "Write", "NotebookEdit")


def detect_ledger_not_materialized(probe: dict, _messages, tool_uses: list[dict], _tool_errors=None,
                                   user_prompt: str = "", traj_stats: dict | None = None) -> dict | None:
    if not traj_stats:
        return None
    open_ct = _as_int(traj_stats.get("open_ledger_count"), 0)
    if open_ct < int(probe.get("min_open", 2)):
        return None
    if int(traj_stats.get("substantive_add_count", 0)) < int(probe.get("substantive_turns", 2)):
        return None
    # Cold-start grace: don't demand a ledger before the session has any history.
    if int(traj_stats.get("turn", 0)) < int(probe.get("grace_turns", 3)):
        return None
    try:
        path_re = re.compile(probe.get("maintenance_path_pattern", _LEDGER_MAINT_PATH_DEFAULT))
    except re.error as e:
        log_err(f"bad-regex probe={probe.get('_probe_id')} err={e!r}")
        path_re = re.compile(_LEDGER_MAINT_PATH_DEFAULT)
    for tu in (tool_uses or []):
        name = tu.get("name", "")
        if name in _LEDGER_MAINT_TOOLS:
            return None  # native-task mirror is being maintained
        if name in _LEDGER_MAINT_EDIT_TOOLS:
            fp = str((tu.get("input") or {}).get("file_path", ""))
            if path_re.search(fp):
                return None  # the visible markdown ledger is being maintained
    return {"open_count": open_ct}


DETECTORS["ledger_not_materialized"] = detect_ledger_not_materialized


class _ProbeBudgetExceeded(BaseException):
    """Raised by the SIGALRM handler to abort a runaway probe phase. Derives
    from BaseException (not Exception) on purpose: run_probes' per-detector
    `except Exception` must NOT swallow it — it has to unwind the whole phase."""


@contextmanager
def probe_time_limit(seconds: float):
    """Hard wall-clock cap on the enclosed block via SIGALRM. Unix-only;
    `UserPromptSubmit` is Claude-Code-only (macOS/Linux), and on any platform
    without SIGALRM (or seconds<=0) this is a no-op — degrade to unbounded
    rather than crash."""
    if seconds <= 0 or not hasattr(signal, "SIGALRM"):
        yield
        return

    def _handler(signum, frame):
        raise _ProbeBudgetExceeded()

    old = signal.signal(signal.SIGALRM, _handler)
    try:
        signal.setitimer(signal.ITIMER_REAL, seconds)
        yield
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, old)


def run_probes(
    probes: list[dict],
    messages: list[dict],
    tool_uses: list[dict],
    suppressed: set[str],
    tool_errors: list[str] | None = None,
    user_prompt: str = "",
    traj_stats: dict | None = None,
) -> list[dict]:
    """Returns list of fired probes (each dict has _skill, _probe_id, _result)."""
    fired: list[dict] = []
    for probe in probes:
        kind = probe.get("kind")
        if kind not in DETECTORS:
            continue
        if probe["_probe_id"] in suppressed:
            continue
        try:
            result = DETECTORS[kind](probe, messages, tool_uses, tool_errors, user_prompt=user_prompt, traj_stats=traj_stats)
        except Exception as e:
            log_err(f"detector-fail probe={probe['_probe_id']} err={e!r}")
            continue
        if result:
            probe["_result"] = result
            fired.append(probe)
            if len(fired) >= MAX_PROBES_TRIGGERED:
                break
    return fired


# -------------------------- output ------------------------------------------

def format_one_probe(probe: dict) -> str:
    skill = probe["_skill"]
    kind = probe.get("kind", "?")
    r = probe.get("_result", {})
    msg = probe.get("message")  # optional human-readable override
    if msg:
        return f"- {skill} [{kind}]: {msg}"
    if kind == "forbidden_regex":
        return f"- {skill} [forbidden_regex]: matched {r.get('matched','?')!r} — recent text: {r.get('evidence','')}"
    if kind == "word_count_per_message":
        return (
            f"- {skill} [word_count_per_message]: avg {r.get('avg_words')} words/msg "
            f"over last {r.get('window')} > threshold {r.get('threshold')}"
        )
    if kind == "claim_without_evidence":
        return (
            f"- {skill} [claim_without_evidence]: claim {r.get('claim')!r} appears "
            f"without a verification tool call in last {r.get('lookback')} tool_uses"
        )
    return f"- {skill} [{kind}]: triggered"


def build_output(fired: list[dict], pulse_skills: list[tuple[str, str]], turn: int,
                 ledger_lines: list[str] | None = None) -> str:
    """One <system-reminder> carrying whichever mechanism(s) produced output.
    Symptomatic correctives lead (higher signal); the request-ledger section
    follows (it does NOT yield at a wrap-up turn — surfacing open requests as the
    agent closes is the whole point); the periodic re-anchor comes last and only
    when no probe fired this turn (it yields — see main)."""
    lines = ["<system-reminder>"]
    if fired:
        lines.append(
            f"compliance-canary (turn {turn}): drift signals detected in your recent "
            f"output. Re-read each named rule and correct your next reply before continuing."
        )
        for probe in fired:
            lines.append(format_one_probe(probe))
    if ledger_lines:
        lines.extend(ledger_lines)
    if pulse_skills:
        lines.append(
            f"compliance-canary re-anchor (turn {turn}): these active skills' rules remain "
            f"in force — re-read each and check your most recent reply against it."
        )
        for name, reminder in pulse_skills:
            # Cap a runaway pulse_reminder so one skill can't flood the block.
            r = reminder if len(reminder) <= MAX_REMINDER_CHARS else reminder[:MAX_REMINDER_CHARS - 1] + "…"
            lines.append(f"- {name}: {r}")
    lines.append("</system-reminder>")
    return "\n".join(lines)


# -------------------------- main --------------------------------------------

def main() -> int:
    # NOTE: COMPLIANCE_CANARY_DISABLED is checked LATER (after the ledger capture
    # block), not here — the kill silences drift detection + its reminders, but it
    # must NEVER stop the ledger from RECORDING a request (user directive: the kill
    # must not disable the ledger). Capture runs unconditionally; only the nagging
    # is silenced.
    cooldown = COOLDOWN_TURNS_DEFAULT
    try:
        cooldown = max(0, int(os.environ.get("COMPLIANCE_CANARY_COOLDOWN", COOLDOWN_TURNS_DEFAULT)))
    except ValueError:
        pass

    raw = sys.stdin.read()
    if not raw.strip():
        return 0
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as e:
        log_err(f"json-decode-fail: {e}")
        return 0

    # Valid JSON that isn't an object (a bare number/string/array/null) would
    # crash every downstream .get() — guard the always-exit-0 contract.
    if not isinstance(payload, dict):
        log_err(f"payload-not-object: {type(payload).__name__}")
        return 0

    # Coerce session_id to str: a non-string (number/array) would crash
    # .encode() in state_path. `or "unknown"` keeps falsy ids out.
    session_id = str(payload.get("session_id") or "unknown")
    transcript_path = payload.get("transcript_path", "")

    path = state_path(session_id)
    is_new_session = not path.exists()

    # Mechanism 3 — request ledger lifecycle. UNCONDITIONAL (no opt-out / no
    # per-ledger disable — user directive "never switch off, never opt out"; the
    # only kill is the whole-hook COMPLIANCE_CANARY_DISABLED valve at the top of
    # main). Mutates state inside the same lock as the turn bump; closed_now/ledger
    # are reused for output below.
    closed_now: list = []
    ledger: list = []
    ledger_action = "none"
    substantive_add_count = 0
    prompt_text = str(payload.get("prompt") or "")

    with state_lock(path):
        state = load_state(path)
        turn = _as_int(state.get("turn_count"), 0) + 1  # guard: corrupt state must not crash (always-exit-0)
        state["turn_count"] = turn
        state["last_seen_iso"] = time.strftime("%FT%TZ", time.gmtime())
        if is_new_session:
            state["session_started_iso"] = state["last_seen_iso"]
        ledger, closed_now, ledger_action = update_ledger(
            state.get("request_ledger", []), prompt_text, turn)
        state["request_ledger"] = ledger
        if ledger_action == "add":
            state["substantive_add_count"] = _as_int(state.get("substantive_add_count"), 0) + 1
        substantive_add_count = _as_int(state.get("substantive_add_count"), 0)
        # Persist counter + ledger early — if any later step errors, we still progress
        save_state(path, state)

    if is_new_session:
        gc_old_state(path.parent, time.time())

    # Whole-hook break-glass valve. Checked HERE (not at entry) so the ledger
    # capture above has already run — the kill silences drift detection + all
    # reminders, but the request is still on the record. Re-enabling resumes with
    # nothing lost.
    if os.environ.get("COMPLIANCE_CANARY_DISABLED") == "1":
        return 0

    # --- periodic re-anchor cadence (absorbed skill-pulse) ---------------
    # COMPLIANCE_CANARY_PULSE_EVERY is primary; SKILL_PULSE_EVERY is a
    # back-compat alias. 0 (or *_PULSE_DISABLED / legacy SKILL_PULSE_DISABLED)
    # disables JUST the re-anchor — symptomatic probes still run.
    try:
        raw_every = int(os.environ.get(
            "COMPLIANCE_CANARY_PULSE_EVERY",
            os.environ.get("SKILL_PULSE_EVERY", CADENCE_DEFAULT)))
    except ValueError:
        raw_every = CADENCE_DEFAULT
    if (os.environ.get("COMPLIANCE_CANARY_PULSE_DISABLED") == "1"
            or os.environ.get("SKILL_PULSE_DISABLED") == "1"):
        raw_every = 0
    pulse_every = 0 if raw_every <= 0 else max(CADENCE_FLOOR, raw_every)
    is_pulse_turn = bool(pulse_every) and turn >= pulse_every and turn % pulse_every == 0

    # --- symptomatic probes (every turn) --------------------------------
    fired: list[dict] = []
    probes = discover_probes(skills_root())
    # C4 — scope probes to a deployment's ACTIVE skills. Default (unset) = every
    # discovered skill's probes run, exactly as before (no regression). Set
    # COMPLIANCE_CANARY_PROBE_SKILLS=a,b,c to fire ONLY those skills' probes — so a
    # session that never invoked caveman-ultra's terse style isn't nagged by its
    # filler/word-count probes. Mirrors COMPLIANCE_CANARY_PULSE_SKILLS (re-anchor).
    _probe_allow = {s.strip() for s in
                    os.environ.get("COMPLIANCE_CANARY_PROBE_SKILLS", "").split(",") if s.strip()}
    if _probe_allow:
        probes = [p for p in probes if p.get("_skill") in _probe_allow]
    # One transcript read feeds both the probes and the ledger's wrap-up check.
    events: list[dict] = []
    if probes or ledger:
        events = read_transcript_tail(transcript_path)
    if probes:
        if events:
            # Fetch enough messages for the LARGEST declared word_count window.
            # Don't early-return on empty messages: tool_use-only turns (the norm
            # during error loops) have no assistant TEXT, but that's exactly when
            # the non-text detectors (trajectory_drift, repeated_tool_error,
            # user_correction) must still run. Text detectors no-op on [].
            WORD_COUNT_WINDOW_CAP = 50
            max_window = max(
                [MSG_WINDOW_DEFAULT]
                + [
                    min(int(p.get("window", MSG_WINDOW_DEFAULT)), WORD_COUNT_WINDOW_CAP)
                    for p in probes
                    if p.get("kind") == "word_count_per_message"
                    and str(p.get("window", MSG_WINDOW_DEFAULT)).lstrip("-").isdigit()
                ]
            )
            messages = recent_assistant_messages(events, max_window) or []
            tool_uses = recent_tool_uses(events, n=10)
            tool_errors = recent_tool_errors(events)

            history = state.get("probe_history", [])
            suppressed = {
                h["probe_id"] for h in history
                if isinstance(h, dict)
                and turn - int(h.get("fired_at_turn", 0)) < cooldown
            }

            traj = trajectory_stats(events)
            traj["final_assistant_has_tool_use"] = final_assistant_has_tool_use(events)
            # Feed the requirements-ledger cross-check (ledger_not_materialized).
            # open_ledger_count counts only items from PRIOR turns (this turn's
            # fresh adds aren't a "drop" yet) and excludes parked/deferred items.
            traj["turn"] = turn
            traj["open_ledger_count"] = sum(
                1 for it in ledger
                if not it.get("deferred") and _as_int(it.get("turn"), turn) < turn)
            traj["substantive_add_count"] = substantive_add_count
            try:
                with probe_time_limit(PROBE_TIMEOUT_SECONDS):
                    fired = run_probes(probes, messages, tool_uses, suppressed, tool_errors,
                                       user_prompt=str(payload.get("prompt") or ""),
                                       traj_stats=traj)
            except _ProbeBudgetExceeded:
                # A drift_probes regex blew the time budget (likely ReDoS). Skip
                # probes this turn rather than wedge the prompt. Re-anchor below
                # still runs (it uses only fixed regexes).
                log_err(f"probe-budget-exceeded: skipped probes (>{PROBE_TIMEOUT_SECONDS}s)")
                fired = []
            if fired:
                with state_lock(path):
                    state = load_state(path)
                    history = state.get("probe_history", [])
                    for probe in fired:
                        history.append({"probe_id": probe["_probe_id"], "fired_at_turn": turn})
                    state["probe_history"] = history[-50:]
                    save_state(path, state)

    # --- periodic re-anchor (yields to fired probes — no double-nag) -----
    pulse_skills: list[tuple[str, str]] = []
    if is_pulse_turn and not fired:
        allow_raw = os.environ.get(
            "COMPLIANCE_CANARY_PULSE_SKILLS",
            os.environ.get("SKILL_PULSE_SKILLS", ""))
        allowlist = {s.strip() for s in allow_raw.split(",") if s.strip()}
        pulse_skills = discover_pulse_skills(skills_root(), allowlist)

    # --- request-ledger surfacing (coupled to drift) --------------------
    # The ledger reminder rides along with the canary's drift response: open
    # requests are re-surfaced exactly when attention is being re-directed —
    #   • a drift probe fired (DRIFT → "you're drifting; don't drop these"),
    #   • the agent is wrapping up on a completion claim (don't self-close),
    #   • the periodic re-anchor turn (preventive), or
    #   • the user just closed something (confirm it).
    # No drift, no wrap-up, no cadence → stay quiet. This is the "remind about
    # ledger items IF there is drift" coupling.
    ledger_lines: list[str] = []
    if closed_now or ledger:
        completion_claim = has_completion_claim(events) if ledger else False
        show = bool(closed_now) or (bool(ledger) and (completion_claim or bool(fired) or is_pulse_turn))
        if show:
            ledger_lines = build_ledger_lines(ledger, closed_now, completion_claim, turn)

    if not fired and not pulse_skills and not ledger_lines:
        return 0

    sys.stdout.write(build_output(fired, pulse_skills, turn, ledger_lines))
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
