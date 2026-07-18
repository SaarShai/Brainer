#!/usr/bin/env python3
r"""compliance-canary UserPromptSubmit hook — the single drift watcher.

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
import shlex
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

PROFILES = {"frontier", "shadow", "legacy", "off"}
FRONTIER_VERIFY_PROBE_IDS = {
    "verify-before-completion:claim-without-evidence",
}

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
_INLINE_CODE_RE = re.compile(r"`([^`\n]+)`")


def _unwrap_inline_span(m: "re.Match") -> str:
    """Inline single-backtick spans are UNWRAPPED (backticks dropped, content
    kept) when the span contains whitespace — i.e. it reads as a natural-
    language PHRASE/SENTENCE styled in backticks (e.g. a closing claim like
    `` `Done and dusted.` ``), not a code token. Pre-fix, strip_code() removed
    the ENTIRE span including its text, so a done-claim wrapped wholly in
    backticks was invisible to claim_without_evidence before the detector
    ever ran (red-team 2026-07-11). A single-token span with NO whitespace
    (a flag/identifier/filename someone is quoting for reference, e.g.
    `done`, `census.py`, `print("Certainly!")`) is still fully REMOVED, not
    unwrapped — that's the code-quoting false-positive case strip_code exists
    to prevent in the first place ("I added a `done` flag" must NOT read as a
    claim; a fenced ```block``` is unaffected either way — handled above)."""
    inner = m.group(1)
    return inner if re.search(r"\s", inner) else " "


def strip_code(text: str) -> str:
    text = _CODE_BLOCK_RE.sub(" ", text)
    text = _INLINE_CODE_RE.sub(_unwrap_inline_span, text)
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


def active_profile() -> str:
    """Return the deployment profile, failing quiet and lean on bad input."""
    raw = os.environ.get("COMPLIANCE_CANARY_PROFILE", "frontier").strip().lower()
    if raw in PROFILES:
        return raw
    log_err(f"unknown-profile value={raw!r}; using frontier")
    return "frontier"


def selected_probe_ids(defaults: set[str] | None = None) -> set[str]:
    """Exact probe-ID selector (`skill:id`), replacing skill-level selection.

    An unset variable uses ``defaults``. An explicitly empty value selects no
    probes, which is useful for controlled experiments without disabling state.
    """
    raw = os.environ.get("COMPLIANCE_CANARY_PROBE_IDS")
    if raw is None:
        return set(defaults or ())
    return {part.strip() for part in raw.split(",") if part.strip()}


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
    # Anchor to CLAUDE_PROJECT_DIR, exactly like state_dir() above — a cwd-relative
    # ".claude/skills" silently points at a nonexistent dir once the agent cd's into
    # a subdir, which made probe/pulse DISCOVERY go dark (the drift watcher itself).
    project = os.environ.get("CLAUDE_PROJECT_DIR")
    base = Path(project) if project else Path.cwd()
    return base / ".claude" / "skills"


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


def gc_old_intent_logs(dir_path: Path, now: float) -> int:
    """F5a (2026-07-18 audit): GC parity with state files — intent logs older
    than the same GC_AGE_SECONDS (7-day) horizon are removed by the same
    new-session gc pass. Only *.jsonl in the intent dir are touched."""
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
                if not entry.name.endswith(".jsonl"):
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

def _normalize_events(events: list[dict]) -> list[dict]:
    """Map a Codex {type,payload} transcript into Claude event shape so every
    detector (which reads Claude-shaped tool_use/message blocks) works on both
    hosts. Claude transcripts pass through. Degrades to identity if the shared
    module is missing — never breaks the always-exit-0 contract."""
    try:
        shared = Path(__file__).resolve().parent.parent.parent / "_shared"
        if str(shared) not in sys.path:
            sys.path.insert(0, str(shared))
        import transcript_norm
        return transcript_norm.normalize(events)
    except Exception as e:
        log_err(f"normalize-fail err={e!r}")
        return events


def _record_trigger_matched_activations(fired: list[dict]) -> None:
    """Best-effort activation telemetry: one "trigger_matched" event per
    DISTINCT skill whose probe actually matched this turn (`fired` is the
    subset of discovered probes whose drift condition triggered — the exact
    "matched", not merely "registered/mentioned in the catalog", signal this
    hook already computes for its own probe display). source="live" — this
    is a real session, not a fixture writer.

    This is telemetry, not a drift mechanism: it must NEVER affect drift
    logic, the ledger, or the re-anchor, and it must NEVER be the thing that
    breaks the hook's always-exit-0 / <PROBE_TIMEOUT_SECONDS contract.
    record_activation() itself never raises (fails closed, returns False on
    any error) — this wrapper is belt-and-suspenders on top of that guarantee,
    swallowing anything unexpected (a bad import, an unexpected _skill shape)
    so a telemetry write can never surface past this function."""
    if not fired:
        return
    try:
        shared = Path(__file__).resolve().parent.parent.parent / "_shared"
        if str(shared) not in sys.path:
            sys.path.insert(0, str(shared))
        import activation_trace
        seen: set[str] = set()
        for probe in fired:
            skill = probe.get("_skill")
            if not skill or skill in seen:
                continue
            seen.add(skill)
            activation_trace.record_activation(None, {
                "skill": skill, "phase": "trigger_matched", "source": "live",
            })
    except Exception as e:
        log_err(f"activation-trace-fail err={e!r}")


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
    return _normalize_events(events)


def recent_assistant_messages(events: list[dict], n: int) -> list[dict]:
    """Return up to n most-recent assistant text-content messages, oldest-first.
    Each: {"text": "...", "uuid": "...", "timestamp": "..."}."""
    out: list[dict] = []
    for event_index in range(len(events) - 1, -1, -1):
        e = events[event_index]
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
            "event_index": event_index,
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


_FAILED_RESULT_RE = re.compile(
    r"(?:^|\n)\s*(?:FAILED\b|ERROR\b|Traceback\b)|"
    r"(?:exit (?:code )?[1-9]\d*|\b[1-9]\d* failed\b|permission denied)",
    re.IGNORECASE,
)
_MUTATING_TOOL_NAMES = {"Edit", "Write", "NotebookEdit", "apply_patch"}
_MUTATING_COMMAND_RE = re.compile(
    r"(?i)(?:\bapply_patch\b|\bsed\s+-i\b|\b(?:rm|mv|cp|mkdir|touch|chmod)\b|"
    r"\bgit\s+(?:commit|merge|rebase|cherry-pick|add|reset|restore|clean)\b|\b(?:npm|pnpm|yarn|pip)\s+install\b|"
    # (`git mv` / `git rm` are already caught by the bare-word mv/rm branch
    # above; reset/restore/clean rewrite the tree with no bare-word anchor —
    # a check run BEFORE one is stale evidence. audit F6)
    # Interpreter-mediated file writes (2026-07-18 audit F6): a one-liner like
    # `python3 -c "open('x','w').write(...)"` mutates the tree without any of
    # the shell shapes above. Conservative: the interpreter flag PLUS a
    # write-shaped call later in the same command (the span crosses `;` —
    # one-liners chain statements with it — but not `&` / `|` / newline);
    # stdout/stderr writes excluded.
    r"\bpython[0-9.]*\s+-c\b[^&|\n]*(?:\bopen\s*\([^)]*['\"]\s*[wax]b?\+?\s*['\"]|"
    r"(?<!\.stdout)(?<!\.stderr)\.write(?:_text|_bytes)?\s*\(|"
    r"\bshutil\.(?:copy2?|move)\s*\(|\bos\.(?:remove|unlink|rename|replace|makedirs?|rmdir)\s*\()|"
    r"\bperl\s+-[A-Za-z]*e\b[^&|\n]*(?:\bopen\s*\([^)]*['\"]\s*>>?|"
    r"\b(?:unlink|rename|mkdir|syswrite)\s*\(?)|"
    r"\bnode\s+-e\b[^&|\n]*\bfs\.(?:writeFile|appendFile|unlink|rename|mkdir|rm|copyFile|"
    r"createWriteStream)(?:Sync)?\s*\(|"
    r"(?:^|[;&|]\s*)[^\n]*?(?:>>?|\btee\b)\s*[^&|;]+)"
)


def _command_from_input(inp: dict) -> str:
    return str(inp.get("command") or inp.get("cmd") or "")


def _evidence_classes(name: str, inp: dict, result_text: str) -> set[str]:
    """Classify successful execution evidence conservatively by artifact type."""
    command = _command_from_input(inp).lower()
    # Class comes from the invoked tool and its input, never free-form output:
    # `echo tests pass` is not a test and a compiler mentioning "server" is not
    # live-service evidence. The paired result establishes success only.
    name_lower = name.lower()
    args = json.dumps(inp, sort_keys=True).lower()
    classes: set[str] = set()
    if re.search(
        r"(?:^|[;&|]\s*)(?:[A-Za-z_][A-Za-z0-9_]*=\S+\s+)*(?:sudo\s+)?"
        r"(?:pytest|python\S*\s+-m\s+pytest|"
        r"python\S*\s+(?:[^;&|\s]+/)?(?:check|test)[A-Za-z0-9_.-]*\.py|"
        r"\./(?:[^;&|\s]+/)?(?:check|test)[A-Za-z0-9_.-]*(?:\.py|\.sh)?|"
        r"npm\s+(?:run\s+)?(?:test|build|lint)|pnpm\s+(?:test|build|lint)|"
        r"yarn\s+(?:test|build|lint)|make\s+(?:check|test|build|lint)|"
        r"cargo\s+(?:test|build|clippy)|go\s+(?:test|build))\b",
        command,
    ):
        classes.add("test/build")
    if name_lower in {"read", "view_file"} or re.search(
        r"(?:^|[;&|]\s*)(?:git\s+(?:diff|status)|stat|ls|find|rg|grep|"
        r"shasum|sha256sum)\b", command
    ):
        classes.add("filesystem/diff")
    if re.search(r"(?:^|[;&|]\s*)(?:curl|wget)\b", command):
        classes.add("live service")
    if (re.search(r"(?:screenshot|view_image|take_screenshot|preview)", name_lower)
            or (name_lower in {"read", "view_file"}
                and re.search(r"\.(?:png|jpe?g|svg|pdf)(?:\b|\")", args))):
        classes.add("visual")
    return classes


def execution_timeline(events: list[dict]) -> dict:
    """Correlate tool uses with results and derive mutation/evidence ordering.

    A typed command is never evidence: only a tool_use with its matching,
    successful tool_result is returned. Event indexes make the post-mutation
    freshness rule independent of unreliable/missing timestamps.
    """
    uses: dict[str, dict] = {}
    results: dict[str, dict] = {}
    last_mutation = -1
    for event_index, event in enumerate(events):
        msg = event.get("message") or {}
        content = msg.get("content")
        if not isinstance(content, list):
            continue
        if event.get("type") == "assistant":
            for block in content:
                if not isinstance(block, dict) or block.get("type") != "tool_use":
                    continue
                name = str(block.get("name") or "")
                inp = block.get("input") or {}
                tid = str(block.get("id") or "")
                mutates = name in _MUTATING_TOOL_NAMES
                if name == "Bash" and _MUTATING_COMMAND_RE.search(_command_from_input(inp)):
                    mutates = True
                if mutates:
                    last_mutation = max(last_mutation, event_index)
                if tid:
                    uses[tid] = {"name": name, "input": inp, "use_index": event_index}
        elif event.get("type") == "user":
            for block in content:
                if not isinstance(block, dict) or block.get("type") != "tool_result":
                    continue
                tid = str(block.get("tool_use_id") or "")
                if tid:
                    results[tid] = {
                        "result_index": event_index,
                        "text": _tool_result_text(block.get("content")),
                        "is_error": bool(block.get("is_error")),
                    }
    evidence: list[dict] = []
    for tid, use in uses.items():
        result = results.get(tid)
        if not result or result["is_error"] or _FAILED_RESULT_RE.search(result["text"]):
            continue
        classes = _evidence_classes(use["name"], use["input"], result["text"])
        if classes:
            evidence.append({**use, **result, "classes": classes})
    return {"last_mutation_index": last_mutation, "evidence": evidence}


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


def recent_bash_tool_results(events: list[dict], n: int = 10) -> list[dict]:
    """Return up to n most-recent Bash tool_use blocks PAIRED with their
    tool_result (correlated by `tool_use_id`), oldest-first. Each:
    {"command": str, "result_text": str, "is_error": bool|None, "has_result": bool}.

    Mechanism 4's bank-resolver needs EXECUTION EVIDENCE, not just invocation
    shape (adversarially confirmed: `CMD="...write_gate.py gate..."` — a bare
    variable assignment — and `false && python3 .../write_gate.py gate ...` — a
    short-circuited command — both present a matching command STRING while
    never actually running the tool; text-only matching cannot tell the
    difference). This walks assistant tool_use blocks (which carry `id` in a
    real transcript) and the following user-event tool_result blocks (which
    carry the same id as `tool_use_id`) to attach the ACTUAL output each Bash
    call produced — same shape mechanism-3-style detectors already read via
    `recent_tool_uses`/`recent_tool_errors`, just correlated by id instead of
    scanned independently. `has_result=False` means no tool_result was found
    in this transcript window for that tool_use (e.g. it's still running, or
    fell outside the tail cap) — callers must treat that as "no evidence",
    never as an error."""
    tool_uses: list[tuple[str, dict]] = []  # (id, {"command":...})
    results_by_id: dict[str, dict] = {}
    for e in events:
        msg = e.get("message") or {}
        content = msg.get("content")
        if not isinstance(content, list):
            continue
        if e.get("type") == "assistant":
            for b in content:
                if isinstance(b, dict) and b.get("type") == "tool_use" and b.get("name") == "Bash":
                    inp = b.get("input") or {}
                    tid = b.get("id")
                    if tid:
                        tool_uses.append((tid, {"command": str(inp.get("command", ""))}))
        elif e.get("type") == "user":
            for b in content:
                if isinstance(b, dict) and b.get("type") == "tool_result":
                    tid = b.get("tool_use_id")
                    if tid:
                        results_by_id[tid] = {
                            "result_text": _tool_result_text(b.get("content")),
                            "is_error": bool(b.get("is_error")),
                        }
    out: list[dict] = []
    for tid, tu in tool_uses[-n:] if len(tool_uses) > n else tool_uses:
        r = results_by_id.get(tid)
        if r is None:
            out.append({"command": tu["command"], "result_text": "", "is_error": None, "has_result": False})
        else:
            out.append({"command": tu["command"], "result_text": r["result_text"],
                        "is_error": r["is_error"], "has_result": True})
    return out[-n:]


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


def _claim_evidence_class(text: str, probe: dict) -> str:
    explicit = probe.get("evidence_class")
    if explicit in {"test/build", "filesystem/diff", "live service", "visual"}:
        return explicit
    if re.search(r"(?i)\b(visual|looks?|render|screenshot|layout|aligned|legible|image|pdf|slide|ui)\b", text):
        return "visual"
    if re.search(r"(?i)\b(live|deployed|service|server|endpoint|website|responding|reachable)\b", text):
        return "live service"
    if re.search(r"(?i)\b(test|tests|build|lint|check|passes|passing|green)\b", text):
        return "test/build"
    return "filesystem/diff"


_HAYSTACK_DQUOTE_RE = re.compile(r'"(?:\\.|[^"\\])*"', re.S)
_HAYSTACK_SQUOTE_RE = re.compile(r"'(?:\\.|[^'\\])*'", re.S)


def _strip_quoted_args(cmd: str) -> str:
    """Strip double/single-quoted STRING CONTENTS from a Bash command before
    scanning verify_keywords — a keyword landing only inside a quoted
    argument (e.g. the commit MESSAGE of `git commit -m "render this PR
    obsolete, closing"`) is ordinary English inside a string literal, not
    evidence the command actually invoked a verification tool (red-team
    2026-07-11: this decoy shape defeated all 8 claim_without_evidence
    probes in the catalog via each probe's own keyword list). Applied only
    to the Bash `command` string on the legacy keyword-scan path."""
    cmd = _HAYSTACK_DQUOTE_RE.sub(" ", cmd)
    cmd = _HAYSTACK_SQUOTE_RE.sub(" ", cmd)
    return cmd


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
    try:
        lookback = int(probe.get("lookback_tool_uses", 5))
    except (TypeError, ValueError):
        log_err(f"bad-lookback probe={probe.get('_probe_id')} value={probe.get('lookback_tool_uses')!r}")
        lookback = 5
    if (traj_stats or {}).get("profile") == "legacy":
        verify_tools = set(probe.get("verify_tools", ["Bash"]))
        keywords = [str(k).lower() for k in probe.get("verify_keywords", [])]
        verify_re = (re.compile(r"\b(" + "|".join(re.escape(k) for k in keywords) + r")\b")
                     if keywords else None)
        for tool_use in tool_uses[-lookback:]:
            if tool_use.get("name") not in verify_tools:
                continue
            inp = tool_use.get("input") or {}
            haystack = (_strip_quoted_args(_command_from_input(inp)) if tool_use.get("name") == "Bash"
                        else json.dumps(inp)).lower()
            if verify_re is not None and verify_re.search(haystack):
                return None
    evidence_class = _claim_evidence_class(last_text, probe)
    timeline = (traj_stats or {}).get("execution_timeline", {})
    last_mutation = _as_int(timeline.get("last_mutation_index"), -1)
    claim_index = _as_int(messages[-1].get("event_index"), 1 << 30)
    candidates = timeline.get("evidence", [])[-lookback:]
    for evidence in candidates:
        result_index = _as_int(evidence.get("result_index"), -1)
        if result_index <= last_mutation or result_index >= claim_index:
            continue
        if evidence_class in evidence.get("classes", set()):
            return None
    return {
        "claim": claim_match.group(0),
        "snippet": last_text[max(0, claim_match.start() - 20): claim_match.end() + 40].replace("\n", " "),
        "lookback": lookback,
        "evidence_class": evidence_class,
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


# ---- verbatim intent log (L0 capture side of the no-drop guarantee) ---------
# docs/TARGET_ARCHITECTURE.md L0 "Intent log": every user-AUTHORED prompt,
# verbatim, append-only — zero LLM, zero injected bytes. "User-authored" is
# decided by harness-block stripping: a turn whose remainder is EMPTY (pure
# notification / command transcript) writes no record; a turn with ANY
# remainder captures the user-authored text verbatim — and when the prompt
# carries a pasted <task-notification> block (the object of the user's ask),
# the pasted block is preserved with it (F4, 2026-07-18 audit) while
# always-mechanical command/system transcripts are still stripped
# (intent_capture_text). One capture, several consumers: TODAY the wrap-up pending-intent
# surface quotes from it (build_ledger_lines); PLANNED close-boundary
# reconciliation maps every captured intent to satisfied / deferred /
# uncovered. Standing user directive: capture has NO opt-out flag —
# frontier/shadow/legacy all capture. Two exceptions: profile `off` (the
# experimental control arm) exits before ANY mutation, so it writes no
# records; and the whole-hook COMPLIANCE_CANARY_DISABLED valve suppresses
# capture like every other mechanism (F5c, 2026-07-18 audit — the request
# LEDGER is the sole record that stays ahead of the valve). Hygiene riders
# (F5, same audit): key-like strings are scrubbed by the shared secret
# redactor before writing (the sole verbatim exception), intent logs age out
# on the same 7-day GC horizon as state files, and a missing session id gets
# a timestamped fallback name instead of a shared unknown.jsonl. Best-effort:
# any failure logs to stderr and never blocks the hook (the always-exit-0
# contract).


def intent_dir() -> Path:
    # Sibling of the canary state dir: <base>/.brainer/intent by default
    # (.brainer/ is git-ignored); a COMPLIANCE_CANARY_STATE_DIR override
    # redirects it as a sibling, so test/sandbox isolation holds.
    return state_dir().parent / "intent"


def intent_log_path(session_id: str) -> Path:
    # Literal <session_id>.jsonl, with path-hostile characters flattened so a
    # garbage session id can never escape the intent dir.
    safe = re.sub(r"[^A-Za-z0-9._-]", "_", session_id or "")
    if not safe:
        # F5d (2026-07-18 audit): NO unknown.jsonl co-mingling — a missing
        # session id gets a timestamped (+pid) fallback so anonymous sessions
        # never share one append target. main() passes the RAW (possibly
        # empty) id through, so this fallback actually fires (R2-1). Without
        # a stable id there is no read-back either — wrap-up quoting falls
        # back to ledger text, best-effort.
        safe = "unknown-" + time.strftime("%Y%m%dT%H%M%SZ", time.gmtime()) + f"-{os.getpid()}"
    return intent_dir() / f"{safe}.jsonl"


def _scrub_intent_text(text: str) -> str | None:
    """F5b (2026-07-18 audit): run the shared secret scrubber
    (skills/_shared/audit_redact.py, key-like strings ONLY —
    `redact_secrets`, not the path-rewriting `redact`) over the prompt
    before it hits disk. This is the SOLE exception to the verbatim rule:
    credential-shaped strings never persist. Returns None on ANY scrubber
    failure (R2-2: secrets must never reach disk on ANY path, so a failed
    scrubber must never fall back to storing the raw text — the caller
    persists the "[REDACTION-FAILED]" placeholder plus the ORIGINAL text's
    hash instead, keeping an integrity anchor without the bytes)."""
    try:
        shared = Path(__file__).resolve().parent.parent.parent / "_shared"
        if str(shared) not in sys.path:
            sys.path.insert(0, str(shared))
        import audit_redact
        return audit_redact.redact_secrets(text)
    except Exception as e:
        log_err(f"intent-redact-fail err={e!r}")
        return None


# Blocks that are ALWAYS mechanical harness transcripts, never user-authored
# content — stripped from intent capture even when the user authored the
# surrounding text. A <task-notification> is the ONE block kind that can be
# user-PASTED content (the object of an ask) — it is preserved (F4).
_INTENT_MECHANICAL_BLOCK_RE = re.compile(
    r"<(local-command-caveat|local-command-stdout|local-command-stderr|"
    r"command-name|command-message|command-args|system-reminder)>.*?</\1>",
    re.S,
)


def intent_capture_text(prompt_text: str, prompt_text_user: str) -> str:
    """F4 (2026-07-18 audit): decide what the verbatim intent log stores.
    An empty user remainder (a pure harness-notification turn) stores
    nothing. A turn whose prompt carries a CLOSED <task-notification> block
    inside otherwise organic user text treats the block as USER-PASTED
    content — the literal subject of the ask ("what does this mean?") —
    and keeps it, stripping only the always-mechanical command/system
    transcripts. Any other turn stores the stripped user-authored
    remainder (pre-audit behavior). Ambiguity errs toward preserving the
    user's literal text."""
    if not prompt_text_user:
        return ""
    if _TASK_NOTIFICATION_BLOCK_RE.search(prompt_text or ""):
        return _INTENT_MECHANICAL_BLOCK_RE.sub("", prompt_text or "")
    if not (_HARNESS_BLOCK_RE.search(prompt_text or "")
            or _HARNESS_OPEN_RE.search(prompt_text or "")):
        # No harness content anywhere: the raw prompt IS the user's text —
        # store it byte-identical (the stripped remainder loses outer
        # whitespace, breaking the verbatim guarantee; R3-1).
        return prompt_text or ""
    return prompt_text_user


def capture_intent(session_id: str, turn: int, user_text: str) -> bool:
    """Append one user-authored prompt to the session's intent log, VERBATIM
    (full-length, whitespace intact — the .strip() below only DECIDES
    emptiness, it never edits what is persisted; R2-3). An empty remainder
    (a pure harness-notification turn) writes no record. The ONE verbatim
    exception: key-like strings are scrubbed by the shared secret redactor
    before writing (F5b; the sha256 anchors the stored, scrubbed text). On
    scrubber failure the record degrades to the "[REDACTION-FAILED]"
    placeholder with the sha256 anchoring the ORIGINAL text (R2-2) — raw
    text never reaches disk on any path. NEVER raises — capture is
    best-effort and must not block the user's prompt."""
    text = user_text or ""
    if not text.strip():
        return False
    scrubbed = _scrub_intent_text(text)
    if scrubbed is None:
        record = {
            "turn": turn,
            "ts": time.strftime("%FT%TZ", time.gmtime()),
            "sha256": hashlib.sha256(text.encode("utf-8", errors="replace")).hexdigest(),
            "text": "[REDACTION-FAILED]",
        }
    else:
        record = {
            "turn": turn,
            "ts": time.strftime("%FT%TZ", time.gmtime()),
            "sha256": hashlib.sha256(scrubbed.encode("utf-8", errors="replace")).hexdigest(),
            "text": scrubbed,
        }
    try:
        path = intent_log_path(session_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "a", encoding="utf-8") as handle:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            handle.write(json.dumps(record) + "\n")
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        return True
    except Exception as e:
        log_err(f"intent-capture-fail err={e!r}")
        return False


def read_intent_turn_texts(session_id: str) -> dict[int, str]:
    """{turn: verbatim text} from the session's intent log. Best-effort: a
    missing/unreadable file or a torn trailing line degrades quietly (never
    raises) — the caller falls back to ledger state text."""
    out: dict[int, str] = {}
    try:
        path = intent_log_path(session_id)
        if not path.is_file():
            return out
        with open(path, "r", encoding="utf-8", errors="replace") as handle:
            for line in handle:
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if not isinstance(obj, dict):
                    continue
                text = obj.get("text")
                if isinstance(text, str) and text:
                    out[_as_int(obj.get("turn"), -1)] = text
    except OSError as e:
        log_err(f"intent-read-fail err={e!r}")
    out.pop(-1, None)
    return out


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

# Harness-injected content is NOT user intent. Task-notifications, slash-command
# transcripts, and system-reminders arrive on the UserPromptSubmit channel but
# were not typed by the user — capturing them pollutes the ledger with
# non-requests (observed live: background-agent notifications resurfacing as
# "open user requests" every turn) and lets prompt_intent probes misfire on
# notification text. STRIP the blocks and keep any user-authored remainder —
# skipping the whole prompt would itself drop a real ask appended after a
# local-command block (the exact failure the ledger exists to prevent).
_HARNESS_BLOCK_RE = re.compile(
    r"<(task-notification|local-command-caveat|local-command-stdout|"
    r"local-command-stderr|command-name|command-message|command-args|"
    r"system-reminder)>.*?</\1>",
    re.S,
)
# An unterminated harness block (truncated notification) swallows the tail —
# these two kinds are never followed by user-authored text.
_HARNESS_OPEN_RE = re.compile(r"<(?:task-notification|system-reminder)>.*\Z", re.S)


def strip_harness_injected(text: str) -> str:
    """Remove harness-injected blocks; return the user-authored remainder."""
    out = _HARNESS_BLOCK_RE.sub("", text or "")
    out = _HARNESS_OPEN_RE.sub("", out)
    return out.strip()


# ---- task-notification evidence boundary (frontier/shadow only) -------------
# A harness <task-notification> arrives on the UserPromptSubmit channel. When
# it reports a TERMINAL SUCCESS for a self-contained substrate job kind (timer
# wakeup / background command / advisor consult), the notification IS the
# evidence boundary for this turn: the agent authored no claim here, so scoring
# its prior prose against claim_without_evidence false-fires (2/2 live field
# FPs, 2026-07-18 review). The predicate is deliberately NARROW and FAIL-OPEN —
# every condition must POSITIVELY match; anything ambiguous (delegate prose
# quoting a notification, a user ask riding along, a failed/killed job, an
# unrecognized job kind, world-state assertion prose) leaves the probe surface
# untouched. Marker shape confirmed against live transcripts:
#   <task-notification><task-id>…</task-id><tool-use-id>…</tool-use-id>
#   <output-file>…</output-file><status>completed</status>
#   <summary>Background command "…" completed (exit code 0)</summary>
#   [<result>…</result>]</task-notification>
# Hardened 2026-07-19 (two adversarial sense-checks):
#   D1 — suppression DEFERS, never destroys: the suppressed probe is still
#        EVALUATED; a would-have-fired is persisted as a `deferred_fires`
#        state marker and emitted once on the next non-notification turn,
#        regardless of message-window slide (see main()).
#   D2 — provenance: suppression additionally requires the notification's
#        task-id to be ≥6 chars AND to appear inside tool_use input,
#        tool_result content, or a substrate-announcement event ANYWHERE in
#        the full transcript file (notification_task_id_provenanced); a
#        pasted, syntactically valid fake — or a one-char id like "0" that
#        matches incidental substrings — has no such anchor and fails open
#        (the turn fires as before).
# Hardened 2026-07-18 (lane A3, adversarial audit — fail-open throughout):
#   F1 — provenance entropy + source floor: the D2 lookup requires a ≥6-char
#        task-id found in tool/substrate content of the FULL transcript file
#        (not the 400-line tail, not arbitrary user/assistant prose) — closes
#        both the `<task-id>0</task-id>` bypass and the legit-announcement-
#        500-lines-ago false fire.
#   F2 — a pending deferred_fire marker survives at most ONE qualifying-
#        notification turn: a second qualifying notification while a marker
#        is pending emits it that turn anyway (a notification flood cannot
#        destroy a fire). At emission, freshness is re-checked: matching
#        successful evidence appearing AFTER the original claim drops the
#        marker silently instead of emitting (no stale nag).
#   F3 — pending_content clears only on evidence of an actual READ (full
#        path, or basename + parent-dir substring in the same event, in a
#        tool_use input or non-error tool_result whose command/content shows
#        no rm/unlink/rmdir); destruction never clears; unresolved entries
#        surface at wrap-up independent of request-ledger state.
_TASK_NOTIFICATION_BLOCK_RE = re.compile(r"<task-notification>(.*?)</task-notification>", re.S)
_TASK_NOTIFICATION_TAG_RES = {
    tag: re.compile(rf"<{tag}>(.*?)</{tag}>", re.S)
    for tag in ("task-id", "tool-use-id", "output-file", "status", "summary", "result")
}
_NOTIFICATION_SUCCESS_STATUS = {"completed", "complete", "succeeded", "success", "ok"}
_NOTIFICATION_FAILURE_STATUS = {"failed", "failure", "error", "errored", "killed",
                                "timed out", "timeout", "cancelled", "canceled", "aborted"}
_NOTIFICATION_SUCCESS_RE = re.compile(r"(?i)\bexit code 0\b")
_NOTIFICATION_FAILURE_RE = re.compile(r"(?i)\bexit code [1-9]\d*\b")
# Allowlisted self-contained job kinds, matched on the summary's LEADING label
# (the substrate's own job-type marker). Anything unlisted — e.g. `Dynamic
# workflow "…"` (an implementation subagent) — is unclassified → no suppression.
_NOTIFICATION_KIND_RES = (
    ("timer", re.compile(r"(?i)^\s*(?:timer|reminder|alarm|wake-?up|scheduled wakeup)\b")),
    ("background-command", re.compile(r"(?i)^\s*background (?:command|task|job|process)\b")),
    ("advisor", re.compile(r"(?i)^\s*(?:advisor(?:\s+consult)?|consult(?:ation)?)\b")),
)
# The substrate's own terminal-status vocabulary, removed before scanning the
# notification's prose for world-state assertions — the `… completed (exit
# code 0)` wrapper IS the status report, never a claim.
_NOTIFICATION_STATUS_WORDS_RE = re.compile(
    r"(?i)\bcompleted\b|\bsucceeded\b|\bsuccessfully\b|\bfinished\b|\bfailed\b|"
    r"\bexit code \d+\b|\(exit code \d+\)")
# World-state ASSERTION prose (the forwarded-subagent-claim shape: "files
# moved", "tests pass", "DONE", "READY FOR JUDGING"). Present anywhere in the
# notification's own prose → the evidence gate stays armed. Broadened
# 2026-07-18 (audit F6) to passive/rephrased forms — "files were moved",
# "checks green", "uploaded", "deployed", "deleted" — while timer/advisor
# status prose (stripped above: completed/exit code N) stays unmatched.
_NOTIFICATION_WORLD_STATE_RE = re.compile(
    r"(?i)\bfiles? (?:were |was |are |is |have been |has been |got |being )?"
    r"(?:moved|created|deleted|written|updated|renamed|copied|modified|uploaded)\b|"
    r"\b(?:tests?|checks?) (?:pass|passed|passing|green|succeeded)\b|"
    r"\b(?:were|was|have been|has been|got) (?:moved|created|deleted|written|updated|"
    r"renamed|copied|modified|uploaded|deployed)\b|"
    r"\bready for judging\b|"
    r"\b(?:done|fixed|verified|shipped|deployed|merged|committed|uploaded|deleted)\b")
NOTIFICATION_PENDING_CAP = 20  # bound state-file growth of pointer-only records
# F1 provenance entropy floor: a task-id shorter than this matches incidental
# substrings everywhere ("0" rides every "exit code 0") and proves nothing.
MIN_NOTIFICATION_TASK_ID_LEN = 6


def _task_id_low_entropy(task_id: str) -> bool:
    """F1 entropy floor: True when a task-id is too predictable to anchor
    provenance even at sufficient length — all-same-char ("000000",
    "aaaaaa"), a <3-distinct-char repetition ("ababab", "010101"), or a
    trivial monotone sequence ("123456", "abcdef", "987654"). These
    collide with incidental substrings in arbitrary transcripts, so finding
    one "in the transcript" proves nothing either."""
    if len(set(task_id)) <= 2:
        return True
    low = task_id.lower()
    for seq in ("0123456789", "abcdefghijklmnopqrstuvwxyz"):
        if low in seq or low in seq[::-1]:
            return True
    deltas = {ord(b) - ord(a) for a, b in zip(low, low[1:])}
    if len(deltas) == 1 and (1 in deltas or -1 in deltas):
        return True
    return False


def _notification_tag(body: str, tag: str) -> str:
    m = _TASK_NOTIFICATION_TAG_RES[tag].search(body)
    return m.group(1).strip() if m else ""


def notification_suppression_decision(prompt_text: str, prompt_text_user: str) -> dict:
    """Classify the current UserPromptSubmit payload for the notification
    evidence boundary. FAIL-OPEN by construction: every condition must
    POSITIVELY match, else ``active`` stays False and the turn is scored
    exactly as before. Suppression requires ALL of:
      (a) substrate-SHAPED — no user-authored remainder after harness
          stripping, exactly one CLOSED <task-notification> block, with a
          task-id (delegate prose quoting a notification, or a real ask
          riding along → out). Syntax alone CANNOT distinguish a substrate
          event from a pasted, syntactically valid fake — this function does
          NOT establish provenance. The caller MUST also require
          ``notification_task_id_provenanced`` (a ≥6-char task-id found in
          tool_use/tool_result/substrate-announcement content of the FULL
          transcript file) before acting on ``active``; id absent there →
          no suppression, the turn fires exactly as before;
      (b) terminal SUCCESS — completed-class status / exit code 0, with no
          failure signal anywhere;
      (c) allowlisted self-contained job kind — timer wakeup, background
          command, or advisor consult — and NO world-state assertion prose in
          the notification's own text (an implementation subagent's "files
          moved / tests pass / DONE / READY FOR JUDGING" keeps the gate armed:
          that forwarded claim is the guard's one proven live catch);
      (d) the notification carries its own result content or an output-file
          pointer (pointer-only → the caller records a pending_content entry).
    """
    decision = {"active": False, "kind": "", "pointer_only": False,
                "output_file": "", "recorded_iso": "", "task_id": ""}
    try:
        if prompt_text_user:
            return decision
        blocks = _TASK_NOTIFICATION_BLOCK_RE.findall(prompt_text or "")
        if len(blocks) != 1:
            return decision
        body = blocks[0]
        task_id = _notification_tag(body, "task-id")
        if not task_id:
            return decision
        status = _notification_tag(body, "status").lower()
        summary = _notification_tag(body, "summary")
        result = _notification_tag(body, "result")
        success = status in _NOTIFICATION_SUCCESS_STATUS or bool(
            _NOTIFICATION_SUCCESS_RE.search(summary))
        failure = (status in _NOTIFICATION_FAILURE_STATUS
                   or bool(_NOTIFICATION_FAILURE_RE.search(summary)))
        if not success or failure:
            return decision
        kind = next((name for name, rx in _NOTIFICATION_KIND_RES if rx.search(summary)), "")
        if not kind:
            return decision
        prose = _NOTIFICATION_STATUS_WORDS_RE.sub(" ", summary + "\n" + result)
        if _NOTIFICATION_WORLD_STATE_RE.search(prose):
            return decision
        output_file = _notification_tag(body, "output-file")
        if not result and not output_file:
            return decision
        decision.update({
            "active": True,
            "kind": kind,
            "pointer_only": not result and bool(output_file),
            "output_file": output_file,
            "recorded_iso": time.strftime("%FT%TZ", time.gmtime()),
            "task_id": task_id,
        })
    except Exception as e:  # fail-open on any classification error
        log_err(f"notification-classify-fail err={e!r}")
    return decision


def _task_id_in_tool_or_substrate_content(event: dict, task_id: str) -> bool:
    """True iff `task_id` rides tool/substrate content of ONE (normalized)
    transcript event: a tool_use input, a tool_result body, or an event the
    substrate itself authored (a non-user/assistant record, e.g. a system
    event). Text blocks inside user/assistant events are PROSE — a user
    typing "check on task abc123", an agent quoting an id, or a pasted fake
    replayed into the transcript as a user message is NOT provenance."""
    msg = event.get("message") or {}
    content = msg.get("content")
    if isinstance(content, list):
        for b in content:
            if not isinstance(b, dict):
                continue
            if b.get("type") == "tool_use":
                try:
                    if task_id in json.dumps(b.get("input") or {}, ensure_ascii=False):
                        return True
                except (TypeError, ValueError):
                    continue
            elif b.get("type") == "tool_result":
                if task_id in _tool_result_text(b.get("content")):
                    return True
    if event.get("type") not in ("user", "assistant"):
        try:
            if task_id in json.dumps(event, ensure_ascii=False):
                return True
        except (TypeError, ValueError):
            pass
    return False


def notification_task_id_provenanced(transcript_path: str, task_id: str) -> bool:
    """F1 mechanical provenance (fail-open). True iff `task_id` is at least
    MIN_NOTIFICATION_TASK_ID_LEN chars AND appears inside tool_use input,
    tool_result content, or a substrate-announcement event ANYWHERE in the
    FULL transcript file. Three audit fixes over the tail-scan original: the
    length floor kills the `<task-id>0</task-id>` bypass (a one-char id
    matches incidental substrings in every transcript), the entropy floor
    kills its longer siblings ("000000" / "123456" — the same incidental-
    collision class), and the whole-file scan (not the 400-line tail) keeps a
    legit notification whose substrate announcement scrolled past the tail
    from false-firing. Cheap: one whole-file read with a substring prefilter
    — only lines containing the id are parsed, and only their tool/substrate
    content is inspected."""
    if (not task_id or len(task_id) < MIN_NOTIFICATION_TASK_ID_LEN
            or _task_id_low_entropy(task_id)):
        return False
    p = Path(transcript_path or "")
    if not p.is_file():
        return False
    try:
        # Streaming line iteration — never materializes the whole transcript
        # (long sessions are exactly where this path runs; R3-4).
        with open(p, encoding="utf-8", errors="replace") as handle:
            for line in handle:
                if task_id not in line:
                    continue
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if not isinstance(obj, dict):
                    continue
                try:
                    candidates = _normalize_events([obj])
                except Exception:
                    candidates = [obj]
                for cand in candidates:
                    if isinstance(cand, dict) and _task_id_in_tool_or_substrate_content(cand, task_id):
                        return True
    except OSError as e:
        log_err(f"transcript-read-fail path={transcript_path} err={e!r}")
        return False
    return False


# F3 (2026-07-18 audit, round 1): pending_content reconciles ONLY on an
# actual READ of the output file — a Read/view tool_use, or a Bash
# content-DISPLAY command (cat/head/tail/grep/…), whose PAIRED tool_result
# is present and non-error (a failed Read shows no content). Destruction
# never reconciles: `rm`/`mv`/`delete` on the pending file must not clear
# the entry (audit: destruction falsely cleared it), and neither does an
# Edit/Write or an interpreter write — overwriting the unread output is not
# reading it.
_DELETION_TOKEN_RE = re.compile(
    r"(?i)\b(?:rm|rmdir|unlink|mv|move|del|delete|trash|shred|truncate)\b")
# Result-side destruction markers (a verbose rm/mv reports "removed '…'" /
# "renamed '…' -> '…'" with no rm token in the result text itself).
_DELETION_RESULT_RE = re.compile(
    r"(?i)\b(?:removed|deleted|renamed|moved|trashed|unlinked)\b")
# Content-DISPLAY commands (a read whose output the agent actually sees).
# Interpreter names qualify only for non-mutating one-liners — the
# _MUTATING_COMMAND_RE guard below excludes `python3 -c "open(…,'w')…"` and
# friends. In-place flags (sed -i, perl -i) mutate without displaying.
_READ_COMMAND_RE = re.compile(
    r"(?i)(?:^|[;&|]\s*)(?:[A-Za-z_][A-Za-z0-9_]*=\S+\s+)*(?:sudo\s+)?"
    r"(?:cat|head|tail|less|more|bat|nl|grep|egrep|fgrep|rg|awk|gawk|jq|"
    r"xxd|od|column|sed|perl|python[0-9.]*|ruby|node)\b")
_INPLACE_FLAG_RE = re.compile(r"(?i)(?:^|\s)-i(?:\s|$)")
_READ_TOOL_NAMES = {"read", "view", "view_file"}


def _path_matches_event_text(hay: str, out_path: str, base: str, parent: str) -> bool:
    """Full path, OR basename together with the containing dir's name in the
    SAME text — the `cd <dir> && cat <file>` relative-read shape (F3b: a
    genuine relative read must reconcile; a bare basename never matches —
    it collides across dirs)."""
    if out_path and out_path in hay:
        return True
    return bool(parent and base and base in hay and parent in hay)


def _notification_output_read(events: list[dict], out_path: str) -> bool:
    """F3 read-detection: True iff the transcript shows an actual READ of
    `out_path` — read-shaped tool events ONLY (a Read/view tool_use, or a
    Bash content-display command), credited only when the tool_use's PAIRED
    tool_result is observed and non-error (a failed Read is not a read).
    Destruction (rm/mv/delete), mutation (Edit/Write, interpreter writes,
    redirects, in-place sed/perl), failed reads, and bare basenames never
    clear the entry."""
    if not out_path:
        return False
    base = out_path.rsplit("/", 1)[-1]
    parent = out_path.rsplit("/", 2)[-2] if out_path.count("/") >= 2 else ""
    # Pass 1: pair tool_use ids with their result status — a read-shaped use
    # counts only when its paired result exists in-window and is not an error.
    result_ok: dict[str, bool] = {}
    for e in events or []:
        msg = e.get("message") or {}
        content = msg.get("content")
        if not isinstance(content, list):
            continue
        for b in content:
            if isinstance(b, dict) and b.get("type") == "tool_result":
                tid = str(b.get("tool_use_id") or "")
                if tid:
                    result_ok[tid] = not b.get("is_error")
    for e in events or []:
        msg = e.get("message") or {}
        content = msg.get("content")
        if not isinstance(content, list):
            continue
        for b in content:
            if not isinstance(b, dict):
                continue
            if b.get("type") == "tool_use":
                tid = str(b.get("id") or "")
                if not result_ok.get(tid, False):
                    continue  # no paired successful result — not an actual read
                inp = b.get("input") or {}
                name = str(b.get("name") or "")
                command = str(inp.get("command") or inp.get("cmd") or "")
                if name == "Bash":
                    if (_DELETION_TOKEN_RE.search(command)
                            or _INPLACE_FLAG_RE.search(command)
                            or _MUTATING_COMMAND_RE.search(command)):
                        continue
                    if not _READ_COMMAND_RE.search(command):
                        continue
                    matched = _path_matches_event_text(command, out_path, base, parent)
                elif name.lower() in _READ_TOOL_NAMES:
                    try:
                        hay = json.dumps(inp, ensure_ascii=False)
                    except (TypeError, ValueError):
                        continue
                    matched = _path_matches_event_text(hay, out_path, base, parent)
                else:
                    continue  # Edit/Write/NotebookEdit/other: not read-shaped
                if matched:
                    return True
            # NOTE: no standalone tool_result branch — an uncorrelated result
            # merely CONTAINING the path (printf/echo/ls output) is not a
            # read; clearing correlates exclusively with a successful
            # read-shaped tool_use (R3-2).
    return False


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
    r"generate|run|review|audit|verify|score|investigate|answer|explain)\b"
)


