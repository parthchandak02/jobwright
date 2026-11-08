"""Which build of the dashboard is deployed (GET /api/version).

Two facts, both read without secrets:

- **The web build** (what a browser refresh loads): ``frontend/dist/version.json``, written by the Vite
  build (``build_id``, ``sha``, ``built_at``). The frontend embeds the same ``build_id``, so a browser
  compares its own id with this one to know a new version is ready. Re-read when the file changes.
- **The server checkout**, computed once at startup from git (short sha, commit time, the last few
  commit subjects for "What's new"). Without git it falls back to ``JOBWRIGHT_BUILD_SHA`` /
  ``JOBWRIGHT_BUILD_AT`` and then to the web build stamp.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import threading
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from jobwright import __version__

REPO_ROOT = Path(__file__).resolve().parents[3]
DIST_DIR = REPO_ROOT / "frontend" / "dist"
VERSION_FILE = "version.json"
MAX_CHANGES = 5

# Commit subjects that are not news to someone using the dashboard.
_NOT_USER_FACING = re.compile(
    r"^(merge\b|revert\b|bump\b|wip\b|fixup!|squash!|chore|ci\b|ci:|test|tests\b|docs?\b|docs?:|"
    r"refactor|lint|format|typo|readme|agents\.md|adr\b|release\b|v?\d+\.\d+)",
    re.IGNORECASE,
)

_started_at = datetime.now(UTC).isoformat(timespec="seconds")
_lock = threading.Lock()
_server: dict[str, Any] | None = None
_web_cache: tuple[float, dict[str, Any] | None] | None = None


def _git(*args: str) -> str | None:
    try:
        out = subprocess.run(
            ["git", *args],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            timeout=5,
            check=True,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return out.stdout.strip() or None


def user_facing_changes(subjects: list[str], limit: int = MAX_CHANGES) -> list[str]:
    """Commit subjects worth showing as "What's new": drop merges, chores, docs, tests and duplicates."""
    seen: set[str] = set()
    out: list[str] = []
    for raw in subjects:
        subject = raw.strip()
        if not subject or len(subject) < 8 or _NOT_USER_FACING.match(subject):
            continue
        key = subject.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(subject[:140])
        if len(out) >= limit:
            break
    return out


def _compute_server() -> dict[str, Any]:
    sha = _git("rev-parse", "--short=7", "HEAD")
    committed_at = _git("log", "-1", "--format=%cI")
    subjects_raw = _git("log", "-15", "--format=%s") or ""
    if not sha:
        sha = (os.environ.get("JOBWRIGHT_BUILD_SHA") or "").strip()[:7] or None
        committed_at = committed_at or (os.environ.get("JOBWRIGHT_BUILD_AT") or "").strip() or None
    subjects = subjects_raw.splitlines()
    return {
        "sha": sha,
        "committed_at": committed_at,
        "started_at": _started_at,
        "subject": subjects[0] if subjects else None,
        "changes": user_facing_changes(subjects),
    }


def server_info() -> dict[str, Any]:
    """Git facts for the running server (computed once per process)."""
    global _server
    with _lock:
        if _server is None:
            _server = _compute_server()
        return _server


def web_build(dist_dir: Path | None = None) -> dict[str, Any] | None:
    """The stamp of the built frontend on disk, or None (dev server / not built)."""
    global _web_cache
    path = (dist_dir or DIST_DIR) / VERSION_FILE
    try:
        mtime = path.stat().st_mtime
    except OSError:
        return None
    if dist_dir is None and _web_cache and _web_cache[0] == mtime:
        return _web_cache[1]
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        data = None
    if not isinstance(data, dict) or not data.get("build_id"):
        data = None
    else:
        data = {k: data.get(k) for k in ("build_id", "sha", "built_at")}
    if dist_dir is None:
        _web_cache = (mtime, data)
    return data


def version_payload(dist_dir: Path | None = None) -> dict[str, Any]:
    server = server_info()
    web = web_build(dist_dir)
    sha = (web or {}).get("sha") or server["sha"]
    return {
        # What a refresh loads; the frontend compares build_id with its own.
        "build_id": (web or {}).get("build_id"),
        "version": sha,
        "built_at": (web or {}).get("built_at") or server["committed_at"],
        "deployed_at": server["started_at"],
        "package_version": __version__,
        "subject": server["subject"],
        "changes": server["changes"],
    }
