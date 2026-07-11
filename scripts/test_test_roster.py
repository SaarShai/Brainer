#!/usr/bin/env python3
"""Verify the declarative deterministic-suite roster (no Bash inference).

``run_all_tests.sh`` owns one marked registry block and executes that block.
This gate discovers standalone test candidates and compares paths only against
the same structured rows. Shell comments, echoes, quoted strings, heredocs, and
control flow outside the markers are deliberately irrelevant.
"""
from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
RUNNER = Path("scripts/run_all_tests.sh")
START = "# brainer:test-roster:start"
END = "# brainer:test-roster:end"
PATTERNS = ("test*.py", "test*.sh")
GROUPS = {"core", "tail", "e3"}
RUNNERS = {"python3", "bash"}


def parse_registry_text(text: str) -> list[dict[str, str]]:
    lines = text.splitlines()
    starts = [i for i, line in enumerate(lines) if line.strip() == START]
    ends = [i for i, line in enumerate(lines) if line.strip() == END]
    if len(starts) != 1 or len(ends) != 1 or starts[0] >= ends[0]:
        raise ValueError(
            f"expected exactly one ordered {START!r}/{END!r} pair; "
            f"found starts={len(starts)}, ends={len(ends)}"
        )

    rows: list[dict[str, str]] = []
    for line_number, line in enumerate(
        lines[starts[0] + 1:ends[0]], start=starts[0] + 2
    ):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        fields = [field.strip() for field in stripped.split("|")]
        if len(fields) != 6:
            raise ValueError(
                f"registry line {line_number}: expected 6 pipe-delimited fields, "
                f"got {len(fields)}"
            )
        kind, group, runner, path, requirement, meta = fields
        rows.append({
            "kind": kind,
            "group": group,
            "runner": runner,
            "path": path,
            "requirement": requirement,
            "meta": meta,
        })
    return rows


def load_registry(path: Path) -> list[dict[str, str]]:
    return parse_registry_text(path.read_text(encoding="utf-8"))


def _effective_label(row: dict[str, str]) -> str:
    if row["meta"] != "-":
        return row["meta"]
    path = row["path"]
    return f"unit:{path[:-3] if path.endswith('.py') else path}"


def validate_registry(root: Path, rows: list[dict[str, str]]) -> list[str]:
    errors: list[str] = []
    suites: dict[str, dict[str, str]] = {}
    delegations: dict[str, str] = {}
    exclusions: dict[str, str] = {}
    labels: set[str] = set()

    for row in rows:
        kind, path = row["kind"], row["path"]
        rel = Path(path)
        if kind not in {"S", "D", "X"}:
            errors.append(f"unknown row kind {kind!r} for {path!r}")
            continue
        if not path or rel.is_absolute() or ".." in rel.parts:
            errors.append(f"unsafe/non-relative registry path: {path!r}")
            continue
        if not (root / rel).is_file():
            errors.append(f"registered path is missing: {path}")

        if kind == "S":
            if path in suites:
                errors.append(f"duplicate suite path: {path}")
            suites[path] = row
            if row["group"] not in GROUPS:
                errors.append(f"invalid group {row['group']!r}: {path}")
            if row["runner"] not in RUNNERS:
                errors.append(f"invalid runner {row['runner']!r}: {path}")
            requirement = row["requirement"]
            if requirement != "-" and not all(
                part.isidentifier() for part in requirement.split(".")
            ):
                errors.append(f"invalid requires_module {requirement!r}: {path}")
            label = _effective_label(row)
            if label in labels:
                errors.append(f"duplicate effective label: {label}")
            labels.add(label)
        elif kind == "D":
            if path in delegations:
                errors.append(f"duplicate delegation: {path}")
            delegations[path] = row["meta"]
            if row["group"] != "-" or row["runner"] != "-" \
                    or row["requirement"] != "-":
                errors.append(f"delegation metadata columns must be '-': {path}")
        else:
            if path in exclusions:
                errors.append(f"duplicate exclusion: {path}")
            exclusions[path] = row["meta"]
            if row["group"] != "-" or row["runner"] != "-" \
                    or row["requirement"] != "-":
                errors.append(f"exclusion metadata columns must be '-': {path}")
            if len(row["meta"].split()) < 3:
                errors.append(f"exclusion needs a concrete reason: {path}")

    classified = set(suites) | set(delegations) | set(exclusions)
    if len(classified) != len(suites) + len(delegations) + len(exclusions):
        errors.append("a path appears in more than one of suite/delegation/exclusion")
    for path, owner in delegations.items():
        if owner not in suites:
            errors.append(f"delegated suite {path} has unregistered owner {owner}")
    if not suites:
        errors.append("registry contains no executable suites")
    return errors