def _ledger_make_id(turn: int, text: str) -> str:
    return f"r{turn}-" + hashlib.sha256(text.encode("utf-8", "replace")).hexdigest()[:6]


def _ledger_atomic_count(text: str) -> int:
    """Bounded hint for the visible ledger's split-conjunct task mirror."""
    return min(8, 1 + len(_LEDGER_COMPOUND_RE.findall(text)))


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
    item = {"id": _ledger_make_id(turn, p), "turn": turn,
            "text": p[:LEDGER_TEXT_CAP], "atomic_count": _ledger_atomic_count(p)}
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


def build_ledger_lines(open_items: list, closed_now: list, completion_claim: bool, turn: int,
                       intent_texts: dict[int, str] | None = None) -> list[str]:
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
            text = it.get("text", "")
            if completion_claim and intent_texts:
                # Wrap-up grounding (L0 intent log): quote the user's OWN
                # captured words for this turn — verbatim, not the ledger's
                # state mirror — truncated to the same per-item budget the
                # ledger capture used. Fall back to the ledger text when the
                # log has no record for the turn (best-effort read). The log
                # already holds exactly what should surface: selective
                # capture stripped the always-mechanical command/system
                # transcripts at write time, and a pasted notification block
                # the user asked ABOUT is preserved with the quote (F4 —
                # err toward the user's literal text, never re-strip).
                verbatim = intent_texts.get(_as_int(it.get("turn"), -1))
                if verbatim:
                    text = (verbatim[:LEDGER_TEXT_CAP - 1] + "…") if len(verbatim) > LEDGER_TEXT_CAP else verbatim
            lines.append(f"- [turn {it.get('turn','?')}] {text}")
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


