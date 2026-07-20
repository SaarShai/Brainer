#!/usr/bin/env python3
"""e3_gauntlet — executable E3 cross-repo lifecycle gauntlet
(LEARNING_CONTRACT.md §8, EVAL_TEMPLATE.md "E3 — Lifecycle").

LEARNING_CONTRACT §8 names E3 as a REQUIRED lifecycle test — a lesson banked
in Brainer must be VISIBLE AND ENFORCED in a fresh consuming repo after
`install.sh`, not just inside the Brainer checkout. Until this script existed,
E3 was prose only: doctrine that nothing ran. Per §3 ("mechanism over prose"),
leaving it prose repeats the exact failure this contract was written to close.
This script makes E3 (b) "cross-repo" + (d) "substrate liveness" executable.

What it does:
  1. Creates a FRESH temp project (git init + minimal README) under a
     scratch root (default: this machine's tmp, override with
     E3_GAUNTLET_SCRATCH or --scratch).
  2. Runs `install.sh --project <tmpdir> --host claude-code --no-graphify`
     (single host, no network installs — fast + deterministic).
  3. Runs four consumer-side checks AGAINST THE INSTALLED COPY (never
     against the Brainer checkout itself):
       (a) installed skill set   — every non-opt-in, non-_shared skill
           install.sh claims to install has a resolving symlink under
           <project>/.claude/skills/.
       (b) write-gate cross-repo — the INSTALLED write_gate.py (reached via
           the project's own symlink, not Brainer's path) rejects a
           scope-less, strong-signal candidate.
       (c) substrate liveness    — the portable subset of
           knowledge_liveness's checks (gate-json parse, SKILL.md
           frontmatter + tool paths, markdown links) against the installed
           skills/ tree. (The Brainer-repo-only extensions — wiki liveness,
           hooks-map liveness — depend on scripts/ and wiki/, which
           `--project` does not install; see FINDINGS below.)
       (d) drift_probes.json set — every installed drift_probes.json
           parses as JSON.
       (e) hook-wiring          — every non-opt-in hook-shipping skill
           install.sh knows how to wire generically for --project
           (currently compliance-canary and context-keeper) has its
           command actually present in the consumer's own
           <project>/.claude/settings.json — not just symlinked. Added after
           a real gap: install.sh --project used to symlink skills + write
           CLAUDE.md but never merge hooks into the CONSUMER's settings.json
           (every per-skill tools/install.sh derives its target root from its
           own script location, so the hook-merge step silently only ever
           touched the Brainer checkout's own .claude/settings.json).
       (f) named-probe liveness  — beyond (d)'s "parses as JSON": imports the
           INSTALLED compliance-canary hook.py, runs its own discover_probes()
           against the consumer's installed skills, asserts the compliance-canary
           new-machinery-no-borrow-checkpoint probe is discoverable by its
           qualified id, and asserts its detector fires on a synthetic write
           without a borrow checkpoint and stays silent with one. Added after
           a real gap: (d) proved every drift_probes.json parses but never
           proved any SPECIFIC probe is discoverable or that its detector
           fires — a probe could parse clean and still be dead on arrival.
  4. Prints PASS/FAIL per sub-check + an overall summary.

Exit codes: 0 all sub-checks pass, 1 usage error, 2 any sub-check FAILs.

Stdlib only. Never edits install.sh or any skills/** file — read-only against
the Brainer checkout; the only writes are inside the fresh temp project.
"""
from __future__ import annotations

import argparse
import importlib.util
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SKILLS = REPO / "skills"
INSTALL_SH = REPO / "install.sh"
KL_PATH = REPO / "skills" / "_shared" / "knowledge_liveness.py"


class SubCheck:
    def __init__(self, name: str) -> None:
        self.name = name
        self.passed: bool | None = None
        self.detail: str = ""

    def ok(self, detail: str = "") -> None:
        self.passed = True
        self.detail = detail

    def fail(self, detail: str) -> None:
        self.passed = False
        self.detail = detail

    def line(self) -> str:
        status = "PASS" if self.passed else "FAIL"
        return f"[{status}] {self.name}" + (f" — {self.detail}" if self.detail else "")


def _load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module


