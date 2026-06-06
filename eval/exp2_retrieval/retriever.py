"""Retriever wrapper around the wiki-memory CLI (`wiki.py`).

Wraps `wiki.py search` (tier-1 ranked hits) and `wiki.py fetch` (tier-3 full
page body) so the retrieval eval sees exactly what an agent would get from the
shipped store — no reimplementation of the ranker.

Two call paths, in priority order:
  1. In-process: import WikiStore from skills/wiki-memory/tools/wiki.py and call
     .search()/.fetch() directly. Fast, no subprocess per query.
  2. Subprocess fallback: shell out to `python3 wiki.py --root <wiki> search ...`
     and parse the JSON the CLI prints (the real stdout contract). Used if the
     in-process import fails for any reason.

The search-hit schema matches wiki.py's `_search_hit`:
    {id, path, title, type, tags, preview, score, reasons, superseded_by}
fetch returns {id, path, title, type, tags, content}.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

# Repo layout: <repo>/eval/exp2_retrieval/retriever.py
REPO_ROOT = Path(__file__).resolve().parents[2]
WIKI_TOOLS = REPO_ROOT / "skills" / "wiki-memory" / "tools"
DEFAULT_WIKI_ROOT = REPO_ROOT / "wiki"
WIKI_PY = WIKI_TOOLS / "wiki.py"


class WikiRetriever:
    """Thin retrieval facade over the wiki-memory store."""

    def __init__(self, wiki_root: str | Path | None = None, prefer_inprocess: bool = True):
        self.wiki_root = Path(wiki_root or DEFAULT_WIKI_ROOT).expanduser().resolve()
        self.mode = "subprocess"
        self._store = None
        if prefer_inprocess:
            self._store = self._try_inprocess()
            if self._store is not None:
                self.mode = "inprocess"

    def _try_inprocess(self):
        try:
            if str(WIKI_TOOLS) not in sys.path:
                sys.path.insert(0, str(WIKI_TOOLS))
            from wiki import WikiStore  # type: ignore

            store = WikiStore(self.wiki_root)
            # Force an index build so the first search is warm and deterministic.
            store.index()
            return store
        except Exception as exc:  # noqa: BLE001 — degrade to subprocess, never crash
            sys.stderr.write(f"[retriever] in-process import failed ({exc!r}); using subprocess\n")
            return None

    # ------------------------------------------------------------------ search
    def search(self, query: str, k: int = 5) -> list[dict[str, Any]]:
        """Tier-1 ranked hits. Returns wiki.py's native hit dicts."""
        if self._store is not None:
            return self._store.search(query, k=k)
        return self._search_subprocess(query, k=k)

    def _search_subprocess(self, query: str, k: int) -> list[dict[str, Any]]:
        out = subprocess.run(
            [sys.executable, str(WIKI_PY), "--root", str(self.wiki_root), "search", query, "-k", str(k)],
            capture_output=True,
            text=True,
            check=True,
        )
        return json.loads(out.stdout)

    # ------------------------------------------------------------------- fetch
    def fetch(self, page_id: str) -> dict[str, Any]:
        """Tier-3 full page body for one id."""
        if self._store is not None:
            return self._store.fetch(page_id)
        return self._fetch_subprocess(page_id)

    def _fetch_subprocess(self, page_id: str) -> dict[str, Any]:
        out = subprocess.run(
            [sys.executable, str(WIKI_PY), "--root", str(self.wiki_root), "fetch", page_id],
            capture_output=True,
            text=True,
            check=True,
        )
        return json.loads(out.stdout)

    # ----------------------------------------------------------- convenience
    def retrieve(self, query: str, k: int = 5, fetch_bodies: bool = True) -> dict[str, Any]:
        """One call: ranked ids + (optionally) fetched bodies for the top-k.

        Returns:
            {
              "query": str,
              "ranked_ids": [id, ...],          # rank order, length<=k
              "hits": [hit_dict, ...],          # native wiki.py search hits
              "contexts": [body_str, ...],      # fetched page bodies, rank-aligned
            }
        """
        hits = self.search(query, k=k)
        ranked_ids = [h["id"] for h in hits]
        contexts: list[str] = []
        if fetch_bodies:
            for pid in ranked_ids:
                try:
                    contexts.append(self.fetch(pid)["content"])
                except Exception as exc:  # noqa: BLE001
                    contexts.append(f"[fetch failed for {pid}: {exc!r}]")
        return {"query": query, "ranked_ids": ranked_ids, "hits": hits, "contexts": contexts}


if __name__ == "__main__":
    # Smoke test: `python3 retriever.py "kv cache eviction"`
    q = sys.argv[1] if len(sys.argv) > 1 else "how does TurboQuant compress the KV cache"
    r = WikiRetriever()
    res = r.retrieve(q, k=5, fetch_bodies=False)
    print(f"mode={r.mode}")
    print(json.dumps({"query": res["query"], "ranked_ids": res["ranked_ids"]}, indent=2))
