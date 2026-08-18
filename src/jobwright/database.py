"""jobwright database layer: schema, migrations, stats, and connection helpers.

Single source of truth for the jobs table schema. All columns from every
pipeline stage are created up front so any stage can run independently
without migration ordering issues.
"""

import hashlib
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path

import jobwright.config as config

# Thread-local connection storage — each thread gets its own connection
# (required for SQLite thread safety with parallel workers)
_local = threading.local()


def get_connection(db_path: Path | str | None = None) -> sqlite3.Connection:
    """Get a thread-local cached SQLite connection with WAL mode enabled.

    Each thread gets its own connection (required for SQLite thread safety).
    Connections are cached and reused within the same thread.

    Args:
        db_path: Override the default DB_PATH. Useful for testing.

    Returns:
        sqlite3.Connection configured with WAL mode and row factory.
    """
    path = str(db_path or config.DB_PATH)

    if not hasattr(_local, 'connections'):
        _local.connections = {}

    conn = _local.connections.get(path)
    if conn is not None:
        try:
            conn.execute("SELECT 1")
            return conn
        except sqlite3.ProgrammingError:
            pass

    conn = sqlite3.connect(path, timeout=30)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=10000")
    conn.row_factory = sqlite3.Row
    _local.connections[path] = conn
    return conn


def close_connection(db_path: Path | str | None = None) -> None:
    """Close the cached connection for the current thread."""
    path = str(db_path or config.DB_PATH)
    if hasattr(_local, 'connections'):
        conn = _local.connections.pop(path, None)
        if conn is not None:
            conn.close()


