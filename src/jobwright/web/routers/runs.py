"""Pipeline run triggers, SSE logs, gated apply, and a durable run registry."""

from __future__ import annotations

import asyncio
import json
import os
import shlex
import signal
import subprocess
import sys
import uuid
from collections.abc import AsyncIterator
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import unquote

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from jobwright import config
from jobwright.database import get_connection
from jobwright.users import is_apply_enabled
from jobwright.web.session import resolve_dashboard_user

router = APIRouter(prefix="/api", tags=["runs"])

ALLOWED_STAGES = (
    "discover",
    "enrich",
    "score",
    "portfolio",
    "tailor",
    "cover",
    "pdf",
    "docx",
    "connect",
)

# In-memory run table (holds the live Popen objects for this API process).
_runs: dict[str, dict] = {}


class RunBody(BaseModel):
    stages: list[str] = Field(default_factory=lambda: ["score"])
    min_score: int = 7
    workers: int = 2


class ApplyBody(BaseModel):
    url: str | None = None
    dry_run: bool = True
    confirm: bool = False
    limit: int = 1


# ---------------------------------------------------------------------------
# User resolution
# ---------------------------------------------------------------------------

def _user_id(request: Request | None = None) -> str:
    """Resolve the active dashboard user from the request cookie, else env."""
    return resolve_dashboard_user(request)


def _jobwright_cmd(args: list[str], user_id: str) -> list[str]:
    return [sys.executable, "-m", "jobwright", "--user", user_id, *args]


# ---------------------------------------------------------------------------
# Durable run registry ({LOG_DIR}/web_runs.json)
# ---------------------------------------------------------------------------

def _registry_path() -> Path:
    return Path(config.LOG_DIR) / "web_runs.json"


def _load_registry() -> list[dict]:
    """Load the on-disk run registry; return [] if missing or corrupt."""
    path = _registry_path()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, ValueError, OSError):
        return []
    if not isinstance(data, list):
        return []
    return [e for e in data if isinstance(e, dict) and e.get("run_id")]


def _save_registry(entries: list[dict]) -> None:
    path = _registry_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(entries, indent=2), encoding="utf-8")
    except OSError:
        pass


def _upsert_registry(entry: dict) -> None:
    """Insert or replace a registry entry by run_id."""
    entries = [e for e in _load_registry() if e.get("run_id") != entry.get("run_id")]
    entries.append(entry)
    _save_registry(entries)


def _pid_running(pid: int | None) -> bool:
    """Best-effort liveness check for a bare PID (no live Popen handle)."""
    if not pid:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False
    return True


def _status_from_entry(run_id: str, entry: dict) -> dict:
    """Build a status dict, preferring the live Popen when present."""
    proc: subprocess.Popen | None = entry.get("proc")
    pid = entry.get("pid")
    if proc is not None:
        code = proc.poll()
        running = code is None
        pid = proc.pid
    else:
        code = None
        running = _pid_running(pid)
    return {
        "run_id": run_id,
        "pid": pid,
        "stages": entry.get("stages", []),
        "started_at": entry.get("started_at"),
        "running": running,
        "returncode": code,
        "log_path": entry.get("log_path"),
        "user": entry.get("user"),
    }


def _merged_entries() -> dict[str, dict]:
    """Merge in-memory runs with the on-disk registry (in-memory wins)."""
    merged: dict[str, dict] = {}
    for entry in _load_registry():
        merged[entry["run_id"]] = dict(entry)
    for run_id, entry in _runs.items():
        merged[run_id] = entry
    return merged


def _write_log_header(
    log_file, *, run_id: str, pid: int, user: str, cwd: str, cmd: list[str]
) -> None:
    quoted = " ".join(shlex.quote(c) for c in cmd)
    log_file.write(
        f"# run_id: {run_id}\n"
        f"# pid: {pid}\n"
        f"# user: {user}\n"
        f"# cwd: {cwd}\n"
        f"# cmd: {quoted}\n"
        f"# started (UTC): {datetime.now(timezone.utc).isoformat()}\n"
        f"$ {quoted}\n"
    )
    log_file.flush()


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post("/run")
def start_run(body: RunBody, request: Request) -> dict:
    stages = [s for s in body.stages if s in ALLOWED_STAGES]
    if not stages:
        raise HTTPException(400, f"No valid stages; allowed: {ALLOWED_STAGES}")

    user_id = _user_id(request)
    run_id = uuid.uuid4().hex[:12]
    log_dir = Path(config.LOG_DIR)
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / f"web_run_{run_id}.log"

    cmd = _jobwright_cmd(
        [
            "run",
            *stages,
            "-w",
            str(max(1, min(body.workers, 4))),
            "--min-score",
            str(body.min_score),
            "--verbose",
        ],
        user_id,
    )
    cwd = str(Path(__file__).resolve().parents[4])
    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"
    env["JOBWRIGHT_LOG_LEVEL"] = env.get("JOBWRIGHT_LOG_LEVEL", "INFO")

    with log_path.open("w", encoding="utf-8") as log_file:
        proc = subprocess.Popen(
            cmd,
            stdout=log_file,
            stderr=subprocess.STDOUT,
            cwd=cwd,
            env=env,
        )
        _write_log_header(
            log_file, run_id=run_id, pid=proc.pid, user=user_id, cwd=cwd, cmd=cmd
        )

    started_at = datetime.now(timezone.utc).isoformat()
    _runs[run_id] = {
        "proc": proc,
        "pid": proc.pid,
        "log_path": str(log_path),
        "stages": stages,
        "started_at": started_at,
        "cmd": cmd,
        "user": user_id,
    }
    _upsert_registry(
        {
            "run_id": run_id,
            "pid": proc.pid,
            "stages": stages,
            "started_at": started_at,
            "log_path": str(log_path),
            "user": user_id,
            "cmd": cmd,
        }
    )
    return {
        "run_id": run_id,
        "pid": proc.pid,
        "user": user_id,
        "stages": stages,
        "log_path": str(log_path),
    }


