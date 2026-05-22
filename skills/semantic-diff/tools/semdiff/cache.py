"""Session-scoped snapshot cache. File-backed JSON for persistence across process runs."""
from __future__ import annotations
import json
import os
from pathlib import Path
from typing import Optional


class SessionCache:
    def __init__(self, session_id: str, cache_dir: Optional[Path] = None):
        self.session_id = session_id
        repo_root = Path(os.environ.get("TOKEN_ECONOMY_ROOT", Path.cwd()))
        self.cache_dir = Path(cache_dir) if cache_dir else repo_root / ".token-economy" / "semdiff"
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.path = self.cache_dir / f"{session_id}.json"
        self._data = self._load()

    def _load(self) -> dict:
        if self.path.exists():
            return json.loads(self.path.read_text())
        return {}

    def _save(self):
        self.path.write_text(json.dumps(self._data, indent=2))

    def get(self, file_path: str) -> Optional[dict]:
        return self._data.get(file_path)

    def set(self, file_path: str, snapshot: dict):
        self._data[file_path] = snapshot
        self._save()

    def clear(self):
        self._data = {}
        self._save()