def _collect(base: Path, recursive: bool) -> set[Path]:
    if not base.is_dir():
        return set()
    found: set[Path] = set()
    for pattern in PATTERNS:
        paths = base.rglob(pattern) if recursive else base.glob(pattern)
        found.update(
            path for path in paths
            if path.is_file() and "__pycache__" not in path.parts
        )
    return found


def discover_candidates(root: Path) -> list[Path]:
    """Bounded to standalone offline entrypoints; pytest collection is CI-owned."""
    suites: set[Path] = set()
    for skill_tools in (root / "skills").glob("*/tools"):
        suites.update(_collect(skill_tools, recursive=True))
    suites.update(_collect(root / "skills" / "_shared", recursive=True))
    suites.update(_collect(root / "scripts", recursive=False))
    suites.update(_collect(root / "eval", recursive=False))
    suites.update(_collect(root / "eval" / "harness_acceptance", recursive=True))
    return sorted(suites)


def find_orphans(root: Path, rows: list[dict[str, str]]) -> list[str]:
    classified = {row["path"] for row in rows}
    return [
        path.relative_to(root).as_posix()
        for path in discover_candidates(root)
        if path.relative_to(root).as_posix() not in classified
    ]


def runner_contract_errors(text: str) -> list[str]:
    errors = []
    if "UNIT_TESTS" in text:
        errors.append("obsolete UNIT_TESTS list remains beside the registry")
    for group in ("core", "tail", "e3"):
        needle = f"run_registered_suites {group}"
        if text.count(needle) != 1:
            errors.append(f"runner must call {needle!r} exactly once")
    if text.count("done < <(test_roster)") != 1:
        errors.append("runner must consume test_roster once via Bash-3 process substitution")
    return errors


def _extract_bash_function(text: str, name: str) -> str:
    lines = text.splitlines()
    start = next(
        (i for i, line in enumerate(lines) if line == f"{name}() {{"), None
    )
    if start is None:
        raise ValueError(f"missing Bash function {name}")
    end = next(
        (i for i in range(start + 1, len(lines)) if lines[i] == "}"), None
    )
    if end is None:
        raise ValueError(f"unterminated Bash function {name}")
    return "\n".join(lines[start:end + 1])


def _bash_consumer_bounds_fixture(runner_text: str) -> tuple[list[str], str]:
    """Exercise the real Bash consumer with an executable row after END."""
    errors: list[str] = []
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        scripts = root / "scripts"
        scripts.mkdir()
        (scripts / "test_inside.py").write_text("raise SystemExit(0)\n")
        (scripts / "test_after_end.py").write_text("raise SystemExit(0)\n")
        registry_text = (
            f"{START}\n"
            "S|tail|python3|scripts/test_inside.py|-|inside-tail\n"
            f"{END}\n"
            "S|core|python3|scripts/test_after_end.py|-|after-end-decoy\n"
        )
        rows = parse_registry_text(registry_text)
        if [row["path"] for row in rows] != ["scripts/test_inside.py"]:
            errors.append(f"validator crossed END marker: rows={rows}")
        errors.extend(validate_registry(root, rows))

        try:
            consumer = _extract_bash_function(runner_text, "run_registered_suites")
        except ValueError as exc:
            return [str(exc)], ""
        shell = (
            "set -u\nPASS=0\nFAIL=0\nFAILED=()\n"
            "run() { printf 'RUN:%s\\n' \"$1\"; }\n"
            "test_roster() { cat <<'BOUND_ROSTER'\n"
            f"{registry_text}"
            "BOUND_ROSTER\n}\n"
            f"{consumer}\n"
            "run_registered_suites core\n"
            "printf 'FAIL=%s\\n' \"$FAIL\"\n"
        )
        bash = "/bin/bash" if Path("/bin/bash").is_file() else "bash"
        result = subprocess.run(
            [bash, "-c", shell], cwd=root, capture_output=True, text=True
        )
        if result.returncode != 0:
            errors.append(
                f"Bash consumer fixture exited {result.returncode}: {result.stderr.strip()}"
            )
        if "RUN:" in result.stdout:
            errors.append(f"post-END suite executed: {result.stdout.strip()}")
        if result.stdout.strip() != "FAIL=0":
            errors.append(f"unexpected Bash consumer output: {result.stdout.strip()!r}")
        version = subprocess.run(
            [bash, "--version"], capture_output=True, text=True
        ).stdout.splitlines()[0]
    return errors, version