def make_fresh_project(scratch_root: Path, keep: bool) -> Path:
    """Create a fresh temp project dir under scratch_root: git init + minimal
    README. Returns the project path. Caller cleans up unless keep=True."""
    scratch_root.mkdir(parents=True, exist_ok=True)
    project = Path(tempfile.mkdtemp(prefix="e3-gauntlet-", dir=str(scratch_root)))
    (project / "README.md").write_text("# e3-gauntlet consumer project\n", encoding="utf-8")
    subprocess.run(["git", "init", "-q"], cwd=project, check=True)
    subprocess.run(["git", "add", "README.md"], cwd=project, check=True)
    subprocess.run(
        ["git", "-c", "user.email=e3@gauntlet.local", "-c", "user.name=e3-gauntlet",
         "commit", "-q", "-m", "init"],
        cwd=project, check=True,
    )
    return project


def run_install(project: Path, host: str = "claude-code") -> tuple[int, str]:
    """Run install.sh --project <project> against THIS Brainer checkout.
    Single selected host, no graphify (no network dependency)."""
    result = subprocess.run(
        ["bash", str(INSTALL_SH), "--project", str(project),
         "--host", host, "--no-graphify"],
        cwd=REPO, capture_output=True, text=True, timeout=300,
    )
    return result.returncode, (result.stdout + result.stderr)


def claimed_skills() -> list[str]:
    """Skills install.sh claims to install: every skills/<name>/SKILL.md
    directory except _shared, INCLUDING opt-in ones (opt-in skills are still
    symlinked + cataloged by install_claude_code(); only their heavier
    tools/install.sh is skipped for opt-in — see install.sh's skill_is_optin
    comment). So the symlink-presence claim covers all of them."""
    names = []
    for d in sorted(SKILLS.iterdir()):
        if not d.is_dir() or d.name == "_shared":
            continue
        if (d / "SKILL.md").is_file():
            names.append(d.name)
    return names


def check_a_installed_skill_set(project: Path) -> SubCheck:
    c = SubCheck("(a) installed skill set present")
    link_dir = project / ".claude" / "skills"
    if not link_dir.is_dir():
        c.fail(f"{link_dir} does not exist")
        return c
    claimed = claimed_skills()
    missing = []
    broken = []
    for name in claimed:
        link = link_dir / name
        if not link.exists() and not link.is_symlink():
            missing.append(name)
        elif link.is_symlink() and not link.resolve().is_dir():
            broken.append(name)
        elif not link.is_dir():
            broken.append(name)
    if missing or broken:
        c.fail(f"missing={missing} broken={broken} (claimed {len(claimed)})")
        return c
    c.ok(f"{len(claimed)}/{len(claimed)} claimed skills present + resolve under {link_dir}")
    return c


def check_b_write_gate_cross_repo(project: Path) -> SubCheck:
    c = SubCheck("(b) write-gate rejects scope-less candidate (cross-repo)")
    wg = project / ".claude" / "skills" / "write-gate" / "tools" / "write_gate.py"
    if not wg.exists():
        c.fail(f"installed write_gate.py not found at {wg}")
        return c
    # Strong-signal candidate (architecture + numbers, well above the default
    # threshold) with NO --scope flag and no scope: frontmatter — must be
    # rejected on SCOPE alone (LEARNING_CONTRACT §1), not on weak signal.
    candidate = (
        "The ingestion worker runs on Fly.io and calls the embedding endpoint.\n"
        "Latency: 120ms p50, 450ms p99.\n"
    )
    result = subprocess.run(
        [sys.executable, str(wg), "gate", "--kind", "fact", "--text", candidate, "--json"],
        cwd=project, capture_output=True, text=True, timeout=30,
    )
    if result.returncode == 0:
        c.fail(f"expected non-zero (reject) exit, got 0 — gate did not trip. stdout={result.stdout!r}")
        return c
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        c.fail(f"non-JSON output from installed write_gate.py: {exc}; stdout={result.stdout!r} stderr={result.stderr!r}")
        return c
    verdict = payload.get("verdict", "")
    if payload.get("passed") is not False or "SCOPE" not in verdict:
        c.fail(f"rejected, but not on SCOPE grounds — verdict={verdict!r}")
        return c
    c.ok(f"exit={result.returncode} verdict={verdict!r}")
    return c


