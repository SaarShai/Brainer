import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "skills" / "task-retrospective" / "SKILL.md"


def read(path) -> str:
    return Path(path).read_text(encoding="utf-8")


def frontmatter(text: str) -> str:
    assert text.startswith("---\n")
    end = text.find("\n---\n", 4)
    assert end != -1
    return text[4:end]


def task_retrospective_catalog_line(carrier: str) -> str:
    text = read(ROOT / carrier)
    match = re.search(r"^- `task-retrospective` — .*$", text, re.MULTILINE)
    assert match, f"task-retrospective catalog line missing from {carrier}"
    return match.group(0)


def test_task_retrospective_frontmatter_is_user_triggered_not_broad_auto():
    fm = frontmatter(read(SKILL))
    assert "Use only when the user explicitly activates task audit mode" in fm
    assert "after-the-fact task learning audit" in fm
    assert "Does not audit Brainer skill obedience" in fm
    assert "does not edit canonical Brainer skills" in fm

    forbidden = [
        "Use at the end of any non-trivial task",
        "ALSO fire mid-task",
        "at task end run task-retrospective",
        "End of any non-trivial task",
    ]
    for phrase in forbidden:
        assert phrase not in fm


def test_resident_carriers_do_not_advertise_old_auto_trigger():
    for carrier in ["AGENTS.md", "CLAUDE.md", "GEMINI.md"]:
        line = task_retrospective_catalog_line(carrier)
        assert "Use only when the user explicitly activates task audit mode" in line
        assert "end of any non-trivial task" not in line.lower()
        assert "also fire mid-task" not in line.lower()


def test_task_retrospective_body_keeps_project_only_boundary_and_project_skill_target():
    text = read(SKILL)
    required = [
        "Task-retrospective improves the current project.",
        "Brainer audit mode improves Brainer.",
        "Do **not** use it to audit Brainer skill obedience",
        "Canonical Brainer skill updates are not on this ladder.",
        "existing project-specific skill",
        "new project-specific skill",
        "No agent-only override.",
        "No durable project lesson found.",
    ]
    for phrase in required:
        assert phrase in text


def test_wiki_and_verify_no_longer_teach_automatic_task_boundary_harvest():
    wiki = read(ROOT / "skills" / "wiki-memory" / "SKILL.md")
    verify = read(ROOT / "skills" / "verify-before-completion" / "SKILL.md")

    assert "No automatic task-boundary harvest" in wiki
    assert "do not run the write protocol merely because an ordinary task ended" in wiki
    assert "does **not** auto-launch task-retrospective or write memory" in verify
    assert "task-retrospective" in verify and "is armed" in verify

    forbidden = [
        "At the **end of any non-trivial task**",
        "This is a reflex at the task boundary",
        "Fire the harvest",
        "Harvest the learning (before you call it done)",
    ]
    scoped = wiki + "\n" + verify
    for phrase in forbidden:
        assert phrase not in scoped


def test_correction_drift_probes_respect_armed_boundary():
    task_probes = json.loads(read(ROOT / "skills" / "task-retrospective" / "drift_probes.json"))
    wiki_probes = json.loads(read(ROOT / "skills" / "wiki-memory" / "drift_probes.json"))
    messages = "\n".join(probe.get("message", "") for probe in task_probes + wiki_probes)

    assert "If task-retrospective is armed" in messages
    assert "do not launch a full retrospective automatically" in messages
    assert "run the task-retrospective reflex NOW" not in messages
    assert "harvest the corrected rule" not in messages


def test_write_gate_override_must_be_user_directed():
    text = read(ROOT / "skills" / "write-gate" / "SKILL.md")
    assert '"override": "user_directed"' in text
    assert "There is no agent-only override." in text
