"""Evidence for every apply attempt: a ``submissions`` row plus a run folder.

Run folder: ``<user dir>/apply-runs/<run_id>/`` (0700) holding
``filled.png`` (form filled), ``review.png`` (just before the final submit, or
the dry-run stop point), ``confirmation.png`` (after submit), any
``step-*.png`` the agent took, ``transcript.jsonl`` (every model turn and tool
call; secrets are never in it: tool results only say "[secret]") and
``answers.json`` (every field label / value / source).
"""

from __future__ import annotations

import json
import os
import secrets
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from jobwright import config
from jobwright.apply.fill import FieldRecord, Need
from jobwright.database import get_connection

SCREENSHOT_NAMES = ("filled", "review", "confirmation")


def new_run_id() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + secrets.token_hex(3)


def runs_root() -> Path:
    return Path(config.APP_DIR) / "apply-runs"


def run_dir(run_id: str) -> Path:
    d = runs_root() / run_id
    d.mkdir(parents=True, exist_ok=True)
    for p in (runs_root(), d):
        try:
            p.chmod(0o700)
        except OSError:
            pass
    return d


class Transcript:
    """Append-only JSONL log. ``forbidden`` values must never appear in it."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.forbidden: set[str] = set()

    def forbid(self, value: str | None) -> None:
        if value and len(value) >= 4:
            self.forbidden.add(value)

    def scrub(self, text: str) -> str:
        for secret in self.forbidden:
            if secret in text:
                text = text.replace(secret, "[secret]")
        return text

    def write(self, kind: str, data: Any) -> None:
        line = json.dumps({"at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "kind": kind,
                           "data": data}, default=str, ensure_ascii=False)
        line = self.scrub(line)
        fd = os.open(str(self.path), os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
        with os.fdopen(fd, "a", encoding="utf-8") as fh:
            fh.write(line + "\n")


def start_submission(job: dict, run_id: str, *, ats: str | None, provider: str, model: str | None,
                     dry_run: bool, conn=None) -> int:
    conn = conn or get_connection()
    cur = conn.execute(
        "INSERT INTO submissions (run_id, job_url, job_id, company, title, dedupe_key, ats, provider, model, "
        "dry_run, outcome, run_dir, started_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'running', ?, ?)",
        (run_id, job.get("url"), job.get("job_id"), job.get("company") or job.get("site"), job.get("title"),
         job.get("dedupe_key"), ats, provider, model, 1 if dry_run else 0, str(run_dir(run_id)),
         datetime.now(timezone.utc).isoformat(timespec="seconds")),
    )
    conn.commit()
    return int(cur.lastrowid)


def finish_submission(
    submission_id: int,
    *,
    outcome: str,
    fields: list[FieldRecord],
    needs: list[Need],
    screenshots: dict[str, str],
    transcript_path: str | None,
    verification_confidence: str | None = None,
    verification_evidence: str | None = None,
    steps: int = 0,
    input_tokens: int = 0,
    output_tokens: int = 0,
    cost_usd: float | None = None,
    error: str | None = None,
    conn=None,
) -> None:
    conn = conn or get_connection()
    row = conn.execute("SELECT run_dir FROM submissions WHERE id = ?", (submission_id,)).fetchone()
    field_dicts = [f.as_dict() for f in fields]
    if row and row["run_dir"]:
        path = Path(row["run_dir"]) / "answers.json"
        fd = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump({"fields": field_dicts, "needs": [n.as_dict() for n in needs]}, fh, indent=2,
                      ensure_ascii=False)
    conn.execute(
        "UPDATE submissions SET outcome = ?, verification_confidence = ?, verification_evidence = ?, "
        "fields_json = ?, needs_json = ?, screenshots_json = ?, transcript_path = ?, steps = ?, "
        "input_tokens = ?, output_tokens = ?, cost_usd = ?, error = ?, finished_at = ? WHERE id = ?",
        (outcome, verification_confidence, verification_evidence, json.dumps(field_dicts, ensure_ascii=False),
         json.dumps([n.as_dict() for n in needs], ensure_ascii=False), json.dumps(screenshots), transcript_path,
         steps, input_tokens, output_tokens, cost_usd, (error or "")[:500] or None,
         datetime.now(timezone.utc).isoformat(timespec="seconds"), submission_id),
    )
    conn.commit()


def _decode(row: dict) -> dict:
    out = dict(row)
    for key, default in (("fields_json", []), ("needs_json", []), ("screenshots_json", {})):
        try:
            out[key.removesuffix("_json")] = json.loads(out.pop(key) or "null") or default
        except ValueError:
            out[key.removesuffix("_json")] = default
    out["dry_run"] = bool(out.get("dry_run"))
    out.pop("run_dir", None)
    out.pop("transcript_path", None)
    return out


def get_submission(submission_id: int, conn=None) -> dict | None:
    conn = conn or get_connection()
    row = conn.execute("SELECT * FROM submissions WHERE id = ?", (submission_id,)).fetchone()
    return _decode(dict(row)) if row else None


def list_submissions(limit: int = 50, conn=None, since: str | None = None) -> list[dict]:
    conn = conn or get_connection()
    if since:
        rows = conn.execute("SELECT * FROM submissions WHERE started_at >= ? ORDER BY id DESC LIMIT ?",
                            (since, limit)).fetchall()
    else:
        rows = conn.execute("SELECT * FROM submissions ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
    return [_decode(dict(r)) for r in rows]


def submission_file(submission_id: int, name: str, conn=None) -> Path | None:
    """A screenshot of a submission, confined to its run folder (png only)."""
    conn = conn or get_connection()
    row = conn.execute("SELECT run_dir, screenshots_json FROM submissions WHERE id = ?",
                       (submission_id,)).fetchone()
    if not row or not row["run_dir"]:
        return None
    try:
        shots = json.loads(row["screenshots_json"] or "{}")
    except ValueError:
        shots = {}
    rel = shots.get(name)
    if not rel:
        return None
    base = Path(row["run_dir"]).resolve()
    path = (base / rel).resolve()
    if base not in path.parents or path.suffix != ".png" or not path.is_file():
        return None
    return path