def check_c_substrate_liveness(project: Path) -> SubCheck:
    """(c) Substrate liveness in the consumer copy. --project installs only
    skills/ (+ root docs), not scripts/ or wiki/ — so knowledge_liveness's
    Brainer-repo-only extensions (wiki liveness, hooks-map liveness, both of
    which import scripts/*.py that --project never ships) cannot run there
    and are not part of what got installed. We run the PORTABLE subset it
    itself names in its own CHECKS tuple (gate-json, skill-md-tool-paths,
    markdown-links) against the installed skills/ tree — the equivalent
    installed substrate check per the brief. A naive full kl.run() against a
    bare --project copy is EXPECTED to fail for the scripts/-dependent
    reason above; see FINDINGS in the gauntlet's own output, not a bug in
    this check.
    """
    c = SubCheck("(c) substrate liveness (portable subset) in consumer copy")
    if not KL_PATH.exists():
        c.fail(f"{KL_PATH} not found in Brainer checkout")
        return c
    try:
        kl = _load_module(KL_PATH, "e3_gauntlet_knowledge_liveness")
    except Exception as exc:
        c.fail(f"failed to import knowledge_liveness.py: {type(exc).__name__}: {exc}")
        return c
    kl.REPO = project
    kl.SKILLS = project / ".claude" / "skills"
    kl.SCRIPTS = project / "scripts"  # does not exist under --project; fine, unused below
    errors: list[str] = []
    try:
        for _label, fn in kl.CHECKS:
            fn(errors)
    except Exception as exc:
        c.fail(f"portable checks raised: {type(exc).__name__}: {exc}")
        return c
    if errors:
        c.fail(f"{len(errors)} finding(s): {errors[:5]}")
        return c
    c.ok(f"{len(kl.CHECKS)} portable checks (gate-json, skill-md-tool-paths, markdown-links) clean")
    return c


def check_d_drift_probes_parse(project: Path) -> SubCheck:
    c = SubCheck("(d) drift_probes.json set parses in consumer copy")
    link_dir = project / ".claude" / "skills"
    if not link_dir.is_dir():
        c.fail(f"{link_dir} does not exist")
        return c
    probe_files = sorted(link_dir.glob("*/drift_probes.json"))
    if not probe_files:
        c.fail("no drift_probes.json found under installed skills (expected at least one)")
        return c
    bad = []
    for p in probe_files:
        try:
            json.loads(p.read_text(encoding="utf-8"))
        except Exception as exc:
            bad.append(f"{p.relative_to(project)}: {type(exc).__name__}: {exc}")
    if bad:
        c.fail(f"{len(bad)} unparseable: {bad}")
        return c
    c.ok(f"{len(probe_files)} drift_probes.json parsed clean")
    return c


# Skills whose tools/install.sh install.sh's --project pass knows how to wire
# generically (see install.sh's KNOWN_HOOK_INSTALLERS table): each maps to the
# hook event(s) that skill's own installer wires. Kept in lockstep with
# install.sh by hand — if install.sh's table changes, update this one too (a
# check drifting silently out of sync with what it's supposed to verify is
# exactly the "gate silently dead" class this check exists to close).
KNOWN_HOOK_SKILLS = {
    "compliance-canary": ["UserPromptSubmit"],
    "context-keeper": ["PreCompact", "SessionEnd"],
}

CODEX_HOOK_COMMANDS = {
    "UserPromptSubmit": 'bash "${CLAUDE_PROJECT_DIR:-$PWD}/.codex/skills/compliance-canary/tools/hook.sh"',
    "Stop": 'bash "${CLAUDE_PROJECT_DIR:-$PWD}/.codex/skills/context-keeper/tools/codex_archive.sh"',
}


def _codex_hook_argv(command: str, env: dict[str, str]) -> list[str]:
    prefix = 'bash "${CLAUDE_PROJECT_DIR:-$PWD}/'
    if not command.startswith(prefix) or not command.endswith('"'):
        raise ValueError(f"unsupported Codex hook command shape: {command!r}")
    root = env.get("CLAUDE_PROJECT_DIR") or env.get("PWD")
    if not root:
        raise ValueError("Codex hook command has no project root")
    return ["bash", str(Path(root) / command[len(prefix):-1])]


def snapshot_host_configs() -> dict[Path, bytes | None]:
    paths = (REPO / ".codex" / "hooks.json", REPO / ".claude" / "settings.json")
    return {path: path.read_bytes() if path.exists() else None for path in paths}