# ---- Mechanism 4: correction ledger (LEARNING_CONTRACT §2) -------------------
# A user correction is closeout-blocking (skills/_shared/LEARNING_CONTRACT.md §2):
# it must become a durable artifact — rule + gate + exemplar — before the task
# closes, unconditionally (not opt-in, not "if a retrospective is armed"). This
# mirrors the request-ledger (Mechanism 3) shape exactly: every fired
# `user_correction` probe opens an OPEN item that is surfaced every turn until a
# banking tool call is observed OR the user explicitly closes it. The hook never
# judges whether the banking was GOOD — only whether a banking tool call
# happened — the same "mechanical tracker, model does the semantics" split as
# Mechanism 3.
CORRECTION_LEDGER_STORE_CAP = 50      # hard cap on stored items (bound state-file size)
CORRECTION_LEDGER_SHOW_MAX = 8        # max items surfaced in one reminder
CORRECTION_LEDGER_TEXT_CAP = 140      # chars kept per remembered correction

# A Bash call that BANKS a lesson: write-gate's score/gate/explain (the quality
# gate §2 requires before a durable write) or wiki.py new (materializing the
# durable artifact itself — `wiki.py` has no `update` subcommand; `new` is the
# only page-writing verb it exposes). Matched against the Bash `command`
# string — same detection style as `_LEDGER_MAINT_PATH_DEFAULT` above
# (path/command substring, not an AST parse) — BUT the token must be in
# COMMAND POSITION (the thing actually being invoked in a shell segment), AND
# the paired tool_result must carry an EXECUTION-EVIDENCE signature (below).
#
# HOLE #1 (adversarially confirmed, pre-fix): a bare substring match let
# `echo write_gate.py`, `wiki.py new --help`, and `grep write_gate.py x` all
# falsely RESOLVE a closeout-blocking correction — none of them ran the gate.
# Command-position invocation shape (this section) closes that hole.
#
# HOLE #2 (adversarially confirmed): invocation SHAPE alone is still
# text-trust, not execution proof — two attacks resolve a correction without
# the gate ever running:
#   (a) `CMD="python3 skills/write-gate/tools/write_gate.py gate --text x"` —
#       a bare shell variable ASSIGNMENT. The command string contains a
#       matching invocation shape, but nothing executes; `CMD` is just a
#       string sitting in an env var.
#   (b) `false && python3 .../write_gate.py gate ...` — a short-circuited
#       compound command. Splitting on `&&`/`||`/`;`/`|` (the HOLE #1 fix)
#       checks each segment independently, so the second segment still
#       "looks like" an invocation even though `&&` guarantees it never runs.
# Neither can be told apart from a genuine invocation by matching the command
# STRING — only by checking what actually happened. Fix: require the SAME
# Bash tool_use to also have a `tool_result` whose content carries a real
# write_gate.py/wiki.py execution signature (see `_WRITE_GATE_VERDICT_RE` /
# `_WIKI_NEW_CREATED_RE` / `_WIKI_NEW_REFUSED_RE` below) — invocation shape is
# still required (narrows which Bash calls we even look at), but shape alone
# no longer resolves anything.
_CORRECTION_BANK_SEGMENT_SPLIT_RE = re.compile(r"&&|\|\||[;|]")
_CORRECTION_BANK_LEADING_RE = re.compile(
    r"^\s*(?:[A-Za-z_][A-Za-z0-9_]*=\S+\s+)*(?:sudo\s+)?"
)
_CORRECTION_BANK_INVOKE_RE = re.compile(
    r"^(?:(?:python3?|bash|sh)\s+)?(?:\S*/)?"
    r"(?P<tool>write_gate\.py|wiki\.py)\b(?P<rest>.*)$"
)
_CORRECTION_BANK_HELP_RE = re.compile(r"(?:^|\s)(?:--help|-h)\b")
_CORRECTION_BANK_WIKI_SUBCMD_RE = re.compile(r"^\s*new\b")

