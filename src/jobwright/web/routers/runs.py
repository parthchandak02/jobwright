"""Pipeline run triggers, SSE logs, gated apply, and a durable run registry."""

from __future__ import annotations

import asyncio
import os
import shlex
import signal
import subprocess
import sys
import time
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
from jobwright.run_registry import load_registry as _load_registry
from jobwright.run_registry import upsert_registry as _upsert_registry
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
    # Signal 0 succeeds on zombies. If we are the parent, reap and treat as dead.
    try:
        waited, _ = os.waitpid(pid, os.WNOHANG)
        if waited == pid:
            return False
    except ChildProcessError:
        pass
    except OSError:
        pass
    return True


def _dedicated_pgid(pid: int) -> int | None:
    """Return the process group id if this PID is a session leader we spawned.

    Pipeline runs use start_new_session=True so pgid == pid. Never return our
    own group (the API / uvicorn worker) — killpg on that would take down the
    dashboard.
    """
    try:
        pgid = os.getpgid(pid)
    except OSError:
        return None
    if pgid != pid:
        return None
    try:
        if pgid == os.getpgrp():
            return None
    except OSError:
        return None
    return pgid


def _kill_run(pid: int | None, proc: subprocess.Popen | None = None, grace: float = 3.0) -> int | None:
    """SIGTERM then SIGKILL the run's process group (or the single PID)."""
    if not pid and proc is not None:
        pid = proc.pid
    if not pid:
        return proc.poll() if proc is not None else None

    pgid = _dedicated_pgid(pid)

    def _send(sig: int) -> None:
        if pgid is not None:
            try:
                os.killpg(pgid, sig)
                return
            except (ProcessLookupError, PermissionError, OSError):
                pass
        if proc is not None and proc.poll() is None:
            if sig == signal.SIGKILL:
                proc.kill()
            else:
                proc.terminate()
            return
        try:
            os.kill(pid, sig)
        except (ProcessLookupError, PermissionError, OSError):
            pass

    _send(signal.SIGTERM)
    if proc is not None:
        try:
            proc.wait(timeout=grace)
        except subprocess.TimeoutExpired:
            _send(signal.SIGKILL)
            try:
                proc.wait(timeout=grace)
            except subprocess.TimeoutExpired:
                pass
        return proc.poll()

    deadline = time.time() + grace
    while time.time() < deadline:
        if not _pid_running(pid):
            return None
        time.sleep(0.05)
    _send(signal.SIGKILL)
    try:
        os.waitpid(pid, os.WNOHANG)
    except (ChildProcessError, OSError):
        pass
    time.sleep(0.05)
    return None


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
        "kind": entry.get("kind") or "pipeline",
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


def spawn_logged_run(
    *,
    args: list[str],
    user_id: str,
    stages: list[str],
    log_name: str,
    kind: str,
    extra_env: dict[str, str] | None = None,
) -> dict:
    """Spawn a jobwright subprocess, tee stdout to a log file, register the run."""
    run_id = uuid.uuid4().hex[:12]
    log_dir = Path(config.LOG_DIR)
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / f"{log_name}_{run_id}.log"
    cmd = _jobwright_cmd(args, user_id)
    cwd = str(Path(__file__).resolve().parents[4])
    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"
    env["JOBWRIGHT_WEB_RUN_ID"] = run_id
    if extra_env:
        env.update(extra_env)
    env.setdefault("JOBWRIGHT_LOG_LEVEL", "INFO")
    # Default tailor batch is 10; Auto Search needs more prepare slots.
    if kind == "pipeline":
        env.setdefault("APPLY_PREP_LIMIT", "25")
        env.setdefault("APPLY_MIN_SCORE", "7")

    with log_path.open("w", encoding="utf-8") as log_file:
        proc = subprocess.Popen(
            cmd,
            stdout=log_file,
            stderr=subprocess.STDOUT,
            cwd=cwd,
            env=env,
            start_new_session=True,
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
        "kind": kind,
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
            "kind": kind,
        }
    )
    return {
        "run_id": run_id,
        "pid": proc.pid,
        "user": user_id,
        "stages": stages,
        "log_path": str(log_path),
        "kind": kind,
    }


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post("/run")
def start_run(body: RunBody, request: Request) -> dict:
    stages = [s for s in body.stages if s in ALLOWED_STAGES]
    if not stages:
        raise HTTPException(400, f"No valid stages; allowed: {ALLOWED_STAGES}")

    return spawn_logged_run(
        args=[
            "run",
            *stages,
            "-w",
            str(max(1, min(body.workers, 4))),
            "--min-score",
            str(body.min_score),
            "--verbose",
        ],
        user_id=_user_id(request),
        stages=stages,
        log_name="web_run",
        kind="pipeline",
    )


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
        code = _kill_run(info.get("pid") or proc.pid, proc=proc)
        return {"run_id": run_id, "stopped": True, "returncode": code}

    # Only known from the on-disk registry (API reload dropped the Popen handle).
    entry = next((e for e in _load_registry() if e.get("run_id") == run_id), None)
    if entry is None:
        raise HTTPException(404, "Unknown run_id")

    pid = entry.get("pid")
    if not _pid_running(pid):
        return {"run_id": run_id, "stopped": True, "returncode": None}
    _kill_run(pid)
    return {"run_id": run_id, "stopped": not _pid_running(pid), "returncode": None}


@router.get("/stream/{run_id}")
async def stream_run(run_id: str) -> StreamingResponse:
    merged = _merged_entries()
    info = merged.get(run_id)
    if not info:
        raise HTTPException(404, "Unknown run_id")
    log_path = Path(info["log_path"])
    proc: subprocess.Popen | None = info.get("proc")
    pid = info.get("pid")

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
            if proc is not None:
                code = proc.poll()
                done = code is not None
            else:
                code = None
                done = not _pid_running(pid)
            if done:
                yield f"data: [done RC={code if code is not None else 0}]\n\n"
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

    handle = spawn_logged_run(
        args=args,
        user_id=user_id,
        stages=["apply"],
        log_name="web_apply",
        kind="apply",
    )
    return {
        **handle,
        "dry_run": body.dry_run,
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
