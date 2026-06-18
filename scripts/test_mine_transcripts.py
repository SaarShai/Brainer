#!/usr/bin/env python3
"""Smoke tests for transcript-mined lesson candidates."""
from __future__ import annotations

from mine_transcripts import candidate_lessons


def test_candidate_lessons_are_advisory_and_ranked() -> None:
    agg = {
        "all_error_signatures": {
            "<tool_use_error>File has not been read yet. Read it first before writing to it.</tool_use_error>": 4,
            "<tool_use_error>File has been modified since read</tool_use_error>": 3,
            "File does not exist. Note: cwd is /repo": 2,
        },
        "bash_results_over_5kb_total": 8,
        "multi_reads": [{"file": "skills/foo/SKILL.md", "reads": 4}],
        "search_chain_occurrences_total": 5,
    }
    lessons = candidate_lessons(agg)
    ids = [item["id"] for item in lessons]
    assert ids[0] == "large-bash-output-needs-filter", lessons
    assert "edit-without-read" in ids, lessons
    assert "stale-read-before-edit" in ids, lessons
    assert all("route" in item and "prevention" in item for item in lessons), lessons
    assert all("wiki.py new" not in item["route"] for item in lessons), "miner must not auto-write durable memory"


def main() -> int:
    test_candidate_lessons_are_advisory_and_ranked()
    print("OK (1 tests)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
