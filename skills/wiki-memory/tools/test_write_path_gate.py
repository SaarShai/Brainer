#!/usr/bin/env python3
"""Tests for the MECHANICAL write-path gate on `wiki.py new`.

Codex flagged that the `new`/write entrypoint did not run write-gate signal
scoring or an overlap() near-dup check before committing — it was honor-system.
new_page() now enforces both BEFORE the write:

  - accept : a good, reasoned, concrete fact passes both checks and is written.
  - reject : a low-signal / reasonless candidate is REFUSED (WikiWriteRejected),
             with the write-gate reason surfaced and no file created.
  - overlap: a near-duplicate of an existing page is REFUSED and steered to
             update-not-create, surfacing the overlapping page.

Run: python3 -m pytest skills/wiki-memory/tools/test_write_path_gate.py -q
 or: python3 skills/wiki-memory/tools/test_write_path_gate.py
"""
from __future__ import annotations

import pathlib
import sys
import tempfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from wiki import WikiStore, WikiWriteRejected  # noqa: E402


def _store() -> WikiStore:
    d = pathlib.Path(tempfile.mkdtemp())
    s = WikiStore(d / "wiki")
    s.init()
    return s


# A high-signal, reasoned, concrete candidate — a real failure lesson with a
# why-clause, an error marker, a code path and a measurement.
_GOOD_TITLE = "ollama batch timeout fix"
_GOOD_BODY = (
    "The nightly eval/runner.py batch failed with a timeout because the Ollama "
    "server defaulted to a 30s read deadline. Fixed by setting OLLAMA_TIMEOUT=600 "
    "in eval/run_all.py so that long generations no longer abort mid-batch."
)
_GOOD_TAGS = ["ollama", "eval", "timeout"]


def test_accept_good_fact():
    """A reasoned, concrete fact passes write-gate + overlap and is written."""
    s = _store()
    res = s.new_page("page", _GOOD_TITLE, domain="experiments",
                     body=_GOOD_BODY, reason="so that long generations don't abort",
                     tags=_GOOD_TAGS)
    assert "created" in res
    assert (s.root / res["created"]).exists()
    assert res["gate"]["accept"] is True
    assert res["gate"]["signal_pass"] is True
    assert res["gate"]["forced"] is False


def test_reject_low_signal():
    """A low-signal / reasonless candidate is REFUSED, reason surfaced, no file."""
    s = _store()
    before = {p.id for p in s.pages()}
    try:
        s.new_page("page", "stuff", domain="experiments",
                   body="some notes about things", tags=["misc"])
        raised = False
    except WikiWriteRejected as e:
        raised = True
        # the write-gate reason must be surfaced, not swallowed
        assert "REJECTED" in str(e) or "low-signal" in str(e).lower()
        assert e.report["signal"]["pass"] is False
    assert raised, "low-signal write should have been refused"
    # nothing was committed
    after = {p.id for p in s.pages()}
    assert after == before


def test_overlap_steers_to_update():
    """A near-duplicate of an existing page is REFUSED and steers to update."""
    s = _store()
    # Seed an established, fully-populated page (force past the gate, then fill
    # body + tags into the file — overlap() scores against the page's stored
    # content/tags/refs, exactly as in real scaffold-then-fill usage).
    res = s.new_page("page", _GOOD_TITLE, domain="experiments",
                     body=_GOOD_BODY, reason="so that long generations don't abort",
                     tags=_GOOD_TAGS, force=True)
    p = s.root / res["created"]
    txt = p.read_text(encoding="utf-8").replace("tags: []", "tags: [ollama, eval, timeout]")
    p.write_text(txt.rstrip() + "\n\n## Lesson\n\n" + _GOOD_BODY + "\n", encoding="utf-8")
    s.index()
    before = {p.id for p in s.pages()}
    # Now attempt a near-duplicate: same subject, same tags, same content.
    try:
        s.new_page("page", "ollama batch timeout fix again", domain="experiments",
                   body=_GOOD_BODY, reason="so that long generations don't abort",
                   tags=_GOOD_TAGS)
        raised = False
    except WikiWriteRejected as e:
        raised = True
        assert e.report["overlap_blocks"] is True
        assert e.report["overlap"]["overlap"] == "high"
        # the overlapping page must be surfaced so the agent can update it
        assert e.report["overlap"]["best_match"] is not None
        assert "update" in str(e).lower()
    assert raised, "near-duplicate write should have been refused"
    after = {p.id for p in s.pages()}
    assert after == before


def test_force_overrides_refusal():
    """force=True is the explicit escape hatch for scaffold-then-fill."""
    s = _store()
    res = s.new_page("page", "stuff", domain="experiments", force=True)
    assert "created" in res
    assert res["gate"]["forced"] is True


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn(); print(f"  ok: {fn.__name__}")
    print(f"\nALL {len(fns)} PASSED")