def init_db(db_path: Path | str | None = None) -> sqlite3.Connection:
    """Create the full jobs table with all columns from every pipeline stage.

    This is idempotent -- safe to call on every startup. Uses CREATE TABLE IF NOT EXISTS
    so it won't destroy existing data.

    Schema columns by stage:
      - Discovery:  url, title, salary, description, location, site, strategy, discovered_at
      - Enrichment: full_description, application_url, detail_scraped_at, detail_error
      - Scoring:    fit_score, score_reasoning, scored_at
      - Tailoring:  tailored_resume_path, tailored_at, tailor_attempts
      - Cover:      cover_letter_path, cover_letter_at, cover_attempts
      - Apply:      applied_at, apply_status, apply_error, apply_attempts,
                   agent_id, last_attempted_at, apply_duration_ms, apply_task_id,
                   verification_confidence

    Args:
        db_path: Override the default DB_PATH.

    Returns:
        sqlite3.Connection with the schema initialized.
    """
    path = db_path or config.DB_PATH

    # Ensure parent directory exists
    Path(path).parent.mkdir(parents=True, exist_ok=True)

    conn = get_connection(path)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS jobs (
            -- Discovery stage (smart_extract / job_search)
            url                   TEXT PRIMARY KEY,
            title                 TEXT,
            salary                TEXT,
            description           TEXT,
            location              TEXT,
            site                  TEXT,
            company               TEXT,
            strategy              TEXT,
            discovered_at         TEXT,

            -- Enrichment stage (detail_scraper)
            full_description      TEXT,
            application_url       TEXT,
            detail_scraped_at     TEXT,
            detail_error          TEXT,

            -- Scoring stage (job_scorer)
            fit_score             INTEGER,
            score_reasoning       TEXT,
            scored_at             TEXT,
            portfolio_project_ids TEXT,

            -- Tailoring stage (resume tailor)
            tailored_resume_path  TEXT,
            tailored_resume_docx_path TEXT,
            tailored_at           TEXT,
            tailor_attempts       INTEGER DEFAULT 0,

            -- Cover letter stage
            cover_letter_path     TEXT,
            cover_letter_docx_path TEXT,
            cover_letter_at       TEXT,
            cover_attempts        INTEGER DEFAULT 0,

            -- Application stage
            applied_at            TEXT,
            apply_status          TEXT,
            apply_error           TEXT,
            apply_attempts        INTEGER DEFAULT 0,
            agent_id              TEXT,
            last_attempted_at     TEXT,
            apply_duration_ms     INTEGER,
            apply_task_id         TEXT,
            verification_confidence TEXT,

            -- Kanban board (stored funnel stage; pipeline eligibility stays timestamp-based)
            funnel_stage          TEXT DEFAULT 'backlog',
            outcome               TEXT,
            source                TEXT DEFAULT 'discovered',
            applied_manually      INTEGER DEFAULT 0,
            notes                 TEXT,
            follow_up_at          TEXT,
            first_response_at     TEXT,
            board_updated_by      TEXT,
            board_updated_at      TEXT,

            -- WhatsApp daily notify (deduped one-shot per prepare job)
            whatsapp_notified_at  TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS stage_history (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            job_url    TEXT NOT NULL,
            from_stage TEXT,
            to_stage   TEXT NOT NULL,
            actor      TEXT NOT NULL,
            at         TEXT NOT NULL,
            note       TEXT,
            FOREIGN KEY (job_url) REFERENCES jobs(url)
        )
    """)
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_stage_history_job_at "
        "ON stage_history(job_url, at)"
    )
    conn.commit()

    # Run migrations for any columns added after initial schema
    ensure_columns(conn)
    backfill_sponsorship_status(conn)
    backfill_funnel_stages(conn)

    return conn


# Complete column registry: column_name -> SQL type with optional default.
# This is the single source of truth. Adding a column here is all that's needed
# for it to appear in both new databases and migrated ones.
_ALL_COLUMNS: dict[str, str] = {
    # Discovery
    "url": "TEXT PRIMARY KEY",
    "title": "TEXT",
    "salary": "TEXT",
    "description": "TEXT",
    "location": "TEXT",
    "site": "TEXT",
    "company": "TEXT",
    "strategy": "TEXT",
    "discovered_at": "TEXT",
    # Enrichment
    "full_description": "TEXT",
    "application_url": "TEXT",
    "detail_scraped_at": "TEXT",
    "detail_error": "TEXT",
    "sponsorship_status": "TEXT",
    # Scoring
    "fit_score": "INTEGER",
    "score_reasoning": "TEXT",
    "scored_at": "TEXT",
    "user_fit_score": "INTEGER",
    "user_score_rationale": "TEXT",
    "user_score_at": "TEXT",
    "portfolio_project_ids": "TEXT",
    # Tailoring
    "tailored_resume_path": "TEXT",
    "tailored_resume_docx_path": "TEXT",
    "tailored_at": "TEXT",
    "tailor_attempts": "INTEGER DEFAULT 0",
    # Cover letter
    "cover_letter_path": "TEXT",
    "cover_letter_docx_path": "TEXT",
    "cover_letter_at": "TEXT",
    "cover_attempts": "INTEGER DEFAULT 0",
    # Application
    "applied_at": "TEXT",
    "apply_status": "TEXT",
    "apply_error": "TEXT",
    "apply_attempts": "INTEGER DEFAULT 0",
    "agent_id": "TEXT",
    "last_attempted_at": "TEXT",
    "apply_duration_ms": "INTEGER",
    "apply_task_id": "TEXT",
    "verification_confidence": "TEXT",
    # Kanban board
    "funnel_stage": "TEXT DEFAULT 'backlog'",
    "outcome": "TEXT",
    "source": "TEXT DEFAULT 'discovered'",
    "applied_manually": "INTEGER DEFAULT 0",
    "notes": "TEXT",
    "follow_up_at": "TEXT",
    "first_response_at": "TEXT",
    "board_updated_by": "TEXT",
    "board_updated_at": "TEXT",
    # WhatsApp daily notify
    "whatsapp_notified_at": "TEXT",
}

# Canonical Kanban lanes (single shared axis).
FUNNEL_STAGES = (
    "backlog",
    "prepare",
    "applied",
    "in_progress",
    "offer",
    "closed",
)
AGENT_MAX_STAGE = "prepare"
HUMAN_HELD_STAGES = ("applied", "in_progress", "offer", "closed")
CLOSED_OUTCOMES = (
    "accepted",
    "rejected",
    "withdrawn",
    "ghosted",
    "cancelled",
)

# Skip agent pipeline work on human-held cards and post-handoff stages.
# Also excludes manual source from digest/auto-apply (added separately where needed).
ANTI_CLOBBER_SQL = (
    " AND (board_updated_by IS NULL OR board_updated_by != 'human')"
    " AND COALESCE(funnel_stage, 'backlog') NOT IN "
    "('applied', 'in_progress', 'offer', 'closed')"
)
MANUAL_SOURCE_EXCLUSION_SQL = " AND COALESCE(source, 'discovered') != 'manual'"


def backfill_funnel_stages(conn: sqlite3.Connection | None = None) -> int:
    """One-time backfill of funnel_stage + seed stage_history for existing rows.

    Idempotent: only updates rows where funnel_stage is NULL (pre-migration) or
    seeds history when a job has no stage_history rows yet after a stage was set
    by DEFAULT without history.

    Returns:
        Number of jobs whose funnel_stage was set by this backfill.
    """
    if conn is None:
        conn = get_connection()

    # Rows that still have NULL funnel_stage (column added without default applied)
    # or that need inferred stage from pipeline timestamps.
    updated = conn.execute("""
        UPDATE jobs SET funnel_stage = CASE
            WHEN applied_at IS NOT NULL THEN 'applied'
            WHEN tailored_resume_path IS NOT NULL THEN 'prepare'
            ELSE 'backlog'
        END
        WHERE funnel_stage IS NULL
           OR (
                funnel_stage = 'backlog'
                AND board_updated_at IS NULL
                AND (
                    applied_at IS NOT NULL
                    OR tailored_resume_path IS NOT NULL
                )
           )
    """).rowcount

    # Seed one history row per job that has none yet.
    conn.execute("""
        INSERT INTO stage_history (job_url, from_stage, to_stage, actor, at, note)
        SELECT
            j.url,
            NULL,
            COALESCE(j.funnel_stage, 'backlog'),
            'system',
            COALESCE(
                j.applied_at, j.tailored_at, j.scored_at, j.discovered_at,
                datetime('now')
            ),
            'backfill'
        FROM jobs j
        WHERE NOT EXISTS (
            SELECT 1 FROM stage_history h WHERE h.job_url = j.url
        )
    """)
    conn.commit()
    return max(updated, 0)


def advance_funnel(
    url: str,
    to_stage: str,
    actor: str,
    note: str | None = None,
    *,
    conn: sqlite3.Connection | None = None,
    applied_manually: bool | None = None,
    outcome: str | None = None,
) -> str | None:
    """Atomically move a job's funnel_stage and append stage_history.

    This is the only supported way to change funnel_stage. Agent callers must
    not advance past AGENT_MAX_STAGE ('prepare'). Human/system may move freely.

    Args:
        url: Job primary key.
        to_stage: Target lane in FUNNEL_STAGES.
        actor: 'agent', 'human', or 'system'.
        note: Optional freeform note for history.
        conn: Optional open connection (uses get_connection if None).
        applied_manually: If set, updates the applied_manually flag.
        outcome: If set (typically on closed), stores outcome enum.

    Returns:
        Previous funnel_stage, or None if the job was not found / no-op same stage.

    Raises:
        ValueError: Invalid stage or agent attempting to cross the handoff.
    """
    if to_stage not in FUNNEL_STAGES:
        raise ValueError(f"Invalid funnel_stage: {to_stage!r}")
    if actor == "agent" and to_stage not in ("backlog", "prepare"):
        raise ValueError(
            f"Agent cannot advance past '{AGENT_MAX_STAGE}' (tried {to_stage!r})"
        )
    if outcome is not None and outcome not in CLOSED_OUTCOMES:
        raise ValueError(f"Invalid outcome: {outcome!r}")

    owns_conn = conn is None
    if owns_conn:
        conn = get_connection()

    row = conn.execute(
        "SELECT funnel_stage FROM jobs WHERE url = ?", (url,)
    ).fetchone()
    if row is None:
        return None

    from_stage = row["funnel_stage"] if row["funnel_stage"] is not None else "backlog"
    if from_stage == to_stage and applied_manually is None and outcome is None:
        return from_stage

    now = datetime.now(timezone.utc).isoformat()
    sets = [
        "funnel_stage = ?",
        "board_updated_by = ?",
        "board_updated_at = ?",
    ]
    params: list = [to_stage, actor, now]
    if applied_manually is not None:
        sets.append("applied_manually = ?")
        params.append(1 if applied_manually else 0)
    if outcome is not None:
        sets.append("outcome = ?")
        params.append(outcome)
    elif to_stage != "closed":
        # Clear stale outcome when moving out of Closed.
        sets.append("outcome = NULL")

    params.append(url)
    conn.execute(
        f"UPDATE jobs SET {', '.join(sets)} WHERE url = ?",
        params,
    )
    if from_stage != to_stage:
        conn.execute(
            "INSERT INTO stage_history (job_url, from_stage, to_stage, actor, at, note) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (url, from_stage, to_stage, actor, now, note),
        )
    if owns_conn:
        conn.commit()
    return from_stage


def maybe_agent_advance_to_prepare(url: str, *, conn: sqlite3.Connection | None = None) -> bool:
    """Advance to prepare when materials are ready, if the agent still owns the card.

    Caps at prepare. Skips human-held cards and post-handoff stages.
    Returns True if a transition was made.
    """
    owns_conn = conn is None
    if owns_conn:
        conn = get_connection()

    row = conn.execute(
        "SELECT funnel_stage, board_updated_by, tailored_resume_path, cover_letter_path "
        "FROM jobs WHERE url = ?",
        (url,),
    ).fetchone()
    if row is None:
        return False

    stage = row["funnel_stage"] or "backlog"
    if row["board_updated_by"] == "human":
        return False
    if stage in HUMAN_HELD_STAGES:
        return False
    if stage == "prepare":
        return False
    if not row["tailored_resume_path"]:
        return False
    # Prefer cover letter ready, but allow prepare once tailored (cover may lag).
    advance_funnel(url, "prepare", "agent", note="materials ready", conn=conn)
    if owns_conn:
        conn.commit()
    return True


def insert_manual_job(
    url: str,
    *,
    title: str | None = None,
    company: str | None = None,
    location: str | None = None,
    description: str | None = None,
    application_url: str | None = None,
    funnel_stage: str = "backlog",
    notes: str | None = None,
    conn: sqlite3.Connection | None = None,
) -> dict:
    """Insert a human-added job with manual source sentinels.

    Isolated from digest and auto-apply via source='manual'.

    Raises:
        ValueError: Missing url, invalid stage, or duplicate url.
    """
    if not url:
        raise ValueError("url is required")
    if funnel_stage not in FUNNEL_STAGES:
        raise ValueError(f"Invalid funnel_stage: {funnel_stage!r}")

    owns_conn = conn is None
    if owns_conn:
        conn = get_connection()

    now = datetime.now(timezone.utc).isoformat()
    full_description = description
    from jobwright.enrichment.sponsorship import classify_sponsorship

    sponsorship_status = classify_sponsorship(full_description)
    try:
        conn.execute(
            """
            INSERT INTO jobs (
                url, title, company, location, description, application_url,
                site, strategy, source, discovered_at, funnel_stage,
                board_updated_by, board_updated_at, notes, full_description,
                sponsorship_status
            ) VALUES (?, ?, ?, ?, ?, ?, 'manual', 'manual', 'manual', ?, ?, 'human', ?, ?, ?, ?)
            """,
            (
                url,
                title,
                company,
                location,
                description,
                application_url or url,
                now,
                funnel_stage,
                now,
                notes,
                description,
                sponsorship_status,
            ),
        )
    except sqlite3.IntegrityError as exc:
        raise ValueError(f"Job already exists: {url}") from exc

    conn.execute(
        "INSERT INTO stage_history (job_url, from_stage, to_stage, actor, at, note) "
        "VALUES (?, NULL, ?, 'human', ?, ?)",
        (url, funnel_stage, now, "manual add"),
    )
    if owns_conn:
        conn.commit()

    row = conn.execute("SELECT * FROM jobs WHERE url = ?", (url,)).fetchone()
    return dict(row) if row else {"url": url}


def ensure_columns(conn: sqlite3.Connection | None = None) -> list[str]:
    """Add any missing columns to the jobs table (forward migration).

    Reads the current table schema via PRAGMA table_info and compares against
    the full column registry. Any missing columns are added with ALTER TABLE.

    This makes it safe to upgrade the database from any previous version --
    columns are only added, never removed or renamed.

    Args:
        conn: Database connection. Uses get_connection() if None.

    Returns:
        List of column names that were added (empty if schema was already current).
    """
    if conn is None:
        conn = get_connection()

    existing = {row[1] for row in conn.execute("PRAGMA table_info(jobs)").fetchall()}
    added = []

    for col, dtype in _ALL_COLUMNS.items():
        if col not in existing:
            # PRIMARY KEY columns can't be added via ALTER TABLE, but url
            # is always created with the table itself so this is safe
            if "PRIMARY KEY" in dtype:
                continue
            conn.execute(f"ALTER TABLE jobs ADD COLUMN {col} {dtype}")
            added.append(col)

    if added:
        conn.commit()

    return added


def backfill_sponsorship_status(conn: sqlite3.Connection | None = None) -> int:
    """Populate sponsorship_status for rows missing a stored value."""
    from jobwright.enrichment.sponsorship import backfill_sponsorship_status as _backfill

    if conn is None:
        conn = get_connection()
    return _backfill(conn)


def get_stats(conn: sqlite3.Connection | None = None) -> dict:
    """Return job counts by pipeline stage.

    Provides a snapshot of how many jobs are at each stage, useful for
    dashboard display and pipeline progress tracking.

    Args:
        conn: Database connection. Uses get_connection() if None.

    Returns:
        Dictionary with keys:
            total, by_site, pending_detail, with_description,
            scored, unscored, tailored, untailored_eligible,
            with_cover_letter, applied, score_distribution
    """
    if conn is None:
        conn = get_connection()

    stats: dict = {}

    # Total jobs
    stats["total"] = conn.execute("SELECT COUNT(*) FROM jobs").fetchone()[0]

    # By site breakdown
    rows = conn.execute(
        "SELECT site, COUNT(*) as cnt FROM jobs GROUP BY site ORDER BY cnt DESC"
    ).fetchall()
    stats["by_site"] = [(row[0], row[1]) for row in rows]

    # Enrichment stage
    stats["pending_detail"] = conn.execute(
        "SELECT COUNT(*) FROM jobs WHERE detail_scraped_at IS NULL"
    ).fetchone()[0]

    stats["with_description"] = conn.execute(
        "SELECT COUNT(*) FROM jobs WHERE full_description IS NOT NULL"
    ).fetchone()[0]

    stats["detail_errors"] = conn.execute(
        "SELECT COUNT(*) FROM jobs WHERE detail_error IS NOT NULL"
    ).fetchone()[0]

    # Scoring stage
    stats["scored"] = conn.execute(
        "SELECT COUNT(*) FROM jobs WHERE fit_score IS NOT NULL"
    ).fetchone()[0]

    stats["unscored"] = conn.execute(
        "SELECT COUNT(*) FROM jobs "
        "WHERE full_description IS NOT NULL AND fit_score IS NULL"
    ).fetchone()[0]

    # Score distribution
    dist_rows = conn.execute(
        "SELECT fit_score, COUNT(*) as cnt FROM jobs "
        "WHERE fit_score IS NOT NULL "
        "GROUP BY fit_score ORDER BY fit_score DESC"
    ).fetchall()
    stats["score_distribution"] = [(row[0], row[1]) for row in dist_rows]

    # Tailoring stage
    stats["tailored"] = conn.execute(
        "SELECT COUNT(*) FROM jobs WHERE tailored_resume_path IS NOT NULL"
    ).fetchone()[0]

    stats["untailored_eligible"] = conn.execute(
        "SELECT COUNT(*) FROM jobs "
        "WHERE fit_score >= 7 AND full_description IS NOT NULL "
        "AND tailored_resume_path IS NULL"
    ).fetchone()[0]

    stats["tailor_exhausted"] = conn.execute(
        "SELECT COUNT(*) FROM jobs "
        "WHERE COALESCE(tailor_attempts, 0) >= 5 "
        "AND tailored_resume_path IS NULL"
    ).fetchone()[0]

    # Cover letter stage
    stats["with_cover_letter"] = conn.execute(
        "SELECT COUNT(*) FROM jobs WHERE cover_letter_path IS NOT NULL"
    ).fetchone()[0]

    stats["cover_exhausted"] = conn.execute(
        "SELECT COUNT(*) FROM jobs "
        "WHERE COALESCE(cover_attempts, 0) >= 5 "
        "AND (cover_letter_path IS NULL OR cover_letter_path = '')"
    ).fetchone()[0]

    # Application stage
    stats["applied"] = conn.execute(
        "SELECT COUNT(*) FROM jobs WHERE applied_at IS NOT NULL"
    ).fetchone()[0]

    stats["apply_errors"] = conn.execute(
        "SELECT COUNT(*) FROM jobs WHERE apply_error IS NOT NULL"
    ).fetchone()[0]

    stats["ready_to_apply"] = conn.execute(
        "SELECT COUNT(*) FROM jobs "
        "WHERE tailored_resume_path IS NOT NULL "
        "AND applied_at IS NULL "
        "AND application_url IS NOT NULL"
    ).fetchone()[0]

    stats["with_portfolio"] = conn.execute(
        "SELECT COUNT(*) FROM jobs WHERE portfolio_project_ids IS NOT NULL"
    ).fetchone()[0]

    return stats


def store_jobs(conn: sqlite3.Connection, jobs: list[dict],
               site: str, strategy: str) -> tuple[int, int]:
    """Store discovered jobs, skipping duplicates by URL.

    Args:
        conn: Database connection.
        jobs: List of job dicts with keys: url, title, salary, description, location.
        site: Source site name (e.g. "RemoteOK", "Dice").
        strategy: Extraction strategy used (e.g. "json_ld", "api_response", "css_selectors").

    Returns:
        Tuple of (new_count, duplicate_count).
    """
    now = datetime.now(timezone.utc).isoformat()
    new = 0
    existing = 0

    for job in jobs:
        url = job.get("url")
        if not url:
            continue
        try:
            conn.execute(
                "INSERT INTO jobs (url, title, salary, description, location, site, strategy, "
                "discovered_at, source, funnel_stage) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'discovered', 'backlog')",
                (url, job.get("title"), job.get("salary"), job.get("description"),
                 job.get("location"), site, strategy, now),
            )
            new += 1
        except sqlite3.IntegrityError:
            existing += 1

    conn.commit()
    return new, existing


def get_jobs_by_stage(conn: sqlite3.Connection | None = None,
                      stage: str = "discovered",
                      min_score: int | None = None,
                      limit: int = 100) -> list[dict]:
    """Fetch jobs filtered by pipeline stage.

    Args:
        conn: Database connection. Uses get_connection() if None.
        stage: One of "discovered", "enriched", "scored", "tailored", "applied".
        min_score: Minimum fit_score filter (only relevant for scored+ stages).
        limit: Maximum number of rows to return.

    Returns:
        List of job dicts.
    """
    if conn is None:
        conn = get_connection()

    conditions = {
        "discovered": "1=1",
        "pending_detail": f"detail_scraped_at IS NULL{ANTI_CLOBBER_SQL}",
        "enriched": "full_description IS NOT NULL",
        "pending_score": (
            f"full_description IS NOT NULL AND fit_score IS NULL{ANTI_CLOBBER_SQL}"
        ),
        "scored": "fit_score IS NOT NULL",
        "pending_tailor": (
            "fit_score >= ? AND full_description IS NOT NULL "
            "AND tailored_resume_path IS NULL AND COALESCE(tailor_attempts, 0) < 5 "
            f"{ANTI_CLOBBER_SQL}"
        ),
        "tailored": "tailored_resume_path IS NOT NULL",
        "pending_apply": (
            "tailored_resume_path IS NOT NULL AND applied_at IS NULL "
            "AND application_url IS NOT NULL"
            f"{ANTI_CLOBBER_SQL}{MANUAL_SOURCE_EXCLUSION_SQL}"
        ),
        "applied": "applied_at IS NOT NULL",
    }

    where = conditions.get(stage, "1=1")
    params: list = []

    if "?" in where and min_score is not None:
        params.append(min_score)
    elif "?" in where:
        params.append(7)  # default min_score

    if min_score is not None and "fit_score" not in where and stage in ("scored", "tailored", "applied"):
        where += " AND fit_score >= ?"
        params.append(min_score)

    query = f"SELECT * FROM jobs WHERE {where} ORDER BY fit_score DESC NULLS LAST, discovered_at DESC"
    if limit > 0:
        query += " LIMIT ?"
        params.append(limit)

    rows = conn.execute(query, params).fetchall()

    # Convert sqlite3.Row objects to dicts
    if rows:
        columns = rows[0].keys()
        return [dict(zip(columns, row)) for row in rows]
    return []


def job_id_for_url(url: str) -> str:
    """Deterministic short id for a job URL (12 hex chars, no storage needed)."""
    return hashlib.blake2b(url.encode("utf-8"), digest_size=6).hexdigest()


def get_unnotified_prepare_jobs(conn: sqlite3.Connection | None = None) -> list[dict]:
    """Return prepare-stage jobs that have not been WhatsApp-notified yet.

    Ordered by effective fit score (user override preferred) descending.
    """
    if conn is None:
        conn = get_connection()

    rows = conn.execute(
        "SELECT * FROM jobs "
        "WHERE funnel_stage = 'prepare' AND whatsapp_notified_at IS NULL "
        "ORDER BY COALESCE(user_fit_score, fit_score) DESC NULLS LAST, discovered_at DESC"
    ).fetchall()

    out: list[dict] = []
    for row in rows:
        d = dict(row)
        effective = d.get("user_fit_score")
        if effective is None:
            effective = d.get("fit_score")
        out.append(
            {
                "url": d.get("url"),
                "title": d.get("title"),
                "company": d.get("company") or d.get("site"),
                "location": d.get("location"),
                "salary": d.get("salary"),
                "fit_score": int(effective) if effective is not None else None,
                "funnel_stage": d.get("funnel_stage") or "prepare",
            }
        )
    return out


def mark_whatsapp_notified(urls: list[str], conn: sqlite3.Connection | None = None) -> int:
    """Stamp whatsapp_notified_at for the given urls (only where currently NULL).

    Returns the number of rows updated (idempotent: re-marking returns 0).
    """
    if not urls:
        return 0

    owns_conn = conn is None
    if owns_conn:
        conn = get_connection()

    now = datetime.now(timezone.utc).isoformat()
    placeholders = ", ".join("?" for _ in urls)
    updated = conn.execute(
        f"UPDATE jobs SET whatsapp_notified_at = ? "
        f"WHERE url IN ({placeholders}) AND whatsapp_notified_at IS NULL",
        [now, *urls],
    ).rowcount
    if owns_conn:
        conn.commit()
    return max(updated, 0)


def get_job_by_id(job_id: str, conn: sqlite3.Connection | None = None) -> dict | None:
    """Return the full job row whose url hashes to job_id, or None."""
    if conn is None:
        conn = get_connection()

    for row in conn.execute("SELECT * FROM jobs").fetchall():
        url = row["url"]
        if url and job_id_for_url(url) == job_id:
            return dict(row)
    return None
