#!/usr/bin/env python3
"""Shared path-confinement helpers for Brainer audit tools.

Every marker-derived path (events_path, report_path, json_report_path, raw
refs, sidecar artifact targets) must be resolved AND confined under its
intended `.brainer/<mode>/` root BEFORE any read/write/append. A tampered
marker could otherwise redirect a write outside the intended root (path
traversal via `../`, an absolute path elsewhere on disk, or a symlink whose
target escapes the root).

These helpers centralize that check so each tool no longer hand-rolls its own
`resolve().relative_to()` dance. They resolve symlinks (`strict=False` so the
final component may not exist yet) and reject any candidate whose real location
is not inside the real base.

Robust import: these tools run as standalone scripts / hooks from arbitrary
working directories, so callers add this directory to ``sys.path`` relative to
``__file__`` before importing. This module has no third-party dependencies and
uses only ``pathlib`` + ``os`` so the import works regardless of cwd.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Union

PathLike = Union[str, "os.PathLike[str]", Path]


class PathConfinementError(Exception):
    """Raised when a candidate path escapes its intended base root."""


def _real(path: Path) -> Path:
    """Resolve a path including symlinks, tolerating non-existent leaves.

    ``Path.resolve(strict=False)`` resolves symlinks for the portion of the
    path that exists and lexically normalizes the rest, which collapses ``..``
    and follows symlinked parent directories. That is exactly what we need to
    catch both traversal and symlink-escape before the leaf is created.
    """
    return Path(os.path.expanduser(str(path))).resolve()


def is_within(base: PathLike, candidate: PathLike) -> bool:
    """Return True iff ``candidate`` resolves to a location inside ``base``.

    Both sides are fully resolved (symlinks + ``..``) before comparison.
    """
    base_real = _real(Path(base))
    cand_real = _real(Path(candidate))
    try:
        cand_real.relative_to(base_real)
        return True
    except ValueError:
        return False


def safe_resolve_under(base: PathLike, candidate: PathLike) -> Path:
    """Resolve ``candidate`` and confirm it lives under ``base``.

    Returns the fully-resolved candidate path. Raises ``PathConfinementError``
    if the resolved candidate escapes ``base`` via traversal, an absolute path
    outside the root, or a symlink whose target is outside the root.

    ``candidate`` may be relative; relative candidates are joined onto ``base``
    before resolution. An empty candidate is rejected.
    """
    if candidate is None or str(candidate).strip() == "":
        raise PathConfinementError("empty path is not allowed")
    base_real = _real(Path(base))
    cand = Path(os.path.expanduser(str(candidate)))
    if not cand.is_absolute():
        cand = base_real / cand
    cand_real = _real(cand)
    try:
        cand_real.relative_to(base_real)
    except ValueError as exc:
        raise PathConfinementError(
            f"path {str(candidate)!r} resolves to {cand_real} which is outside {base_real}"
        ) from exc
    return cand_real


def ensure_write_allowed(base: PathLike, candidate: PathLike) -> Path:
    """Confinement gate to call immediately before any write/append/read.

    Thin wrapper over :func:`safe_resolve_under` whose name documents intent at
    every call site. Returns the safe, fully-resolved path to use.
    """
    return safe_resolve_under(base, candidate)