# Execution-evidence signatures — the REAL output shapes each tool prints,
# verified by running both live (2026-07-06):
#   write_gate.py {score,gate,explain} --json  → prints a JSON object whose
#     "verdict" field is "PASSED: ..." or "REJECTED: ...".
#   write_gate.py {score,explain} (no --json)   → prints "PASSED: ..." /
#     "REJECTED: ..." as the first line.
#   write_gate.py gate (no --json, no subcommand text)  → prints NOTHING to
#     stdout, only an exit code — so `gate` alone carries no verdict signature
#     in the tool_result at all; a banking call must use `--json` or `score`/
#     `explain` for the hook to see a verdict.
#   wiki.py new (success)  → JSON with a "created": "<relative/path.md>" key.
#   wiki.py new (refused)  → JSON with a "refused": "REFUSED: ..." key.
_WRITE_GATE_VERDICT_RE = re.compile(r'(?im)(?:^|"verdict"\s*:\s*")\s*(PASSED|REJECTED):')
_WIKI_NEW_CREATED_RE = re.compile(r'"created"\s*:\s*"')
_WIKI_NEW_REFUSED_RE = re.compile(r'"refused"\s*:\s*"REFUSED:')


def _command_has_bank_invocation_shape(command: str) -> bool:
    """True iff `command` contains a shell segment that DIRECTLY invokes
    write_gate.py (any subcommand) or wiki.py new, in command position — not
    merely as a substring/argument, and not a --help/-h invocation. Necessary
    but NOT sufficient: this is invocation SHAPE only (text), narrowing which
    Bash calls are even worth checking for execution evidence. See
    `_bash_call_banks_correction` for the full (shape + evidence) gate."""
    for segment in _CORRECTION_BANK_SEGMENT_SPLIT_RE.split(command):
        seg = _CORRECTION_BANK_LEADING_RE.sub("", segment).strip()
        m = _CORRECTION_BANK_INVOKE_RE.match(seg)
        if not m:
            continue
        rest = m.group("rest")
        if _CORRECTION_BANK_HELP_RE.search(rest):
            continue  # --help/-h → never banks
        if m.group("tool") == "wiki.py" and not _CORRECTION_BANK_WIKI_SUBCMD_RE.match(rest):
            continue  # wiki.py without a `new` subcommand → not a bank call
        return True
    return False


