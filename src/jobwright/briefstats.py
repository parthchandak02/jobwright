"""Jobwright scoreboard: per-brief notify history + precision tracking (D4).

Records one ``brief_items`` row per candidate prepare-stage job at each
``notify`` send, so we can later measure a precision proxy (items that moved
to applied / in_progress over items shown). Read-only over existing funnel
data (``jobs.funnel_stage``) — this module never mutates the jobs table.

The table DDL lives here (not in ``database.py``) because this module owns the
scoreboard feature. Importing this module does not touch the schema by itself;
call :func:`ensure_brief_items` to create the table (idempotent).
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta
from typing import Any

from jobwright.database import get_connection, job_id_for_url

# ---------------------------------------------------------------------------
# brief_items schema (DDL owned here)
# ---------------------------------------------------------------------------

_BRIEF_ITEMS_DDL = """
CREATE TABLE IF NOT EXISTS brief_items (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    brief_date TEXT NOT NULL,          -- YYYY-MM-DD of the notify run
    job_url    TEXT NOT NULL,
    job_id     TEXT,                   -- dashboard deep-link id (blake2 hash)
    fit_score  INTEGER,                -- effective score shown/sorted by
    jev_score  REAL,                   -- nullable: Jev fast-path score (D3)
    cap_rank   INTEGER,                -- 1..N within a given brief's cap; NULL if not shown
    shown      INTEGER NOT NULL DEFAULT 0  -- 1 if this item was in the notify list
);
"""


def ensure_brief_items(conn: sqlite3.Connection | None = None) -> None:
    """Create the brief_items table if it does not exist (idempotent)."""
    if conn is None:
        conn = get_connection()
    conn.execute(_BRIEF_ITEMS_DDL)
    conn.commit()


# ---------------------------------------------------------------------------
# jev_score is provided by the D3 fastpath (other teammate owns it). It may be
# missing from the jobs table in older DBs, so read it defensively.
# ---------------------------------------------------------------------------

def _has_column(conn: sqlite3.Connection, column: str) -> bool:
    cols = {row[1] for row in conn.execute("PRAGMA table_info(jobs)").fetchall()}
    return column in cols


def _fetch_jev_scores(conn: sqlite3.Connection, urls: list[str]) -> dict[str, Any]:
    """Return {job_url: jev_score} for the given urls, or {} if no jev column."""
    if not urls or not _has_column(conn, "jev_score"):
        return {}
    placeholders = ", ".join("?" for _ in urls)
    rows = conn.execute(
        f"SELECT url, jev_score FROM jobs WHERE url IN ({placeholders})", urls
    ).fetchall()
    return {row["url"]: row["jev_score"] for row in rows if row["jev_score"] is not None}


def record_brief_items(
    jobs: list[dict],
    shown_urls: list[str],
    *,
    brief_date: str | None = None,
    conn: sqlite3.Connection | None = None,
) -> int:
    """Record a brief_items snapshot of the candidate jobs for this notify run.

    ``jobs`` is the full, fit-score-desc-sorted candidate list (from
    ``get_unnotified_prepare_jobs``). ``shown_urls`` is the capped subset that
    was actually sent; only those get ``shown=1`` and a ``cap_rank`` (1..N in
    list order). Jobs below the cap are recorded with ``shown=0`` and no rank.

    Idempotent at the (brief_date, job_url, shown) tuple level: re-recording
    the same snapshot does not duplicate rows. Returns the number of rows
    written.
    """
    if conn is None:
        conn = get_connection()
    ensure_brief_items(conn)
    # Local calendar date for the notify run (not UTC) so daily grouping matches
    # the user's brief day.
    brief_date = brief_date or datetime.now().strftime("%Y-%m-%d")  # noqa: DTZ005
    shown_set = set(shown_urls)

    existing = {
        (r["brief_date"], r["job_url"], int(r["shown"]))
        for r in conn.execute(
            "SELECT brief_date, job_url, shown FROM brief_items WHERE brief_date = ?",
            (brief_date,),
        ).fetchall()
    }

    urls = [job.get("url") or "" for job in jobs]
    jev = _fetch_jev_scores(conn, [u for u in urls if u])

    writes = 0
    for rank, job in enumerate(jobs, start=1):
        url = job.get("url") or ""
        if not url:
            continue
        shown = 1 if url in shown_set else 0
        cap_rank = rank if shown else None
        key = (brief_date, url, shown)
        if key in existing:
            continue
        fit_score = job.get("fit_score")
        try:
            fit_score = int(fit_score) if fit_score is not None else None
        except (TypeError, ValueError):
            fit_score = None
        conn.execute(
            "INSERT INTO brief_items "
            "(brief_date, job_url, job_id, fit_score, jev_score, cap_rank, shown) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                brief_date,
                url,
                job_id_for_url(url),
                fit_score,
                jev.get(url),
                cap_rank,
                shown,
            ),
        )
        writes += 1
    conn.commit()
    return writes


# ---------------------------------------------------------------------------
# Scoreboard
# ---------------------------------------------------------------------------

def _funnel_state(row: dict) -> str:
    stage = (row.get("funnel_stage") or "backlog").strip().lower()
    if stage in ("applied", "in_progress", "offer"):
        return stage
    if stage == "closed":
        return "closed"
    if stage == "prepare":
        # Gated users: materials are generated only after a human review, so
        # reaching prepare IS the user signaling interest — count as advanced.
        return "advanced"
    return "untouched"  # backlog / anything else


def briefstats(
    user: str | None = None,
    days: int = 14,
    conn: sqlite3.Connection | None = None,
) -> list[dict]:
    """Per-brief precision report over the last ``days`` days (read-only).

    Categories per brief (from each shown item's *current* funnel stage):
      applied / in_progress / offer — moved forward (advanced)
      closed                          — no longer active
      untouched                       — still backlog/prepare

    Precision proxy = advanced / shown, where advanced = applied + in_progress.

    ``user`` is stored on the returned rows for convenience but is not used to
    scope the query (this runs against the active user's database). Returns a
    list of dicts, most recent brief first.
    """
    if conn is None:
        conn = get_connection()
    ensure_brief_items(conn)

    # Local calendar-day cutoff; days < 0 never match anything (>= 1 enforced).
    cutoff = (datetime.now() - timedelta(days=max(days, 1))).strftime("%Y-%m-%d")  # noqa: DTZ005

    rows = conn.execute(
        """
        SELECT bi.brief_date, bi.job_url,
               MAX(bi.shown) AS shown,
               MAX(bi.fit_score) AS fit_score,
               MAX(bi.jev_score) AS jev_score,
               MAX(bi.cap_rank) AS cap_rank,
               j.funnel_stage
        FROM brief_items bi
        LEFT JOIN jobs j ON j.url = bi.job_url
        WHERE bi.brief_date >= ?
        GROUP BY bi.brief_date, bi.job_url
        ORDER BY bi.brief_date DESC, shown DESC, bi.cap_rank ASC
        """,
        (cutoff,),
    ).fetchall()

    per_brief: dict[str, dict] = {}
    for r in rows:
        date = r["brief_date"]
        state = _funnel_state(dict(r))
        b = per_brief.setdefault(
            date,
            {"brief_date": date, "shown": 0, "recorded": 0,
             "applied": 0, "in_progress": 0, "offer": 0, "closed": 0,
             "untouched": 0, "advanced": 0, "precision": None},
        )
        b["recorded"] += 1
        if r["shown"]:
            b["shown"] += 1
            b[state] += 1
            if state in ("applied", "in_progress"):
                b["advanced"] += 1

    out: list[dict] = []
    for date in sorted(per_brief, reverse=True):
        b = per_brief[date]
        if b["shown"]:
            b["precision"] = round(b["advanced"] / b["shown"], 3)
        b["user"] = user
        out.append(b)
    return out