def check_codex_links(project: Path) -> SubCheck:
    c = SubCheck("(codex-a) resolving installed skill links")
    link_dir = project / ".codex" / "skills"
    missing = [name for name in claimed_skills() if not (link_dir / name).resolve().is_dir()]
    if missing:
        c.fail(f"missing or broken: {missing}")
    else:
        c.ok(f"{len(claimed_skills())} skill links resolve under .codex/skills")
    return c


def check_codex_hook_json(project: Path) -> SubCheck:
    c = SubCheck("(codex-b) exact default-on hook JSON")
    path = project / ".codex" / "hooks.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        c.fail(f"cannot read valid {path.relative_to(project)}: {exc}")
        return c
    expected = {"hooks": {
        "Stop": [{"hooks": [{"type": "command", "command": CODEX_HOOK_COMMANDS["Stop"]}]}],
        "UserPromptSubmit": [{"matcher": "*", "hooks": [
            {"type": "command", "command": CODEX_HOOK_COMMANDS["UserPromptSubmit"]}
        ]}],
    }}
    if data != expected:
        c.fail(f"expected {expected}, got {data}")
    else:
        c.ok("UserPromptSubmit + Stop commands exactly match declared .codex/skills commands; no opt-in hooks")
    return c


def check_codex_hook_execution(project: Path) -> SubCheck:
    c = SubCheck("(codex-c) synthetic hooks produce ledger/archive evidence")
    failures = []
    shutil.rmtree(project / ".brainer", ignore_errors=True)
    base_env = {**os.environ, "COMPLIANCE_CANARY_PROFILE": "frontier",
                "COMPLIANCE_CANARY_DISABLED": "1"}

    for label, cwd, env, marker in (
        ("PWD fallback", project,
         {k: v for k, v in base_env.items() if k != "CLAUDE_PROJECT_DIR"},
         "E3_CODEX_LEDGER_PWD_MARKER"),
        ("CLAUDE_PROJECT_DIR", REPO,
         {**base_env, "CLAUDE_PROJECT_DIR": str(project)},
         "E3_CODEX_LEDGER_ENV_MARKER"),
    ):
        env["PWD"] = str(cwd)
        payload = json.dumps({"hook_event_name": "UserPromptSubmit",
                              "session_id": f"e3-codex-{label}", "prompt": marker})
        result = subprocess.run(
            _codex_hook_argv(CODEX_HOOK_COMMANDS["UserPromptSubmit"], env), cwd=cwd,
            input=payload, text=True, capture_output=True, env=env, timeout=30,
        )
        ledgers = list((project / ".brainer" / "ledger").glob("*.md"))
        if result.returncode != 0 or not any(marker in p.read_text(encoding="utf-8") for p in ledgers):
            failures.append(f"UserPromptSubmit/{label}: rc={result.returncode}, marker not materialized")

    sessions_root = project / ".e3-codex-sessions"
    rollout = sessions_root / "2026" / "07" / "19" / "rollout-e3.jsonl"
    rollout.parent.mkdir(parents=True, exist_ok=True)
    rollout_marker = "E3_CODEX_ARCHIVE_MARKER"
    rollout.write_text(json.dumps({"payload": {"cwd": str(project)}}) + "\n" + rollout_marker + "\n",
                       encoding="utf-8")

    archive_worker = project / ".codex" / "skills" / "context-keeper" / "tools" / "codex_archive.py"
    try:
        worker = _load_module(archive_worker, "e3_gauntlet_codex_archive")
        worker.SESSIONS_ROOT = sessions_root
        old_pwd, old_stdin = os.environ.get("PWD"), sys.stdin
        try:
            os.environ["PWD"] = str(project)
            sys.stdin = io.StringIO('{"hook_event_name":"Stop"}')
            worker_rc = worker.main()
        finally:
            sys.stdin = old_stdin
            if old_pwd is None:
                os.environ.pop("PWD", None)
            else:
                os.environ["PWD"] = old_pwd
    except Exception as exc:
        worker_rc = -1
        failures.append(f"Stop/injected sessions root: worker raised {type(exc).__name__}: {exc}")
    archived = project / ".brainer" / "sessions" / "raw" / rollout.name
    if worker_rc != 0 or not archived.is_file() or rollout_marker not in archived.read_text(encoding="utf-8"):
        failures.append(f"Stop/injected sessions root: rc={worker_rc}, matching rollout not archived")

    pwd_env = {k: v for k, v in base_env.items() if k != "CLAUDE_PROJECT_DIR"}
    pwd_env["PWD"] = str(project)
    result = subprocess.run(
        _codex_hook_argv(CODEX_HOOK_COMMANDS["Stop"], pwd_env), cwd=project, input='{"hook_event_name":"Stop"}',
        text=True, capture_output=True, env=pwd_env, timeout=30,
    )
    if result.returncode != 0 or "context-keeper/codex_archive: no-matching-rollout" not in result.stderr:
        failures.append("Stop/PWD fallback: command lookup did not reach codex_archive worker")

    command_cwd = project / ".e3-command-cwd"
    command_cwd.mkdir(exist_ok=True)
    env_root = {**base_env, "CLAUDE_PROJECT_DIR": str(project), "PWD": str(command_cwd)}
    result = subprocess.run(
        _codex_hook_argv(CODEX_HOOK_COMMANDS["Stop"], env_root), cwd=command_cwd, input='{"hook_event_name":"Stop"}',
        text=True, capture_output=True, env=env_root, timeout=30,
    )
    if result.returncode != 0 or "context-keeper/codex_archive: no-matching-rollout" not in result.stderr:
        failures.append("Stop/CLAUDE_PROJECT_DIR: command lookup did not reach codex_archive worker")
    if failures:
        c.fail("; ".join(failures))
    else:
        c.ok("ledger markers via PWD+env; Stop lookups reached worker; injected-root worker archived fake rollout")
    return c