def _result_has_bank_signature(result_text: str) -> bool:
    """True iff a Bash tool_result's text carries a real write_gate.py verdict
    line or a wiki.py new outcome key — the ACTUAL execution evidence, not the
    command that was typed. A REJECTED verdict or a REFUSED wiki write is NOT a
    bank signature: the gate ran but refused the candidate, so the correction
    stays open (a rejected banking attempt is not a successful banking)."""
    if not result_text:
        return False
    m = _WRITE_GATE_VERDICT_RE.search(result_text)
    if m:
        return m.group(1) == "PASSED"
    if _WIKI_NEW_CREATED_RE.search(result_text):
        return True
    if _WIKI_NEW_REFUSED_RE.search(result_text):
        return False
    return False


def _bash_call_banks_correction(command: str, result_text: str, has_result: bool) -> bool:
    """True iff a Bash tool_use both (a) has bank invocation shape and (b) its
    PAIRED tool_result carries a passing execution-evidence signature. Shape
    without a result (has_result=False — no tool_result observed in this
    transcript window) or shape with a non-passing/absent signature never
    resolves anything — text-trust alone is not enough (HOLE #2 above)."""
    if not _command_has_bank_invocation_shape(command):
        return False
    if not has_result:
        return False
    return _result_has_bank_signature(result_text)


def _correction_ledger_make_id(turn: int, text: str) -> str:
    return f"c{turn}-" + hashlib.sha256(text.encode("utf-8", "replace")).hexdigest()[:6]


def update_correction_ledger(ledger: list, fired_probes: list[dict], bash_results: list[dict],
                             prompt: str, turn: int) -> tuple[list, list, str]:
    """Pure mechanical lifecycle, same shape as `update_ledger`. Returns
    (new_ledger, closed_items, action). NEVER judges whether the banked lesson
    is any good — only whether a banking tool call ACTUALLY RAN (execution
    evidence), not merely whether its command text looks like one.

    Open: one item per `user_correction` probe that fired THIS turn (fired_probes
    is the subset `run_probes` already computed — no extra transcript scan).
    Close: (a) a recent Bash call satisfying `_bash_call_banks_correction` —
    invocation shape AND a passing execution-evidence signature in its PAIRED
    tool_result (banked — resolves ALL open items, mirroring "close all"), or
    (b) the user's prompt matches the same explicit-closure phrasing Mechanism 3
    uses ("close it", "that's all", ...) — an explicit user override for a
    correction the agent judges already handled outside the banking tools.
    Absent either, the item stays OPEN indefinitely (no auto-resolve on the
    mere passage of turns).

    `bash_results` is `recent_bash_tool_results()`'s output: each Bash tool_use
    paired with its tool_result (if one was observed in this transcript
    window). A command with matching invocation shape but NO paired result, or
    a result that doesn't carry a PASSED/created signature (REJECTED/REFUSED,
    or unrelated output), does not resolve anything — this is the fix for the
    text-trust hole (a bare `CMD="...write_gate.py gate..."` assignment, or a
    short-circuited `false && python3 .../write_gate.py gate ...`, both present
    a matching command STRING while never executing the tool; only a real
    tool_result can distinguish "ran" from "was merely typed").

    Actions: open · bank-resolved · user-resolved · none."""
    ledger = list(ledger)
    closed: list = []
    action = "none"

    corrections = [p for p in (fired_probes or []) if p.get("kind") == "user_correction"]
    for probe in corrections:
        result = probe.get("_result") or {}
        text = result.get("snippet") or result.get("matched") or (prompt or "")
        item = {
            "id": _correction_ledger_make_id(turn, text),
            "turn": turn,
            "text": str(text)[:CORRECTION_LEDGER_TEXT_CAP],
        }
        ledger = (ledger + [item])[-CORRECTION_LEDGER_STORE_CAP:]
        action = "open"

    if ledger:
        banked = any(
            _bash_call_banks_correction(r.get("command", ""), r.get("result_text", ""),
                                        bool(r.get("has_result")))
            for r in (bash_results or [])
        )
        if banked:
            closed = ledger
            ledger = []
            action = "bank-resolved"
        elif _LEDGER_CLOSE_RE.search((prompt or "").strip()):
            closed = ledger
            ledger = []
            action = "user-resolved"

    return ledger, closed, action


def build_correction_ledger_lines(open_items: list, closed_now: list, turn: int) -> list[str]:
    lines: list[str] = []
    if closed_now:
        tail = f"; {len(open_items)} still open." if open_items else " — correction ledger now empty."
        lines.append(
            f"compliance-canary correction ledger (turn {turn}): resolved {len(closed_now)} "
            f"correction(s){tail}"
        )
    if open_items:
        lines.append(
            f"compliance-canary correction ledger (turn {turn}): {len(open_items)} user "
            f"correction(s) still OPEN — closeout-blocking per LEARNING_CONTRACT §2 "
            f"(skills/_shared/LEARNING_CONTRACT.md). Bank each as a durable rule + gate + "
            f"exemplar, SCOPE-classified per §1, before this task closes:"
        )
        for it in open_items[:CORRECTION_LEDGER_SHOW_MAX]:
            lines.append(f"- [turn {it.get('turn','?')}] {it.get('text','')}")
        extra = len(open_items) - CORRECTION_LEDGER_SHOW_MAX
        if extra > 0:
            lines.append(f"- (+{extra} more still open)")
    return lines


# --- Mechanism 5: probe escalation (LEARNING_CONTRACT §8, detection→prevention) --
# Live evidence 2026-07-07 (screenery-lean + product-images monitoring): the same
# advisory probe fired 3-5x uncorrected while the defect shipped — advisory
# reminders lose to speed pressure. After ESCALATION_THRESHOLD fires with the
# latest fire still recent, the probe stops being advice and becomes a
# closeout-blocking directive. Stateless by design: derived from probe_history
# every turn, so it clears itself only when the probe goes silent for
# ESCALATION_CLEAR_TURNS consecutive turns (observed correction) — there is no
# flag to forget and no state to rot.
ESCALATION_THRESHOLD = 3      # fires (within the capped history) that trip escalation
ESCALATION_CLEAR_TURNS = 3    # consecutive silent turns that prove correction
ESCALATION_SHOW_MAX = 4       # max escalated probes surfaced per reminder


def build_probe_escalation_lines(history: list, turn: int) -> list[str]:
    counts: dict[str, int] = {}
    last_fired: dict[str, int] = {}
    for h in history:
        if not isinstance(h, dict):
            continue
        pid = str(h.get("probe_id", ""))
        if not pid:
            continue
        counts[pid] = counts.get(pid, 0) + 1
        ft = _as_int(h.get("fired_at_turn"), 0)
        if ft > last_fired.get(pid, 0):
            last_fired[pid] = ft
    escalated = sorted(
        (pid for pid, n in counts.items()
         if n >= ESCALATION_THRESHOLD
         and turn - last_fired.get(pid, 0) < ESCALATION_CLEAR_TURNS),
        key=lambda p: -counts[p])
    if not escalated:
        return []
    lines = [
        f"compliance-canary ESCALATION (turn {turn}): {len(escalated)} drift probe(s) "
        f"fired {ESCALATION_THRESHOLD}+ times UNCORRECTED — advisory reminders have "
        f"failed; each named rule is now a closeout-blocking gate (LEARNING_CONTRACT "
        f"§8: detection is not prevention). Before ANY further progress or done-claim, "
        f"perform the named rule's required action THIS turn and show its evidence "
        f"(render/test/ledger write). Clears only after {ESCALATION_CLEAR_TURNS} "
        f"consecutive turns without a re-fire:"
    ]
    for pid in escalated[:ESCALATION_SHOW_MAX]:
        lines.append(
            f"- {pid}: {counts[pid]} fires, last at turn {last_fired[pid]} — act now, "
            f"do not acknowledge-and-continue")
    extra = len(escalated) - ESCALATION_SHOW_MAX
    if extra > 0:
        lines.append(f"- (+{extra} more escalated)")
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
        if name in _LEDGER_MAINT_EDIT_TOOLS:
            fp = str((tu.get("input") or {}).get("file_path", ""))
            if path_re.search(fp):
                return None  # the visible markdown ledger is being maintained
    task_ids = set()
    for tu in (tool_uses or []):
        if tu.get("name", "") not in _LEDGER_MAINT_TOOLS:
            continue
        metadata = (tu.get("input") or {}).get("metadata")
        ledger_id = metadata.get("ledger_id") if isinstance(metadata, dict) else None
        if isinstance(ledger_id, str) and ledger_id:
            task_ids.add(ledger_id)
    for req in traj_stats.get("open_ledger_requirements", []):
        base = str(req.get("id", ""))
        count = max(1, min(8, _as_int(req.get("atomic_count"), 1)))
        expected = ({base} if count == 1 else
                    {f"{base}-{chr(ord('a') + i)}" for i in range(count)})
        if base and expected <= task_ids:
            return None  # matching native-task mirror group is being maintained
    return {"open_count": open_ct}


