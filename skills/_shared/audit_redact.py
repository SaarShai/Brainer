#!/usr/bin/env python3
"""Shared secret-redaction for Brainer audit tools.

ONE place that scrubs a broad secret family from any text or object before it
hits disk. Every audit tool funnels strings through :func:`redact` (single
string) or :func:`redact_obj` (recursively over dicts/lists, redacting every
string leaf) so no raw secret reaches a JSONL event, a marker, a status payload,
or a rendered report.

Covered secret families:
  - OpenAI keys: ``sk-...`` (and ``sk-proj-...``)
  - GitHub tokens: ``ghp_...``, ``gho_...``, ``ghu_...``, ``ghs_...``,
    ``ghr_...``, and fine-grained ``github_pat_...``
  - AWS access key ids: ``AKIA...`` / ``ASIA...`` plus ``aws_secret_access_key``
    assignments
  - JWTs: ``<b64url>.<b64url>.<b64url>``
  - HTTP auth headers: ``Authorization: Bearer ...`` / ``Authorization: Basic ...``
  - ``.env``-style assignments: ``API_KEY=...``, ``TOKEN=...``, ``PASSWORD=...``,
    ``SECRET=...``, ``*_KEY=...`` (case-insensitive key + ``:`` or ``=``)
  - URLs with embedded credentials: ``https://user:pass@host`` -> user kept,
    password redacted
  - SSH / PEM private-key blocks: ``-----BEGIN ... PRIVATE KEY----- ... -----END ...-----``
  - Service-account JSON ``"private_key": "..."``
  - Local usernames in ``/Users/<name>`` and ``/home/<name>`` paths

Robust import: callers add this directory to ``sys.path`` relative to
``__file__``. Pure stdlib (``re``, ``json``), so the import works from any cwd.
"""
from __future__ import annotations

import json
import re
from typing import Any

REDACTED = "[REDACTED]"

# NOTE: order matters. Multi-line / structural patterns (PEM blocks, JSON
# private_key) run first so a later narrow pattern cannot partially rewrite the
# inside of a block. Each entry is (compiled_regex, replacement_callable).

_PEM_RE = re.compile(
    r"-----BEGIN (?:[A-Z0-9 ]+ )?PRIVATE KEY-----.*?-----END (?:[A-Z0-9 ]+ )?PRIVATE KEY-----",
    re.S,
)

# service-account / JSON style: "private_key": "-----...-----\n..."
_JSON_PRIVATE_KEY_RE = re.compile(
    r'("?private_key"?\s*[:=]\s*")(?:\\.|[^"\\])*(")',
)

_AUTH_BEARER_RE = re.compile(
    r"(?i)(authorization\s*:\s*(?:bearer|basic|token)\s+)[A-Za-z0-9._~+/=-]+"
)

# URL with embedded credentials: scheme://user:password@host -> keep user, hide password
_URL_CRED_RE = re.compile(
    r"(?i)\b([a-z][a-z0-9+.\-]*://[^\s:/@]+):([^\s:/@]+)@"
)

# JWT: three base64url segments separated by dots. Require a reasonable length
# so ordinary dotted identifiers are not caught.
_JWT_RE = re.compile(
    r"\beyJ[A-Za-z0-9_-]{6,}\.[A-Za-z0-9_-]{6,}\.[A-Za-z0-9_-]{6,}\b"
)

# OpenAI keys (incl. project keys). Generic sk- form kept broad.
_OPENAI_RE = re.compile(r"\bsk-(?:proj-)?[A-Za-z0-9_-]{16,}\b")

# GitHub tokens (classic prefixes + fine-grained PAT).
_GITHUB_PAT_RE = re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,}\b")
_GITHUB_TOKEN_RE = re.compile(r"\bgh[opusr]_[A-Za-z0-9]{20,}\b")

# AWS access key id.
_AWS_AKID_RE = re.compile(r"\b(?:AKIA|ASIA|AGPA|AIDA|AROA|ANPA|ANVA)[A-Z0-9]{16}\b")

# AWS secret access key assignment (40-char base64-ish following the key name).
_AWS_SECRET_RE = re.compile(
    r"(?i)(aws_secret_access_key\s*[:=]\s*['\"]?)[A-Za-z0-9/+=]{20,}"
)

# .env-style assignment: KEY = value where KEY looks sensitive. Keeps the key
# name + delimiter, hides the value (stops at whitespace / quote).
_ENV_ASSIGN_RE = re.compile(
    r"(?i)\b([A-Za-z0-9_]*(?:api[_-]?key|secret|token|password|passwd|pwd|access[_-]?key|private[_-]?key|client[_-]?secret|auth)[A-Za-z0-9_]*)"
    r"(\s*[:=]\s*)"
    r"(['\"]?)([^'\"\s]+)(['\"]?)"
)

# Local usernames in home-directory paths.
_USERS_PATH_RE = re.compile(r"(/Users/)[^/\s]+")
_HOME_PATH_RE = re.compile(r"(/home/)[^/\s]+")


def _replace_env_assign(m: "re.Match[str]") -> str:
    # group1 = key, group2 = delimiter, group3 = opening quote, value hidden, group5 = closing quote
    return f"{m.group(1)}{m.group(2)}{m.group(3)}{REDACTED}{m.group(5)}"


def redact(text: Any) -> str:
    """Scrub every covered secret family from ``text``; returns a string.

    Accepts non-str input defensively (coerced via ``str``); ``None``/empty
    yields ``""``.
    """
    if text is None:
        return ""
    out = text if isinstance(text, str) else str(text)
    if not out:
        return out

    # 1. Structural / multi-line blocks first.
    out = _PEM_RE.sub(REDACTED, out)
    out = _JSON_PRIVATE_KEY_RE.sub(lambda m: m.group(1) + REDACTED + m.group(2), out)

    # 2. Header / URL credentials.
    out = _AUTH_BEARER_RE.sub(lambda m: m.group(1) + REDACTED, out)
    out = _URL_CRED_RE.sub(lambda m: m.group(1) + ":" + REDACTED + "@", out)

    # 3. .env-style assignments (covers api_key/token/password/secret/etc).
    out = _ENV_ASSIGN_RE.sub(_replace_env_assign, out)
    out = _AWS_SECRET_RE.sub(lambda m: m.group(1) + REDACTED, out)

    # 4. Standalone token shapes.
    out = _JWT_RE.sub(REDACTED, out)
    out = _OPENAI_RE.sub(REDACTED, out)
    out = _GITHUB_PAT_RE.sub(REDACTED, out)
    out = _GITHUB_TOKEN_RE.sub(REDACTED, out)
    out = _AWS_AKID_RE.sub(REDACTED, out)

    # 5. Local usernames in home paths.
    out = _USERS_PATH_RE.sub(lambda m: m.group(1) + REDACTED, out)
    out = _HOME_PATH_RE.sub(lambda m: m.group(1) + REDACTED, out)

    return out


def redact_obj(obj: Any) -> Any:
    """Recursively redact every string leaf in a dict/list/scalar structure.

    Dict keys are left intact (only values are scrubbed); strings inside lists,
    tuples, and nested dicts are all passed through :func:`redact`. Non-string
    scalars (int/float/bool/None) are returned unchanged.
    """
    if isinstance(obj, str):
        return redact(obj)
    if isinstance(obj, dict):
        return {key: redact_obj(value) for key, value in obj.items()}
    if isinstance(obj, list):
        return [redact_obj(item) for item in obj]
    if isinstance(obj, tuple):
        return tuple(redact_obj(item) for item in obj)
    return obj
