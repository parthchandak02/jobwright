"""Human relevance labels (append-only) and the evaluation set built from them.

Every human rescore is appended to ``score_labels`` with a snapshot of the job,
so labels survive pruning and every future rescore is kept, not overwritten.
``jobs.user_fit_score`` mirrors the latest label for the board.

The eval set combines explicit labels with implicit board signals:
  positive  applied / in_progress / offer (or ever reached applied), or label >= 7
  negative  label <= 4, or closed by the human without ever applying
  ignored   labels 5-6 (ambiguous "good role, but..."), everything unlabeled
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone

from jobwright.database import get_connection, job_id_for_url

POSITIVE_MIN = 7
NEGATIVE_MAX = 4
_SNAPSHOT_CHARS = 6000


def record_label(
    url: str,
    score: int,
    *,
    rationale: str = "",
    reasons: list[str] | None = None,
    source: str = "dashboard",
    actor: str | None = None,
    conn: sqlite3.Connection | None = None,
    created_at: str | None = None,
    update_job: bool = True,
) -> int:
    """Append a label and mirror it onto the job. Returns the label id."""
    if not 1 <= int(score) <= 10:
        raise ValueError("label score must be between 1 and 10")
    conn = conn or get_connection()
    row = conn.execute(
        "SELECT title, company, location, full_description, description, fit_score FROM jobs WHERE url = ?",
        (url,),
    ).fetchone()
    if row is None:
        raise KeyError(url)
    now = created_at or datetime.now(timezone.utc).isoformat()
    verdict = "relevant" if score >= POSITIVE_MIN else ("not_relevant" if score <= NEGATIVE_MAX else "mixed")
    cur = conn.execute(
        "INSERT INTO score_labels (job_url, job_id, label_score, verdict, reasons, rationale, source, actor, "
        "model_score, title, company, location, description, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            url, job_id_for_url(url), int(score), verdict,
            json.dumps(reasons or []), rationale.strip(), source, actor,
            row[5], row[0], row[1], row[2],
            ((row[3] or row[4]) or "")[:_SNAPSHOT_CHARS], now,
        ),
    )
    if update_job:
        conn.execute(
            "UPDATE jobs SET user_fit_score = ?, user_score_rationale = ?, user_score_at = ?, "
            "board_updated_by = 'human', board_updated_at = ? WHERE url = ?",
            (int(score), rationale.strip(), now, now, url),
        )
    conn.commit()
    return int(cur.lastrowid)


def clear_label(url: str, *, actor: str | None = None, conn: sqlite3.Connection | None = None) -> None:
    """Clear the job's current label; history keeps a 'cleared' marker row."""
    conn = conn or get_connection()
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        "INSERT INTO score_labels (job_url, job_id, label_score, verdict, source, actor, created_at) "
        "VALUES (?, ?, 0, 'cleared', 'dashboard', ?, ?)",
        (url, job_id_for_url(url), actor, now),
    )
    conn.execute(
        "UPDATE jobs SET user_fit_score = NULL, user_score_rationale = NULL, user_score_at = NULL, "
        "board_updated_by = 'human', board_updated_at = ? WHERE url = ?",
        (now, url),
    )
    conn.commit()


def import_existing_user_scores(conn: sqlite3.Connection) -> int:
    """One-time: copy pre-existing jobs.user_fit_score rows into score_labels."""
    rows = conn.execute(
        "SELECT url, user_fit_score, user_score_rationale, user_score_at FROM jobs "
        "WHERE user_fit_score IS NOT NULL"
    ).fetchall()
    n = 0
    for url, score, rationale, at in rows:
        exists = conn.execute("SELECT 1 FROM score_labels WHERE job_url = ?", (url,)).fetchone()
        if exists:
            continue
        record_label(
            url, int(score), rationale=rationale or "", source="import_pre_v06",
            conn=conn, created_at=at, update_job=False,
        )
        n += 1
    return n


def label_history(url: str, conn: sqlite3.Connection | None = None) -> list[dict]:
    conn = conn or get_connection()
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT id, label_score, verdict, reasons, rationale, source, actor, model_score, created_at "
        "FROM score_labels WHERE job_url = ? ORDER BY created_at, id",
        (url,),
    ).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        try:
            d["reasons"] = json.loads(d.get("reasons") or "[]")
        except ValueError:
            d["reasons"] = []
        out.append(d)
    return out


@dataclass
class EvalItem:
    url: str
    title: str
    company: str
    location: str
    description: str
    salary: str
    label: int  # 1 relevant, 0 not relevant
    source: str
    label_score: int | None
    rationale: str
    dedupe_key: str | None
    model_score: int | None


def _latest_labels(conn: sqlite3.Connection) -> dict[str, sqlite3.Row]:
    conn.row_factory = sqlite3.Row
    latest: dict[str, sqlite3.Row] = {}
    for r in conn.execute("SELECT * FROM score_labels ORDER BY created_at, id"):
        latest[r["job_url"]] = r
    return latest


def build_eval_set(conn: sqlite3.Connection | None = None) -> list[EvalItem]:
    """Labeled examples for offline scoring evals and few-shot retrieval."""
    conn = conn or get_connection()
    conn.row_factory = sqlite3.Row
    labels = _latest_labels(conn)
    ever_applied = {
        r[0]
        for r in conn.execute(
            "SELECT DISTINCT job_url FROM stage_history WHERE to_stage IN ('applied', 'in_progress', 'offer')"
        )
    }
    jobs = {r["url"]: r for r in conn.execute("SELECT * FROM jobs")}
    items: dict[str, EvalItem] = {}

    for url, lab in labels.items():
        if lab["verdict"] == "cleared":
            continue
        score = int(lab["label_score"])
        job = jobs.get(url)
        applied = url in ever_applied or (job is not None and job["applied_at"] is not None)
        if applied or score >= POSITIVE_MIN:
            label = 1
        elif score <= NEGATIVE_MAX:
            label = 0
        else:
            continue
        desc = (job["full_description"] if job is not None else None) or lab["description"] or ""
        items[url] = EvalItem(
            url=url,
            title=(job["title"] if job is not None else lab["title"]) or "",
            company=(job["company"] if job is not None else lab["company"]) or "",
            location=(job["location"] if job is not None else lab["location"]) or "",
            description=desc,
            salary=(job["salary"] if job is not None else "") or "",
            label=label,
            source="label+applied" if applied else "label",
            label_score=score,
            rationale=lab["rationale"] or "",
            dedupe_key=job["dedupe_key"] if job is not None else None,
            model_score=lab["model_score"],
        )

    for url, job in jobs.items():
        if url in items or url in labels:
            continue
        stage = job["funnel_stage"] or "backlog"
        applied = url in ever_applied or job["applied_at"] is not None or stage in ("applied", "in_progress", "offer")
        if applied:
            label, source = 1, "applied"
        elif stage == "closed" and (job["board_updated_by"] or "") == "human":
            label, source = 0, "closed_unapplied"
        else:
            continue
        if not (job["full_description"] or "").strip():
            continue
        items[url] = EvalItem(
            url=url, title=job["title"] or "", company=job["company"] or "", location=job["location"] or "",
            description=job["full_description"] or "", salary=job["salary"] or "", label=label, source=source,
            label_score=None, rationale=job["close_reason"] or "", dedupe_key=job["dedupe_key"],
            model_score=job["fit_score"],
        )
    return list(items.values())