def _negative_fixture() -> tuple[list[str], list[str]]:
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        tools = root / "skills" / "demo" / "tools"
        shared = root / "skills" / "_shared"
        scripts = root / "scripts"
        harness = root / "eval" / "harness_acceptance"
        for directory in (tools, shared, scripts, harness):
            directory.mkdir(parents=True, exist_ok=True)
        for name in (
            "test_registered.py", "test_delegated.py", "test_orphan.py",
            "test_echo_decoy.py", "test_heredoc_decoy.py",
            "test_quoted_decoy.py", "test.sh",
        ):
            (tools / name).write_text("raise SystemExit(0)\n", encoding="utf-8")
        (shared / "test_shared_registered.py").write_text("raise SystemExit(0)\n")
        (scripts / "test_script_registered.py").write_text("raise SystemExit(0)\n")
        (scripts / "test_skill.sh").write_text("exit 2\n")
        (harness / "test_run.py").write_text("raise SystemExit(0)\n")

        runner = scripts / "run_all_tests.sh"
        runner.write_text(
            "#!/usr/bin/env bash\n"
            "echo skills/demo/tools/test_echo_decoy.py\n"
            "cat <<'DECOY'\n"
            "S|core|python3|skills/demo/tools/test_heredoc_decoy.py|-|-\n"
            "DECOY\n"
            "DECOY_TEXT='skills/demo/tools/test_quoted_decoy.py\n"
            "S|core|python3|skills/demo/tools/test_quoted_decoy.py|-|-'\n"
            "test_roster() { cat <<'BRAINER_TEST_ROSTER'\n"
            f"{START}\n"
            "S|core|python3|skills/demo/tools/test_registered.py|-|-\n"
            "S|core|bash|skills/demo/tools/test.sh|-|fixture-owner\n"
            "S|core|python3|skills/_shared/test_shared_registered.py|-|-\n"
            "S|core|python3|scripts/test_script_registered.py|-|-\n"
            "S|core|python3|eval/harness_acceptance/test_run.py|-|-\n"
            "D|-|-|skills/demo/tools/test_delegated.py|-|skills/demo/tools/test.sh\n"
            "X|-|-|scripts/test_skill.sh|-|parameterized helper requires a skill name\n"
            f"{END}\n"
            "BRAINER_TEST_ROSTER\n}\n",
            encoding="utf-8",
        )
        rows = load_registry(runner)
        return find_orphans(root, rows), validate_registry(root, rows)


def _report(orphans: list[str]) -> int:
    if orphans:
        print("FAIL deterministic candidate(s) absent from the declarative registry:")
        for path in orphans:
            print(f"  - {path}")
        return 1
    print("PASS declarative deterministic-suite registry covers every candidate")
    return 0


def main() -> int:
    runner = REPO_ROOT / RUNNER
    try:
        rows = load_registry(runner)
    except (OSError, ValueError) as exc:
        print(f"FAIL registry parse: {exc}")
        return 1

    errors = validate_registry(REPO_ROOT, rows)
    runner_text = runner.read_text(encoding="utf-8")
    errors.extend(runner_contract_errors(runner_text))
    consumer_errors, bash_version = _bash_consumer_bounds_fixture(runner_text)
    errors.extend(consumer_errors)
    if errors:
        print("FAIL declarative registry contract:")
        for error in errors:
            print(f"  - {error}")
        return 1

    fixture_orphans, fixture_errors = _negative_fixture()
    expected = [
        "skills/demo/tools/test_echo_decoy.py",
        "skills/demo/tools/test_heredoc_decoy.py",
        "skills/demo/tools/test_orphan.py",
        "skills/demo/tools/test_quoted_decoy.py",
    ]
    if fixture_errors or fixture_orphans != expected:
        print(
            "FAIL registry negative fixture: "
            f"expected={expected}, got={fixture_orphans}, errors={fixture_errors}"
        )
        return 1
    if "--negative-fixture" in sys.argv[1:]:
        return _report(fixture_orphans)

    counts = {
        group: sum(1 for row in rows if row["kind"] == "S" and row["group"] == group)
        for group in sorted(GROUPS)
    }
    print(
        "PASS registry fixture: echo/heredoc/multiline-quoted decoys ignored; "
        "delegation and exclusion honored"
    )
    print(f"PASS registry schema: suite counts {counts}")
    print(f"PASS Bash consumer stops at END marker ({bash_version})")
    return _report(find_orphans(REPO_ROOT, rows))


if __name__ == "__main__":
    sys.exit(main())