DETECTORS["ledger_not_materialized"] = detect_ledger_not_materialized


# Detector for dependency discipline (lean-execution / code-craft directives).
# Fires when a tool call edits a path matching `path_pattern` — e.g. a dependency
# manifest/lockfile, where the rule is "every dependency is permanent code you
# don't control; justify it". A NUDGE (warn): the probe can't know whether a
# reason was stated, only that the manifest moved.
_PATH_TOUCH_EDIT_TOOLS_DEFAULT = ("Edit", "Write", "NotebookEdit")
_BASH_WRITE_TARGET_RE = re.compile(
    r"(?:>{1,2}|(?:^|[|;&])\s*tee(?:\s+-a)?)\s*[\"']?([^\s\"';&|]+)"
)
_SHELL_BREAK = re.compile(r"^[;&|\n]+$")
_SHELL_ASSIGNMENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=.*$", re.S)
_GLOBAL_OPTION_VALUES = {
    "npm": {"--prefix", "--registry", "--cache", "--userconfig",
            "--globalconfig", "--workspace", "-w", "--loglevel"},
    "poetry": {"--directory", "-C", "--project", "-P"},
}


def _shell_command_segments(command: str) -> list[list[str]]:
    """Tokenize shell commands without executing them; malformed input is inert."""
    try:
        lexer = shlex.shlex(command, posix=True, punctuation_chars=";&|\n")
        lexer.whitespace_split = True
        lexer.commenters = "#"
        lexer.whitespace = " \t\r"  # keep newline as a command separator token
        tokens = list(lexer)
    except (TypeError, ValueError):
        return []
    segments: list[list[str]] = []
    current: list[str] = []
    for token in tokens:
        if _SHELL_BREAK.match(token):
            if current:
                segments.append(current)
                current = []
        else:
            current.append(token)
    if current:
        segments.append(current)
    return segments


def _unwrap_shell_command(tokens: list[str]) -> list[str]:
    """Remove assignment/env/sudo wrappers and return executable-first tokens."""
    i = 0
    while i < len(tokens):
        while i < len(tokens) and _SHELL_ASSIGNMENT.match(tokens[i]):
            i += 1
        if i >= len(tokens):
            return []
        executable = os.path.basename(tokens[i]).lower()
        if executable == "env":
            i += 1
            while i < len(tokens):
                token = tokens[i]
                if _SHELL_ASSIGNMENT.match(token) or token in ("-i", "--ignore-environment"):
                    i += 1
                elif token in ("-u", "--unset", "--chdir"):
                    i += 2
                elif token.startswith(("--unset=", "--chdir=")):
                    i += 1
                else:
                    break
            continue
        if executable == "sudo":
            i += 1
            while i < len(tokens) and tokens[i].startswith("-"):
                option = tokens[i]
                i += 2 if option in ("-u", "-g", "--user", "--group") else 1
            continue
        return tokens[i:]
    return []


def _global_subcommand(tokens: list[str], manager: str) -> str:
    i = 1
    takes_value = _GLOBAL_OPTION_VALUES[manager]
    while i < len(tokens):
        token = tokens[i]
        if token == "--":
            i += 1
            break
        if token in takes_value:
            i += 2
            continue
        if token.startswith("-"):
            i += 1
            continue
        return token.lower()
    return tokens[i].lower() if i < len(tokens) else ""


def _true_cli_flag(tokens: list[str], name: str) -> bool:
    state = None
    for token in tokens:
        if token == name:
            state = True
        elif token.startswith(name + "="):
            value = token.split("=", 1)[1].strip().lower()
            state = value not in ("false", "0", "no", "off")
    return state is True


def _bash_manifest_mutation_targets(command: str) -> list[str]:
    targets: list[str] = []
    for segment in _shell_command_segments(command):
        tokens = _unwrap_shell_command(segment)
        if not tokens:
            continue
        manager = os.path.basename(tokens[0]).lower()
        if manager.endswith(".cmd"):
            manager = manager[:-4]
        if manager not in _GLOBAL_OPTION_VALUES:
            continue
        subcommand = _global_subcommand(tokens, manager)
        dry_run = _true_cli_flag(tokens, "--dry-run")
        if manager == "npm" and subcommand in ("install", "i", "add"):
            if not dry_run and not _true_cli_flag(tokens, "--no-save"):
                targets.extend(("package.json", "package-lock.json"))
        elif manager == "poetry" and subcommand == "add" and not dry_run:
            targets.extend(("pyproject.toml", "poetry.lock"))
    return targets


def detect_tool_path_touch(probe: dict, _messages, tool_uses: list[dict], _tool_errors=None,
                           user_prompt: str = "", traj_stats: dict | None = None) -> dict | None:
    pat = probe.get("path_pattern")
    if not pat:
        return None
    try:
        rx = re.compile(pat)
    except re.error as e:
        log_err(f"bad-regex probe={probe.get('_probe_id')} err={e!r}")
        return None
    tools = tuple(probe.get("tools") or _PATH_TOUCH_EDIT_TOOLS_DEFAULT)
    # min_count (default 1, byte-identical to prior fire-on-first behavior):
    # counts matching Edit/Write touches over the existing tool_uses window and
    # only fires once that count is reached — lets a probe distinguish a single
    # allowed fixup from a bulk mechanical edit (team-lead §5/§6 proportionality)
    # without adding a second window concept (reuses the caller's tool_uses cap).
    # _as_int + clamp (cross-vendor review P5): a non-numeric min_count (e.g. a
    # typo'd "three") must NOT raise into run_probes' blanket except — that would
    # silently DROP the probe instead of degrading to the documented default. And
    # a 0/negative min_count must NOT invert the threshold into firing on the
    # FIRST edit (len(hits) >= 0 is always true) — clamp to the fire-on-first
    # floor of 1, the same floor the default already uses.
    min_count = max(1, _as_int(probe.get("min_count"), 1))
    hits = []
    for tu in (tool_uses or []):
        name = tu.get("name", "")
        if name not in tools:
            continue
        inp = tu.get("input") or {}
        if name == "Bash":
            command = str(inp.get("command", ""))
            hits.extend(target for target in _BASH_WRITE_TARGET_RE.findall(command)
                        if rx.search(target))
            hits.extend(target for target in _bash_manifest_mutation_targets(command)
                        if rx.search(target))
        else:
            fp = str(inp.get("file_path", ""))
            if fp and rx.search(fp):
                hits.append(fp)
    if len(hits) >= min_count:
        return {"path": hits[-1], "count": len(hits), "min_count": min_count}
    return None


DETECTORS["tool_path_touch"] = detect_tool_path_touch


# Detector for the no-reformat rule (lean-execution / surgical changes). Fires
# when an Edit's old_string and new_string differ ONLY by whitespace — a pure
# reformat that buries real changes in noise. Whitespace-stripped equality is
# exact, so low false-positive; `min_chars` skips trivial edits.
_WS_RE = re.compile(r"\s+")


def detect_whitespace_only_edit(probe: dict, _messages, tool_uses: list[dict], _tool_errors=None,
                                user_prompt: str = "", traj_stats: dict | None = None) -> dict | None:
    min_chars = _as_int(probe.get("min_chars"), 12)
    for tu in (tool_uses or []):
        if tu.get("name", "") != "Edit":
            continue
        inp = tu.get("input") or {}
        old = inp.get("old_string")
        new = inp.get("new_string")
        if not isinstance(old, str) or not isinstance(new, str):
            continue
        if old == new or len(old) < min_chars:
            continue
        if _WS_RE.sub("", old) == _WS_RE.sub("", new):
            return {"file": str(inp.get("file_path", ""))}
    return None


DETECTORS["whitespace_only_edit"] = detect_whitespace_only_edit


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
    max_fired: int | None = MAX_PROBES_TRIGGERED,
) -> list[dict]:
    """Returns list of fired probes (each dict has _skill, _probe_id, _result)."""
    fired: list[dict] = []
    # requires_context_regex haystack, built lazily once: recent tool_uses +
    # messages serialized. Lets a probe declare "only arm me when the session
    # actually shows this context" — e.g. vision/judge done-claim probes arm
    # only when .ai/Illustrator activity is present, so a docs-only session
    # doesn't get render/verdict nags (2026-07-01: 3 false fires observed in
    # one meta-work session; alarm fatigue is how real alarms get ignored).
    ctx_hay: str | None = None
    for probe in probes:
        kind = probe.get("kind")
        if kind not in DETECTORS:
            continue
        if probe["_probe_id"] in suppressed:
            continue
        ctx_pat = probe.get("requires_context_regex")
        if ctx_pat:
            try:
                cre = re.compile(ctx_pat)
            except re.error as e:
                log_err(f"bad-context-regex probe={probe['_probe_id']} err={e!r}")
                cre = None
            if cre is not None:
                if ctx_hay is None:
                    try:
                        ctx_hay = json.dumps(tool_uses[-60:]) + json.dumps(messages[-30:]) + (user_prompt or "")
                    except Exception:
                        ctx_hay = user_prompt or ""
                if not cre.search(ctx_hay):
                    continue
        try:
            result = DETECTORS[kind](probe, messages, tool_uses, tool_errors, user_prompt=user_prompt, traj_stats=traj_stats)
        except Exception as e:
            log_err(f"detector-fail probe={probe['_probe_id']} err={e!r}")
            continue
        if result:
            probe["_result"] = result
            fired.append(probe)
            if max_fired is not None and len(fired) >= max_fired:
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
        # D5 (2026-07-19): this fallback is BYTE-IDENTICAL to the `message`
        # field of verify-before-completion's claim-without-evidence probe in
        # drift_probes.json — one wording for the two message sources (they
        # had drifted apart). test_profiles.py pins the equality; keep in sync.
        return (
            f"- {skill} [claim_without_evidence]: recent reply claims work is "
            f"done/fixed/passing, but no verification evidence matching the claim "
            f"appears in the last 5 tool uses (no fresh, successful, post-edit "
            f"check of the right class) — run a fresh check (test, build, lint, "
            f"curl, etc.) and quote its output"
        )
    return f"- {skill} [{kind}]: triggered"


def build_output(fired: list[dict], pulse_skills: list[tuple[str, str]], turn: int,
                 ledger_lines: list[str] | None = None,
                 correction_ledger_lines: list[str] | None = None) -> str:
    """One <system-reminder> carrying whichever mechanism(s) produced output.
    Symptomatic correctives lead (higher signal); the request-ledger section
    follows (it does NOT yield at a wrap-up turn — surfacing open requests as the
    agent closes is the whole point); the correction ledger (LEARNING_CONTRACT
    §2) comes next — also non-yielding, closeout-blocking; the periodic
    re-anchor comes last and only when no probe fired this turn (it yields —
    see main)."""
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
    if correction_ledger_lines:
        lines.extend(correction_ledger_lines)
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


def _session_hash(session_id: str) -> str:
    return hashlib.sha256(session_id.encode("utf-8", errors="replace")).hexdigest()[:16]


def append_telemetry(session_id: str, turn: int, mechanism: str, probe_id: str,
                     emitted: bool, content: str) -> None:
    """Append content-free experiment telemetry; never expose transcript text."""
    record = {
        "session_hash": _session_hash(session_id),
        "turn": turn,
        "mechanism": mechanism,
        "probe_id": probe_id,
        "emitted": bool(emitted),
        "injected_bytes": len(content.encode("utf-8")) if emitted else 0,
        "content_hash": hashlib.sha256(content.encode("utf-8")).hexdigest(),
    }
    path = Path(os.environ.get("COMPLIANCE_CANARY_TELEMETRY_PATH") or
                (state_dir() / "telemetry.jsonl"))
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "a", encoding="utf-8") as handle:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            handle.write(json.dumps(record, sort_keys=True) + "\n")
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
    except Exception as e:
        log_err(f"telemetry-write-fail path={path} err={e!r}")


