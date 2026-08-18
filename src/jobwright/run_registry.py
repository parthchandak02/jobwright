"""Durable pipeline run records in ``{LOG_DIR}/web_runs.json``.

Used by the dashboard API and by CLI ``jobwright run`` so the frontend can
attach to a run no matter who started it.
"""

from __future__ import annotations

import json
import os
import sys
import uuid
from datetime import datetime, timezone
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


def save_registry(entries: list[dict]) -> None:
    path = registry_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(entries, indent=2), encoding="utf-8")
    except OSError:
        pass


def upsert_registry(entry: dict) -> None:
    entries = [e for e in load_registry() if e.get("run_id") != entry.get("run_id")]
    entries.append(entry)
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
            "user": config.ACTIVE_USER_ID,
            "cmd": list(sys.argv),
        }
    )
    return run_id
