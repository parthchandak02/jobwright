"""Durable pipeline run records in ``{LOG_DIR}/web_runs.json``.

Used by the dashboard API and by CLI ``jobwright run`` so the frontend can
attach to a run no matter who started it.
"""

from __future__ import annotations

import fcntl
import json
import os
import sys
import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path

from jobwright import config


def registry_path() -> Path:
    return Path(config.LOG_DIR) / "web_runs.json"


def load_registry() -> list[dict]:
    path = registry_path()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, ValueError, OSError):
        return []
    if not isinstance(data, list):
        return []
    return [e for e in data if isinstance(e, dict) and e.get("run_id")]


MAX_ENTRIES = 200
KEEP_DAYS = 30


def save_registry(entries: list[dict]) -> None:
    """Atomic write, pruned to the last KEEP_DAYS days / MAX_ENTRIES runs."""
    path = registry_path()
    cutoff = (datetime.now(timezone.utc) - timedelta(days=KEEP_DAYS)).isoformat()
    kept = [e for e in entries if (e.get("started_at") or "") >= cutoff][-MAX_ENTRIES:]
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(f".{os.getpid()}.tmp")
        tmp.write_text(json.dumps(kept, indent=2), encoding="utf-8")
        os.replace(tmp, path)
    except OSError:
        pass


@contextmanager
def _locked():
    """Serialize read-modify-write across the API and CLI processes."""
    lock = registry_path().with_suffix(".lock")
    lock.parent.mkdir(parents=True, exist_ok=True)
    with lock.open("a") as fh:
        fcntl.flock(fh.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(fh.fileno(), fcntl.LOCK_UN)


def upsert_registry(entry: dict) -> None:
    with _locked():
        entries = [e for e in load_registry() if e.get("run_id") != entry.get("run_id")]
        entries.append(entry)
        save_registry(entries)


def finish_run(run_id: str, returncode: int) -> None:
    """Record the exit code of a run (called by the CLI on exit)."""
    with _locked():
        entries = load_registry()
        for e in entries:
            if e.get("run_id") == run_id:
                e["returncode"] = int(returncode)
                e["finished_at"] = datetime.now(timezone.utc).isoformat()
        save_registry(entries)


def register_pipeline_run(stages: list[str]) -> str:
    """Record this process in the run registry unless the web API already did.

    The dashboard sets ``JOBWRIGHT_WEB_RUN_ID`` on spawned pipelines so we do
    not create a second run_id for the same PID.
    """
    existing = os.environ.get("JOBWRIGHT_WEB_RUN_ID", "").strip()
    if existing:
        return existing
    run_id = uuid.uuid4().hex[:12]
    upsert_registry(
        {
            "run_id": run_id,
            "pid": os.getpid(),
            "stages": stages,
            "started_at": datetime.now(timezone.utc).isoformat(),
            "log_path": str(Path(config.LOG_DIR) / f"pipeline_{run_id}.log"),
            "user": config.get_active_user_id(),
            "cmd": list(sys.argv),
        }
    )
    return run_id