def deferred_marker_verified_fresh(marker: dict, events: list[dict]) -> bool:
    """F2 stale-nag guard (2026-07-18 audit): True iff matching SUCCESSFUL
    evidence appears AFTER the original claim — the agent verified in the
    meantime, so the deferred fire is stale and the marker drops silently
    instead of nagging. FAIL-OPEN: any uncertainty (no claim anchor recorded,
    claim scrolled out of the tail, unreadable timeline, no matching class)
    → False (emit). The claim anchor is the claim TEXT's hash, resolved to
    the LAST matching assistant message in the CURRENT tail — an event INDEX
    from the suppressing turn's tail window is not comparable across turns
    (the window slides). The freshness rule mirrors
    detect_claim_without_evidence: post-mutation AND post-claim,
    class-matched."""
    if not events:
        return False
    try:
        claim_sha = str(marker.get("claim_sha256") or "")
        if not claim_sha:
            return False
        claim_index = -1
        for m in recent_assistant_messages(events, TRANSCRIPT_LINE_CAP):
            if hashlib.sha256(m["text"].encode("utf-8", "replace")).hexdigest() == claim_sha:
                claim_index = max(claim_index, _as_int(m.get("event_index"), -1))
        if claim_index < 0:
            return False
        evidence_class = str((marker.get("result") or {}).get("evidence_class") or "")
        timeline = execution_timeline(events)
        last_mutation = _as_int(timeline.get("last_mutation_index"), -1)
        for ev in timeline.get("evidence", []):
            result_index = _as_int(ev.get("result_index"), -1)
            if result_index <= claim_index or result_index <= last_mutation:
                continue
            if evidence_class and evidence_class not in ev.get("classes", set()):
                continue
            return True
    except Exception as e:  # fail-open on any freshness error
        log_err(f"deferred-freshness-fail err={e!r}")
    return False


# -------------------------- main --------------------------------------------