@router.get("/runs")
def list_runs() -> dict:
    entries = _merged_entries()
    runs = [_status_from_entry(rid, e) for rid, e in entries.items()]
    runs.sort(key=lambda r: (r.get("started_at") or ""), reverse=True)
    return {"runs": runs}


@router.get("/runs/{run_id}")
def run_status(run_id: str) -> dict:
    entries = _merged_entries()
    entry = entries.get(run_id)
    if not entry:
        raise HTTPException(404, "Unknown run_id")
    return _status_from_entry(run_id, entry)


@router.post("/runs/{run_id}/stop")
def stop_run(run_id: str) -> dict:
    info = _runs.get(run_id)
    if info is not None:
        proc: subprocess.Popen = info["proc"]
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                proc.kill()
                try:
                    proc.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    pass
        code = proc.poll()
        return {"run_id": run_id, "stopped": True, "returncode": code}

    # Only known from the on-disk registry: signal the bare PID.
    entry = next((e for e in _load_registry() if e.get("run_id") == run_id), None)
    if entry is None:
        raise HTTPException(404, "Unknown run_id")

    pid = entry.get("pid")
    if not _pid_running(pid):
        return {"run_id": run_id, "stopped": False, "returncode": None}
    try:
        os.kill(pid, signal.SIGTERM)
    except (ProcessLookupError, PermissionError, OSError):
        return {"run_id": run_id, "stopped": False, "returncode": None}
    return {"run_id": run_id, "stopped": True, "returncode": None}


@router.get("/stream/{run_id}")
async def stream_run(run_id: str) -> StreamingResponse:
    info = _runs.get(run_id)
    if not info:
        raise HTTPException(404, "Unknown run_id")
    log_path = Path(info["log_path"])
    proc: subprocess.Popen = info["proc"]

    async def event_gen() -> AsyncIterator[str]:
        pos = 0
        while True:
            if log_path.exists():
                data = log_path.read_bytes()
                if len(data) > pos:
                    chunk = data[pos:].decode("utf-8", errors="replace")
                    pos = len(data)
                    for line in chunk.splitlines():
                        yield f"data: {line}\n\n"
            code = proc.poll()
            if code is not None:
                yield f"data: [done RC={code}]\n\n"
                yield "event: done\ndata: {}\n\n"
                break
            await asyncio.sleep(0.5)

    return StreamingResponse(event_gen(), media_type="text/event-stream")


@router.post("/apply")
def apply_job(body: ApplyBody, request: Request) -> dict:
    """Gated apply: dry-run by default; live requires confirm + apply_enabled."""
    user_id = _user_id(request)
    live = not body.dry_run
    if live:
        if not body.confirm:
            raise HTTPException(400, "Live apply requires confirm=true")
        if not is_apply_enabled(user_id):
            raise HTTPException(403, f"apply_enabled is false for user {user_id}")

    args = ["apply", "-w", "1", "--limit", str(max(1, body.limit))]
    if body.dry_run:
        args.append("--dry-run")
    else:
        args.append("--live")
    if body.url:
        args.extend(["--url", body.url])

    run_id = uuid.uuid4().hex[:12]
    log_dir = Path(config.LOG_DIR)
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / f"web_apply_{run_id}.log"
    cmd = _jobwright_cmd(args, user_id)
    cwd = str(Path(__file__).resolve().parents[4])
    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"
    env["JOBWRIGHT_LOG_LEVEL"] = env.get("JOBWRIGHT_LOG_LEVEL", "INFO")

    with log_path.open("w", encoding="utf-8") as log_file:
        proc = subprocess.Popen(
            cmd,
            stdout=log_file,
            stderr=subprocess.STDOUT,
            cwd=cwd,
            env=env,
        )
        _write_log_header(
            log_file, run_id=run_id, pid=proc.pid, user=user_id, cwd=cwd, cmd=cmd
        )

    started_at = datetime.now(timezone.utc).isoformat()
    _runs[run_id] = {
        "proc": proc,
        "pid": proc.pid,
        "log_path": str(log_path),
        "stages": ["apply"],
        "started_at": started_at,
        "cmd": cmd,
        "user": user_id,
    }
    _upsert_registry(
        {
            "run_id": run_id,
            "pid": proc.pid,
            "stages": ["apply"],
            "started_at": started_at,
            "log_path": str(log_path),
            "user": user_id,
            "cmd": cmd,
        }
    )
    return {
        "run_id": run_id,
        "pid": proc.pid,
        "user": user_id,
        "dry_run": body.dry_run,
        "log_path": str(log_path),
        "url": body.url,
    }


@router.post("/jobs/{url:path}/applied")
def mark_applied(url: str) -> dict:
    """Mark a job applied without running the browser agent."""
    from jobwright.apply.launcher import mark_job
    from jobwright.web.routers.board import _row_to_card

    url = unquote(url)
    conn = get_connection()
    exists = conn.execute("SELECT 1 FROM jobs WHERE url = ?", (url,)).fetchone()
    if not exists:
        raise HTTPException(404, "Job not found")
    mark_job(url, "applied")
    row = conn.execute("SELECT * FROM jobs WHERE url = ?", (url,)).fetchone()
    return _row_to_card(row)
