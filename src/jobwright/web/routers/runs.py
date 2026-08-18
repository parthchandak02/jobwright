"""Pipeline run triggers, SSE logs, and gated apply."""

from __future__ import annotations

import asyncio
import os
import shlex
import subprocess
import sys
import uuid
from collections.abc import AsyncIterator
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import unquote

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from jobwright import config
from jobwright.database import get_connection
from jobwright.users import is_apply_enabled

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


def _user_id() -> str:
    return os.environ.get("JOBWRIGHT_DASHBOARD_USER", "richa")


def _jobwright_cmd(args: list[str]) -> list[str]:
    return [sys.executable, "-m", "jobwright", "--user", _user_id(), *args]


@router.post("/run")
def start_run(body: RunBody) -> dict:
    stages = [s for s in body.stages if s in ALLOWED_STAGES]
    if not stages:
        raise HTTPException(400, f"No valid stages; allowed: {ALLOWED_STAGES}")

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
        ]
    )
    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"

    with log_path.open("w", encoding="utf-8") as log_file:
        log_file.write(f"$ {' '.join(shlex.quote(c) for c in cmd)}\n")
        log_file.flush()
        proc = subprocess.Popen(
            cmd,
            stdout=log_file,
            stderr=subprocess.STDOUT,
            cwd=str(Path(__file__).resolve().parents[4]),
            env=env,
        )

    _runs[run_id] = {
        "proc": proc,
        "log_path": str(log_path),
        "stages": stages,
        "started_at": datetime.now(timezone.utc).isoformat(),
        "cmd": cmd,
    }
    return {"run_id": run_id, "stages": stages, "log_path": str(log_path)}


@router.get("/runs/{run_id}")
def run_status(run_id: str) -> dict:
    info = _runs.get(run_id)
    if not info:
        raise HTTPException(404, "Unknown run_id")
    proc: subprocess.Popen = info["proc"]
    code = proc.poll()
    return {
        "run_id": run_id,
        "stages": info["stages"],
        "started_at": info["started_at"],
        "running": code is None,
        "returncode": code,
        "log_path": info["log_path"],
    }


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
def apply_job(body: ApplyBody) -> dict:
    """Gated apply: dry-run by default; live requires confirm + apply_enabled."""
    user_id = _user_id()
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
    cmd = _jobwright_cmd(args)
    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"

    with log_path.open("w", encoding="utf-8") as log_file:
        log_file.write(f"$ {' '.join(shlex.quote(c) for c in cmd)}\n")
        log_file.flush()
        proc = subprocess.Popen(
            cmd,
            stdout=log_file,
            stderr=subprocess.STDOUT,
            cwd=str(Path(__file__).resolve().parents[4]),
            env=env,
        )

    _runs[run_id] = {
        "proc": proc,
        "log_path": str(log_path),
        "stages": ["apply"],
        "started_at": datetime.now(timezone.utc).isoformat(),
        "cmd": cmd,
    }
    return {
        "run_id": run_id,
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