def main() -> int:
    # NOTE: COMPLIANCE_CANARY_DISABLED is checked LATER (after the ledger capture
    # block), not here — the kill silences drift detection + its reminders, but it
    # must NEVER stop the ledger from RECORDING a request (user directive: the kill
    # must not disable the ledger). Capture runs unconditionally; only the nagging
    # is silenced.
    profile = active_profile()
    # A true experimental control: no state directory, lock, counter, ledger,
    # telemetry, transcript read, or activation trace is touched.
    if profile == "off":
        return 0

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
    # F5c — the intent log distinguishes a MISSING session id from a real
    # one: an absent id must not co-mingle every anonymous session into one
    # shared unknown.jsonl, so capture sees the raw (possibly empty) id and
    # intent_log_path maps it to a timestamped fallback filename instead.
    intent_session_id = str(payload.get("session_id") or "")
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
    # Mechanism 4 — correction ledger, persisted from prior turns (opened below,
    # once `fired` is known). Read here so the transcript-read gate can see it.
    correction_ledger: list = []
    prompt_text = str(payload.get("prompt") or "")
    # Ledger + prompt-scanning probes see only user-AUTHORED text; harness
    # injections (task-notifications, command transcripts) are stripped.
    prompt_text_user = strip_harness_injected(prompt_text)
    # Task-notification evidence boundary (applied to the frontier/shadow probe
    # surface below; legacy keeps pre-fix behavior for rollback). Pure fail-open
    # classification here — no state or telemetry mutation at this point.
    notification = notification_suppression_decision(prompt_text, prompt_text_user)
    # One transcript tail-read feeds the probe/ledger gate below (via
    # `events`); the D2 provenance check scans the FULL file separately
    # (F1 — a legit announcement older than the tail still suppresses).
    events: list[dict] = []
    if notification["active"]:
        # D2/F1 — mechanical provenance (fail-open): syntax alone cannot
        # distinguish a pasted, syntactically valid <task-notification> from
        # a substrate event. Suppress only when the notification's task-id
        # is >=6 chars AND appears in tool_use/tool_result/substrate content
        # ANYWHERE in the full transcript file; id absent/short/prose-only →
        # NO suppression, the turn fires exactly as before.
        if not notification_task_id_provenanced(transcript_path, notification["task_id"]):
            notification = dict(notification, active=False)

    with state_lock(path):
        state = load_state(path)
        turn = _as_int(state.get("turn_count"), 0) + 1  # guard: corrupt state must not crash (always-exit-0)
        state["turn_count"] = turn
        state["last_seen_iso"] = time.strftime("%FT%TZ", time.gmtime())
        if is_new_session:
            state["session_started_iso"] = state["last_seen_iso"]
        ledger, closed_now, ledger_action = update_ledger(
            state.get("request_ledger", []), prompt_text_user, turn)
        state["request_ledger"] = ledger
        if ledger_action == "add":
            added_atomic = _as_int(ledger[-1].get("atomic_count"), 1) if ledger else 1
            state["substantive_add_count"] = (
                _as_int(state.get("substantive_add_count"), 0) + max(1, added_atomic))
        substantive_add_count = _as_int(state.get("substantive_add_count"), 0)
        correction_ledger = state.get("correction_ledger", [])
        # Persist counter + ledger early — if any later step errors, we still progress
        save_state(path, state)

    if is_new_session:
        gc_old_state(path.parent, time.time())
        # F5a — GC parity: intent logs age out on the same 7-day horizon.
        gc_old_intent_logs(intent_dir(), time.time())

    # Verbatim intent log (L0 no-drop capture). Profile `off` never reaches
    # here (it exited before any mutation). Best-effort: a failure logs to
    # stderr, never blocks.
    # F4 (2026-07-18 audit): harness-block stripping decides ONLY whether
    # the turn is pure-notification (empty remainder → no record). A pasted
    # notification block inside organic user text is the object of the ask
    # and is captured with it; always-mechanical command/system transcripts
    # are still stripped (intent_capture_text). Sole content exception:
    # key-like strings scrubbed (F5b).
    # F5c (2026-07-18 audit): the whole-hook DISABLED valve suppresses intent
    # capture like every other mechanism — the no-opt-out posture belongs to
    # the request LEDGER (standing user directive); the intent log is its
    # verbatim mirror and follows the operator valve.
    if os.environ.get("COMPLIANCE_CANARY_DISABLED") != "1":
        capture_text = intent_capture_text(prompt_text, prompt_text_user)
        if capture_text:
            capture_intent(intent_session_id, turn, capture_text)

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
    all_probes = discover_probes(skills_root())
    probes = all_probes
    frontier_ids = selected_probe_ids(FRONTIER_VERIFY_PROBE_IDS)
    # D1 — claim_without_evidence probe ids suppressed by THIS turn's
    # qualifying notification. They are NOT dropped from `probes`: they still
    # EVALUATE below, and a would-have-fired is persisted as a deferred_fires
    # marker (suppression defers the fire past the notification turn, it never
    # destroys it).
    notification_suppressed_ids: set[str] = set()
    # C4 — scope probes to a deployment's ACTIVE skills. Default (unset) = every
    # discovered skill's probes run, exactly as before (no regression). Set
    # COMPLIANCE_CANARY_PROBE_SKILLS=a,b,c to fire ONLY those skills' probes — so a
    # session that never invoked caveman-ultra's terse style isn't nagged by its
    # filler/word-count probes. Mirrors COMPLIANCE_CANARY_PULSE_SKILLS (re-anchor).
    #
    # EXCEPTION: `user_correction` probes are exempt from this filter for LEDGER
    # OPENING (Mechanism 4) — display/nagging may still be filtered, but ledger
    # capture is unconditional (HOLE, adversarially confirmed: an allowlist that
    # excludes a skill's `user_correction` probe silently prevented its
    # corrections from EVER opening a closeout-blocking item). `ledger_probes`
    # below always includes every discovered `user_correction` probe regardless
    # of the allowlist; `probes` (display-filtered) still governs `fired`/output.
    _probe_allow = {s.strip() for s in
                    os.environ.get("COMPLIANCE_CANARY_PROBE_SKILLS", "").split(",") if s.strip()}
    if profile == "legacy":
        explicit_ids = selected_probe_ids()
        if explicit_ids:
            probes = [p for p in probes if p.get("_probe_id") in explicit_ids]
        elif _probe_allow:
            probes = [p for p in probes if p.get("_skill") in _probe_allow]
        ledger_probes = [p for p in all_probes if p.get("kind") == "user_correction"]
    else:
        # Frontier evaluates only the compact verification guard. Shadow also
        # evaluates the suppressed legacy surface for observational telemetry,
        # but its emitted/task-decision surface remains byte-identical.
        probes = [
            p for p in all_probes if p.get("_probe_id") in frontier_ids
        ]
        ledger_probes = []
        if notification["active"]:
            # The current turn is a substrate-authored terminal-SUCCESS
            # task-notification for an allowlisted self-contained job kind —
            # claim_without_evidence does not EMIT this turn (the notification
            # is the evidence boundary; the agent made no claim). Logged as a
            # suppressed_notification telemetry event so the counterfactual
            # stays measurable; confined to the frontier/shadow surface so
            # shadow output stays byte-identical to frontier and legacy keeps
            # its frozen rollback behavior. Fail-open already happened in the
            # classifier AND the provenance check above — reaching this point
            # means every condition matched. The probe stays in `probes` and
            # is still EVALUATED (D1 deferral — see below).
            for p in probes:
                if p.get("kind") != "claim_without_evidence":
                    continue
                notification_suppressed_ids.add(p["_probe_id"])
                append_telemetry(
                    session_id, turn, "suppressed_notification",
                    p.get("_probe_id", "unknown"), False,
                    f"task-notification kind={notification['kind']} "
                    f"pointer_only={notification['pointer_only']}")
            if notification["pointer_only"]:
                # Pointer-only success: the result content has not been seen —
                # record the output-file pointer as pending_content so the gap
                # is visible in state instead of silently dropped. Reconciled
                # on later turns (D4): cleared once the transcript shows the
                # file being read back; surfaced at wrap-up while unresolved.
                with state_lock(path):
                    state = load_state(path)
                    pending = state.get("notification_pending_content", [])
                    if not isinstance(pending, list):
                        pending = []
                    pending.append({
                        "output_file": notification["output_file"],
                        "turn": turn,
                        "recorded_iso": notification["recorded_iso"],
                        "kind": notification["kind"],
                    })
                    state["notification_pending_content"] = pending[-NOTIFICATION_PENDING_CAP:]
                    save_state(path, state)
    # One transcript read feeds the probes, the ledger's wrap-up check, and the
    # correction ledger's bank-resolution check (needs recent Bash tool_uses
    # PAIRED with their tool_results — execution evidence, not just command
    # text — even on a turn where no NEW correction fires).
    tool_uses: list[dict] = []
    bash_results: list[dict] = []
    messages: list[dict] = []
    tool_errors: list[str] = []
    traj: dict = {}
    if probes or ledger_probes or ledger or correction_ledger:
        if not events:  # the D2/F1 check above scans the full file, no tail prefetch
            events = read_transcript_tail(transcript_path)
        if events:
            bash_results = recent_bash_tool_results(events, n=10)
            if not probes:
                tool_uses = recent_tool_uses(events, n=10)
    # Ledger-opening exemption: run any `user_correction` probes the allowlist
    # excluded from `probes` on their own (cheap — the detector only needs
    # user_prompt, no messages/tool_uses/traj_stats). Their results feed ONLY
    # the correction ledger below, never `fired`/`build_output` (display stays
    # allowlist-scoped; capture does not).
    ledger_only_probes = [p for p in ledger_probes if p not in probes]
    ledger_only_fired: list[dict] = []
    if ledger_only_probes and prompt_text_user:
        try:
            with probe_time_limit(PROBE_TIMEOUT_SECONDS):
                ledger_only_fired = run_probes(
                    ledger_only_probes, [], [], set(), None,
                    user_prompt=prompt_text_user, traj_stats=None)
        except _ProbeBudgetExceeded:
            log_err(f"probe-budget-exceeded: skipped ledger-only probes (>{PROBE_TIMEOUT_SECONDS}s)")
            ledger_only_fired = []
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
            traj["profile"] = profile
            traj["execution_timeline"] = execution_timeline(events)
            traj["final_assistant_has_tool_use"] = final_assistant_has_tool_use(events)
            # Feed the requirements-ledger cross-check (ledger_not_materialized).
            # open_ledger_count counts only items from PRIOR turns (this turn's
            # fresh adds aren't a "drop" yet) and excludes parked/deferred items.
            traj["turn"] = turn
            prior_open = [
                it for it in ledger if isinstance(it, dict) and not it.get("deferred")
                and _as_int(it.get("turn"), turn) < turn
            ]
            traj["open_ledger_count"] = sum(
                max(1, _as_int(it.get("atomic_count"), 1)) for it in prior_open
            )
            traj["open_ledger_requirements"] = [
                {"id": it.get("id", ""),
                 "atomic_count": max(1, _as_int(it.get("atomic_count"), 1))}
                for it in prior_open
            ]
            traj["substantive_add_count"] = substantive_add_count
            try:
                with probe_time_limit(PROBE_TIMEOUT_SECONDS):
                    fired = run_probes(probes, messages, tool_uses, suppressed, tool_errors,
                                       user_prompt=prompt_text_user,
                                       traj_stats=traj)
            except _ProbeBudgetExceeded:
                # A drift_probes regex blew the time budget (likely ReDoS). Skip
                # probes this turn rather than wedge the prompt. Re-anchor below
                # still runs (it uses only fixed regexes).
                log_err(f"probe-budget-exceeded: skipped probes (>{PROBE_TIMEOUT_SECONDS}s)")
                fired = []
            if notification_suppressed_ids:
                # D1 — a notification-suppressed probe that WOULD have fired
                # (on prior-turn content: the agent authored no new claim on a
                # notification turn) does not emit now. Persist a deferred_fire
                # marker instead — the fire is deferred past the notification
                # turn, never destroyed; it emits once on the next turn that is
                # not itself a qualifying notification (below), regardless of
                # message-window slide. No probe_history entry yet: cooldown
                # tracks EMISSIONS, and this probe has not emitted.
                deferred = [p for p in fired if p["_probe_id"] in notification_suppressed_ids]
                fired = [p for p in fired if p["_probe_id"] not in notification_suppressed_ids]
                if deferred:
                    with state_lock(path):
                        state = load_state(path)
                        markers = state.get("deferred_fires", [])
                        if not isinstance(markers, list):
                            markers = []
                        have = {m.get("probe_id") for m in markers if isinstance(m, dict)}
                        for p in deferred:
                            if p["_probe_id"] in have:
                                continue
                            markers.append({
                                "probe_id": p["_probe_id"],
                                "skill": p.get("_skill", ""),
                                "kind": p.get("kind", ""),
                                "result": p.get("_result") or {},
                                "deferred_at_turn": turn,
                                "notification_kind": notification["kind"],
                                # F2 — emission-time freshness anchor: a hash
                                # of the claim TEXT this fire was deferred
                                # for (NOT an event index — tail-window
                                # indexes slide between turns and are not
                                # comparable). Used to drop a stale marker
                                # when the agent verified in the meantime; a
                                # missing/rolled-off anchor fails OPEN (emit).
                                "claim_sha256": (hashlib.sha256(
                                    messages[-1]["text"].encode("utf-8", "replace")
                                ).hexdigest() if messages else ""),
                            })
                            have.add(p["_probe_id"])
                        state["deferred_fires"] = markers[-NOTIFICATION_PENDING_CAP:]
                        save_state(path, state)
            if fired:
                with state_lock(path):
                    state = load_state(path)
                    history = state.get("probe_history", [])
                    for probe in fired:
                        history.append({"probe_id": probe["_probe_id"], "fired_at_turn": turn})
                    state["probe_history"] = history[-50:]
                    save_state(path, state)
                # Best-effort activation telemetry — ADDS a record only, never
                # touches drift logic/ledger/re-anchor above or below. Outside
                # state_lock on purpose: it's an independent append-only sink,
                # not part of this session's locked state.
                _record_trigger_matched_activations(fired)

    # --- D1 deferred-fire emission (frontier/shadow) ----------------------
    # On the first turn that is NOT itself a qualifying notification, emit
    # each persisted deferred_fire marker once and clear it — regardless of
    # message-window slide (the marker carries the result captured at the
    # suppressing turn, so the fire survives the claim scrolling out of the
    # recent-message window). A probe that re-fired on its own this turn is
    # already delivered; its marker is cleared without a second emission.
    # F2 (2026-07-18 audit): a marker survives at most ONE qualifying-
    # notification turn — when a second qualifying notification arrives while
    # a marker from an EARLIER turn is still pending, that marker emits NOW
    # anyway (a notification flood cannot destroy a fire). At emission time
    # freshness is re-checked: matching successful evidence after the
    # original claim drops the marker silently instead of emitting.
    if profile in {"frontier", "shadow"}:
        deferred_markers: list[dict] = []
        with state_lock(path):
            state = load_state(path)
            raw_markers = state.get("deferred_fires", [])
            if isinstance(raw_markers, list) and raw_markers:
                candidates = [m for m in raw_markers if isinstance(m, dict)]
                if not notification["active"]:
                    deferred_markers = candidates
                    state["deferred_fires"] = []
                    save_state(path, state)
                else:
                    # F2 flood rule: markers persisted BEFORE this turn have
                    # already survived their one qualifying-notification
                    # grace — they are due now. Markers persisted THIS turn
                    # keep their grace.
                    due = [m for m in candidates
                           if _as_int(m.get("deferred_at_turn"), turn) < turn]
                    if due:
                        deferred_markers = due
                        state["deferred_fires"] = [m for m in candidates if m not in due]
                        save_state(path, state)
        if deferred_markers:
            if not events:
                # Freshness re-check needs a transcript; none readable →
                # fail-open and emit (never destroy a fire on uncertainty).
                events = read_transcript_tail(transcript_path)
            by_id = {p.get("_probe_id"): p for p in all_probes}
            delivered = {p.get("_probe_id") for p in fired}
            emitted_deferred: list[dict] = []
            for marker in deferred_markers:
                pid = str(marker.get("probe_id") or "")
                if not pid or pid in delivered:
                    continue
                if deferred_marker_verified_fresh(marker, events):
                    continue  # F2 — verified in the meantime; drop silently
                delivered.add(pid)
                base = by_id.get(pid)
                probe = dict(base) if isinstance(base, dict) else {
                    "_skill": marker.get("skill") or pid.split(":")[0],
                    "_probe_id": pid,
                    "kind": marker.get("kind") or "claim_without_evidence",
                }
                probe["_probe_id"] = pid
                probe["_result"] = marker.get("result") or {}
                fired.append(probe)
                emitted_deferred.append(probe)
            if emitted_deferred:
                with state_lock(path):
                    state = load_state(path)
                    history = state.get("probe_history", [])
                    if not isinstance(history, list):
                        history = []
                    for probe in emitted_deferred:
                        history.append({"probe_id": probe["_probe_id"], "fired_at_turn": turn})
                    state["probe_history"] = history[-50:]
                    save_state(path, state)
                _record_trigger_matched_activations(emitted_deferred)

    # --- D4a notification pending-content reconciliation (frontier/shadow) --
    # notification_pending_content gets a consumer: an entry recorded at an
    # EARLIER turn leaves the pending set once the transcript shows its
    # output-file actually being READ (F3: full path, or basename + parent-dir
    # substring in the same event, in a tool_use input or non-error
    # tool_result with no rm/unlink/rmdir in its command/content — destruction
    # does not clear). Entries still unresolved are listed at the existing
    # wrap-up surface below (D4b — no new emission point), independent of
    # request-ledger state (F3).
    pending_content: list[dict] = []
    if profile in {"frontier", "shadow"}:
        with state_lock(path):
            state = load_state(path)
            raw_pending = state.get("notification_pending_content", [])
            if isinstance(raw_pending, list):
                entries = [e for e in raw_pending if isinstance(e, dict)]
                if entries and events:
                    kept: list[dict] = []
                    cleared_any = False
                    for entry in entries:
                        out_path = str(entry.get("output_file") or "")
                        if (out_path and _as_int(entry.get("turn"), turn) < turn
                                and _notification_output_read(events, out_path)):
                            cleared_any = True
                            continue
                        kept.append(entry)
                    if cleared_any:
                        state["notification_pending_content"] = kept
                        save_state(path, state)
                        entries = kept
                pending_content = entries

    suppressed_fired: list[dict] = []
    if profile == "shadow" and events:
        shadow_probes = [p for p in all_probes if p.get("_probe_id") not in frontier_ids]
        try:
            with probe_time_limit(PROBE_TIMEOUT_SECONDS):
                # No cooldown and no output cap: shadow must record every legacy
                # mechanism that would have fired, including repeated noise.
                suppressed_fired = run_probes(
                    shadow_probes, messages, tool_uses, set(), tool_errors,
                    user_prompt=prompt_text_user, traj_stats=traj, max_fired=None)
        except _ProbeBudgetExceeded:
            log_err(f"probe-budget-exceeded: skipped shadow probes (>{PROBE_TIMEOUT_SECONDS}s)")

    # --- periodic re-anchor (yields to fired probes — no double-nag) -----
    pulse_skills: list[tuple[str, str]] = []
    if profile == "legacy" and is_pulse_turn and not fired:
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
    # F3 — the wrap-up detector also arms when unresolved pointer-only
    # notification outputs exist, even with an EMPTY request ledger: a
    # session whose only prompts were notifications + trivia still surfaces
    # its unread outputs at wrap-up.
    completion_claim = (has_completion_claim(events)
                        if (ledger or pending_content) else False)
    if closed_now or ledger:
        show = bool(closed_now) or (bool(ledger) and (
            completion_claim or (profile == "legacy" and (bool(fired) or is_pulse_turn))))
        if show:
            # Ground the wrap-up surface in the verbatim intent log (L0) —
            # quote the user's own captured words instead of ledger state
            # text. Read only when the wrap-up detector fired (no new emission
            # point, no extra read on ordinary turns); best-effort fallback to
            # ledger text when the log is missing/unreadable.
            intent_texts = read_intent_turn_texts(session_id) if completion_claim else None
            ledger_lines = build_ledger_lines(ledger, closed_now, completion_claim, turn, intent_texts)
    if completion_claim and pending_content:
        # D4b — unresolved pointer-only notification outputs ride the
        # EXISTING wrap-up surface (no new emission point), one compact line
        # each — INDEPENDENT of whether the request ledger has open items
        # (F3: the pending-content guarantee must not piggyback on an
        # unrelated ledger).
        for entry in pending_content[:LEDGER_SHOW_MAX]:
            out_path = str(entry.get("output_file") or "")
            if not out_path:
                continue
            kind = str(entry.get("kind") or "task")
            ledger_lines.append(f"- {kind} output never read: {out_path}")

    # --- Mechanism 4: correction ledger (LEARNING_CONTRACT §2) ------------
    # UNCONDITIONAL, same as Mechanism 3: opens on every fired `user_correction`
    # probe, persisted across turns, surfaced EVERY turn it is non-empty (closeout-
    # blocking — unlike the request ledger, this does not wait for a wrap-up turn
    # or drift coupling, since a banked-but-forgotten correction must not go quiet).
    # `fired + ledger_only_fired`: ledger OPENING sees every fired user_correction
    # probe regardless of COMPLIANCE_CANARY_PROBE_SKILLS (the allowlist scopes
    # DISPLAY only — `fired` alone still drives `build_output`/nagging).
    correction_ledger_lines: list[str] = []
    if profile == "legacy":
        correction_closed_now, correction_action = [], "none"
        correction_ledger, correction_closed_now, correction_action = update_correction_ledger(
            correction_ledger, fired + ledger_only_fired, bash_results, prompt_text_user, turn)
        if correction_action != "none":
            with state_lock(path):
                state = load_state(path)
                state["correction_ledger"] = correction_ledger
                save_state(path, state)
        correction_ledger_lines = build_correction_ledger_lines(
            correction_ledger, correction_closed_now, turn)

    # --- Mechanism 5: probe escalation (advisory → closeout-blocking) -----
    # Reload state so this turn's just-appended fires are included; stateless
    # derivation from probe_history — see build_probe_escalation_lines.
    if profile == "legacy":
        escalation_lines: list[str] = build_probe_escalation_lines(
            load_state(path).get("probe_history", []), turn)
        correction_ledger_lines = escalation_lines + correction_ledger_lines

    for probe in suppressed_fired:
        append_telemetry(session_id, turn, "symptomatic_probe",
                         probe.get("_probe_id", "unknown"), False,
                         format_one_probe(probe))

    if not fired and not pulse_skills and not ledger_lines and not correction_ledger_lines:
        return 0

    output = build_output(fired, pulse_skills, turn, ledger_lines, correction_ledger_lines)
    if profile in {"frontier", "shadow"}:
        for probe in fired:
            append_telemetry(session_id, turn, "symptomatic_probe",
                             probe.get("_probe_id", "unknown"), True,
                             format_one_probe(probe))
        if ledger_lines:
            append_telemetry(session_id, turn, "intent_wrap_up", "request-ledger:wrap-up",
                             True, "\n".join(ledger_lines))
    sys.stdout.write(output)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