def check_host_config_isolation(before: dict[Path, bytes | None]) -> SubCheck:
    c = SubCheck("(codex-d) canonical Brainer host configs unchanged")
    changed = [str(path.relative_to(REPO)) for path, content in before.items()
               if (path.read_bytes() if path.exists() else None) != content]
    if changed:
        c.fail(f"consumer install mutated canonical config: {changed}")
    else:
        c.ok(".codex/hooks.json and .claude/settings.json byte-identical")
    return c


def run_codex_gauntlet(scratch_root: Path, keep: bool) -> tuple[int, list[SubCheck], Path, str]:
    project = make_fresh_project(scratch_root, keep)
    before = snapshot_host_configs()
    install_rc, install_out = run_install(project, "codex")
    checks = [check_codex_links(project), check_codex_hook_json(project),
              check_codex_hook_execution(project), check_host_config_isolation(before)]
    exit_code = 2 if install_rc != 0 or any(c.passed is False for c in checks) else 0
    return exit_code, checks, project, install_out


def check_e_hook_wiring(project: Path) -> SubCheck:
    c = SubCheck("(e) known hook skills wired into consumer settings.json")
    settings_path = project / ".claude" / "settings.json"
    if not settings_path.is_file():
        c.fail(f"{settings_path} does not exist — no hooks wired at all")
        return c
    try:
        data = json.loads(settings_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        c.fail(f"{settings_path} is not valid JSON: {exc}")
        return c
    hooks = data.get("hooks", {})
    missing = []
    for skill_name, events in KNOWN_HOOK_SKILLS.items():
        for event in events:
            rules = hooks.get(event, [])
            found = any(
                skill_name in h.get("command", "")
                for rule in rules
                for h in rule.get("hooks", [])
            )
            if not found:
                missing.append(f"{skill_name}:{event}")
    if missing:
        c.fail(f"not wired in {settings_path.relative_to(project)}: {missing}")
        return c
    c.ok(f"{sum(len(v) for v in KNOWN_HOOK_SKILLS.values())} skill:event pair(s) wired in {settings_path.relative_to(project)}")
    return c


def check_f_named_probe_detector_live(project: Path) -> SubCheck:
    """(f) named-probe firing check — closes an adversarially-found gap in
    check (d): parsing drift_probes.json as JSON proves nothing about whether
    a specific NAMED probe is actually discoverable and its detector fires.
    This imports the INSTALLED consumer copy of compliance-canary's hook.py
    (never Brainer's own copy — same cross-repo discipline as check (b)),
    runs its own discover_probes() against the fresh project's installed
    .claude/skills, asserts the compliance-canary new-machinery-no-borrow-checkpoint
    probe is among them by its qualified id, and asserts its detector actually
    fires on a synthetic write without a borrow checkpoint and stays silent
    with one — proving the probe is live, not just well-formed
    JSON."""
    c = SubCheck("(f) named probe compliance-canary:new-machinery-no-borrow-checkpoint discoverable + detector fires")
    hook_path = project / ".claude" / "skills" / "compliance-canary" / "tools" / "hook.py"
    if not hook_path.exists():
        c.fail(f"installed compliance-canary hook.py not found at {hook_path}")
        return c
    try:
        canary_hook = _load_module(hook_path, "e3_gauntlet_canary_hook")
    except Exception as exc:
        c.fail(f"failed to import installed hook.py: {type(exc).__name__}: {exc}")
        return c
    link_dir = project / ".claude" / "skills"
    probes = canary_hook.discover_probes(link_dir)
    named = [p for p in probes if p.get("_probe_id") == "compliance-canary:new-machinery-no-borrow-checkpoint"]
    if not named:
        c.fail("compliance-canary:new-machinery-no-borrow-checkpoint not discovered among installed probes")
        return c
    probe = named[0]
    detector = canary_hook.DETECTORS.get("new_machinery_no_borrow_checkpoint")
    if detector is None:
        c.fail("DETECTORS['new_machinery_no_borrow_checkpoint'] not registered in installed hook.py")
        return c
    machinery_write = [{"name": "Write", "input": {"file_path": "tools/new_pipeline.py"}}]
    fires = detector(probe, [], machinery_write)
    silent = detector(probe, [{"text": "Checked existing tool fit before building."}], machinery_write)
    if fires is None:
        c.fail(f"detector did not fire on synthetic machinery write without borrow checkpoint (got {fires!r})")
        return c
    if silent is not None:
        c.fail(f"detector fired with a synthetic borrow checkpoint, expected silent (got {silent!r})")
        return c
    c.ok("probe discovered by qualified id; detector fires without a borrow checkpoint, silent with one")
    return c


def run_gauntlet(scratch_root: Path, keep: bool) -> tuple[int, list[SubCheck], Path, str]:
    project = make_fresh_project(scratch_root, keep)
    install_rc, install_out = run_install(project)
    checks: list[SubCheck] = []
    if install_rc != 0:
        # install.sh itself failed — every downstream sub-check is a hard FAIL
        # (nothing to check against), but still report each by name so the
        # summary shape stays constant.
        for fn in (check_a_installed_skill_set, check_b_write_gate_cross_repo,
                   check_c_substrate_liveness, check_d_drift_probes_parse,
                   check_e_hook_wiring, check_f_named_probe_detector_live):
            c = fn(project)
            if c.passed is None:
                c.fail("install.sh --project failed; nothing installed to check")
            checks.append(c)
        return 2, checks, project, install_out

    for fn in (check_a_installed_skill_set, check_b_write_gate_cross_repo,
               check_c_substrate_liveness, check_d_drift_probes_parse,
               check_e_hook_wiring, check_f_named_probe_detector_live):
        checks.append(fn(project))

    exit_code = 2 if any(c.passed is False for c in checks) else 0
    return exit_code, checks, project, install_out


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--scratch", default=None,
                     help="scratch root to create the temp project under "
                          "(default: $E3_GAUNTLET_SCRATCH or system tmp)")
    ap.add_argument("--keep", action="store_true",
                     help="do not delete the temp project on exit (for inspection)")
    ap.add_argument("--quiet", action="store_true", help="suppress install.sh's own output")
    ap.add_argument("--host", choices=("claude-code", "codex"), default="claude-code",
                    help="fresh consumer lifecycle to exercise (default: claude-code)")
    args = ap.parse_args(argv)

    scratch_root = Path(args.scratch or os.environ.get("E3_GAUNTLET_SCRATCH")
                         or tempfile.gettempdir())

    runner = run_codex_gauntlet if args.host == "codex" else run_gauntlet
    exit_code, checks, project, install_out = runner(scratch_root, args.keep)

    print(f"e3_gauntlet: fresh consumer project: {project}")
    if not args.quiet:
        print("--- install.sh --project output ---")
        print(install_out.rstrip("\n"))
        print("--- end install.sh output ---")
    print()
    for c in checks:
        print(c.line())
    n_pass = sum(1 for c in checks if c.passed)
    print()
    if exit_code == 0:
        print(f"e3_gauntlet: PASS ({n_pass}/{len(checks)})")
    else:
        print(f"e3_gauntlet: FAIL ({n_pass}/{len(checks)} passed)")

    if args.keep:
        print(f"e3_gauntlet: --keep set; consumer project left at {project}")
    else:
        shutil.rmtree(project, ignore_errors=True)

    return exit_code


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
