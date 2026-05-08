# Codex manual summ (archived 2026-05-08)

Archived because the framework now ships `./te context codex-fresh-thread` — this 153-line inline App Server launcher was a workaround for older installs that lack that subcommand. Kept for provenance only; do not link from operational docs.

Use this when an existing project has an older project-local Token Economy CLI. This prompt intentionally uses one reliable path: create a lean handoff, then launch a persistent fresh Codex successor thread through `codex app-server` directly. Do not attempt same-thread compaction in older installs; it can fail on inherited host config such as `tools.defer_loading`.

```text
summ

Refresh context now. This is a context-refresh operation only.

First split this session into:
1. a lean handoff containing only what is needed to continue, and
2. durable wiki memory that should be documented but not loaded into the fresh context unless needed later.

Treat any instructions after this `summ` prompt as next-session requirements. Put them in the handoff. Do not execute them in this old context.

Spawn or route a lightweight documentation worker for durable wiki memory using `prompts/subagents/wiki-documenter.prompt.md`. If that file is missing, use this inline contract: update only repo-local wiki/log after verified evidence, return changed files, summary, verification. Close the worker only after its result packet has been read and documented or folded into the handoff.

Create the handoff with `./te context checkpoint --handoff-template` or `prompts/summarize-for-handoff.md`. If the generated handoff is generic, replace it with a specific handoff from current session facts. Keep it under 2000 estimated tokens. Preserve exact paths, commands, errors, decisions, blockers, commits, active unfinished subagents, and next-session requirements. Exclude transcript noise, raw logs, broad wiki pages, and docs-only discoveries.

If available, lint it:
./te context lint-handoff <handoff-file>

Do not attempt same-thread compaction. Do not inspect App Server schemas. Do not use `./te context fresh-start` as a launcher. Do not stop because local `./te` lacks `codex-compact-thread` or `codex-fresh-thread`.

After the handoff is ready, replace `<handoff-file>` below with the actual handoff path and run this exact fresh-successor launcher from the current workspace root:

HANDOFF="<handoff-file>" python3 - <<'PY'
import json, os, select, subprocess, time
from pathlib import Path

repo = os.getcwd()
handoff = os.environ["HANDOFF"]
if not os.path.isabs(handoff):
    handoff = os.path.join(repo, handoff)
model = os.environ.get("TOKEN_ECONOMY_CODEX_FRESH_MODEL") or "gpt-5.3-codex-spark"
prompt = (
    f"Read {repo}/start.md and {handoff} only. Continue from that handoff. "
    "Do not load broad wiki/raw archives until retrieval proves relevance. "
    "Start in plan mode. First report that this is a fresh successor context, verify the handoff path, "
    "state the immediate plan in 3-5 bullets, and stop for the user unless the handoff explicitly says to continue."
)

proc = subprocess.Popen(
    ["codex", "app-server", "--listen", "stdio://"],
    stdin=subprocess.PIPE,
    stdout=subprocess.PIPE,
    stderr=subprocess.PIPE,
    text=True,
    bufsize=1,
)
events = []
stderr_text = ""

def send(obj):
    proc.stdin.write(json.dumps(obj) + "\n")
    proc.stdin.flush()

def read_until(timeout, pred):
    deadline = time.time() + timeout
    while time.time() < deadline:
        r, _, _ = select.select([proc.stdout], [], [], 0.2)
        if not r:
            if proc.poll() is not None:
                break
            continue
        line = proc.stdout.readline()
        if not line:
            continue
        try:
            ev = json.loads(line)
        except Exception:
            ev = {"raw": line.rstrip("\n")}
        events.append(ev)
        if pred(ev):
            return ev
    return None

try:
    send({"id": 1, "method": "initialize", "params": {"clientInfo": {"name": "token-economy-manual-fresh", "title": "Token Economy Manual Fresh", "version": "0.1.0"}, "capabilities": {"experimentalApi": True}}})
    read_until(10, lambda e: e.get("id") == 1)
    send({"method": "initialized", "params": {}})
    send({"id": 2, "method": "thread/start", "params": {"cwd": repo, "approvalPolicy": "never", "sandbox": "workspace-write", "ephemeral": False, "model": model}})
    read_until(20, lambda e: e.get("id") == 2)
    thread_response = next((e for e in events if e.get("id") == 2), {})
    thread_id = (((thread_response.get("result") or {}).get("thread") or {}).get("id"))
    if not thread_id:
        raise SystemExit("No thread id returned by Codex App Server.")
    send({"id": 3, "method": "turn/start", "params": {"threadId": thread_id, "approvalPolicy": "never", "model": model, "input": [{"type": "text", "text": prompt}]}})
    read_until(180, lambda e: (
        e.get("method") == "thread/status/changed"
        and (e.get("params") or {}).get("threadId") == thread_id
        and ((e.get("params") or {}).get("status") or {}).get("type") == "idle"
    ) or (e.get("method") == "error" and not e.get("willRetry")))
    send({"id": 4, "method": "thread/list", "params": {"cwd": repo, "archived": False, "limit": 20, "sourceKinds": ["cli", "vscode", "exec", "appServer", "unknown"], "sortKey": "updated_at"}})
    read_until(10, lambda e: e.get("id") == 4)
finally:
    proc.terminate()
    try:
        proc.wait(timeout=5)
    except Exception:
        proc.kill()
    if proc.stderr:
        stderr_text = proc.stderr.read()

thread_response = next((e for e in events if e.get("id") == 2), {})
thread = ((thread_response.get("result") or {}).get("thread") or {})
thread_id = thread.get("id")
assistant_responded = any(
    ((e.get("params") or {}).get("item") or {}).get("type") == "agentMessage"
    or bool(isinstance((e.get("params") or {}).get("delta"), str) and (e.get("params") or {}).get("delta").strip())
    for e in events
)
thread_idle = any(
    e.get("method") == "thread/status/changed"
    and (e.get("params") or {}).get("threadId") == thread_id
    and ((e.get("params") or {}).get("status") or {}).get("type") == "idle"
    for e in events
)
list_response = next((e for e in events if e.get("id") == 4), {})
listed_ids = [t.get("id") for t in ((list_response.get("result") or {}).get("data") or []) if isinstance(t, dict)]
outdir = Path(".token-economy/checkpoints/manual-codex-fresh")
outdir.mkdir(parents=True, exist_ok=True)
(outdir / "events.jsonl").write_text("\n".join(json.dumps(e, sort_keys=True) for e in events) + "\n", encoding="utf-8")
(outdir / "stderr.txt").write_text(stderr_text, encoding="utf-8")
summary = {
    "ok": bool(thread_id and thread.get("ephemeral") is False and thread.get("turns") == [] and assistant_responded and thread_idle and thread_id in listed_ids),
    "thread_id": thread_id,
    "thread_persistent": thread.get("ephemeral") is False,
    "thread_turns_empty": thread.get("turns") == [],
    "assistant_responded": assistant_responded,
    "thread_idle": thread_idle,
    "listed_after_start": thread_id in listed_ids,
    "handoff": handoff,
    "model": model,
    "events": str(outdir / "events.jsonl"),
    "stderr": str(outdir / "stderr.txt"),
}
print(json.dumps(summary, indent=2, sort_keys=True))
PY

Success requires:
ok: true
thread_persistent: true
thread_turns_empty: true
assistant_responded: true
thread_idle: true
listed_after_start: true

If the launcher succeeds, stop old-context work immediately after reporting the new thread id and handoff path. Do not continue old-context task work. Do not inspect schemas. Do not retry alternate methods unless the launcher returns `ok: false`.

End with:
FRESH SUCCESSOR LAUNCHED - STOP HERE
```
