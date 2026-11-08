"""Numbered schema migrations (database.MIGRATIONS / run_migrations)."""

from __future__ import annotations

import sqlite3
import threading
from pathlib import Path

import pytest

from jobwright import database as db_mod
from jobwright.database import (
    LATEST_SCHEMA_VERSION,
    MIGRATIONS,
    _ALL_COLUMNS,
    close_connection,
    get_connection,
    get_schema_version,
    init_db,
    run_migrations,
)

# jobs columns as of migration 1 (2026-11). Frozen on purpose: a column added to
# _ALL_COLUMNS later must come with its own numbered migration, or
# test_db_at_v1_gets_every_later_column fails.
V1_JOBS_COLUMNS = (
    "url", "title", "salary", "description", "location", "site", "company", "strategy", "discovered_at",
    "full_description", "application_url", "detail_scraped_at", "detail_error", "sponsorship_status",
    "fit_score", "score_reasoning", "scored_at", "user_fit_score", "user_score_rationale", "user_score_at",
    "portfolio_project_ids", "jev_score", "jev_confidence", "jev_routed",
    "tailored_resume_path", "tailored_resume_docx_path", "tailored_at", "tailor_attempts",
    "cover_letter_path", "cover_letter_docx_path", "cover_letter_at", "cover_attempts",
    "applied_at", "apply_status", "apply_error", "apply_attempts", "agent_id", "last_attempted_at",
    "apply_duration_ms", "apply_task_id", "verification_confidence",
    "funnel_stage", "outcome", "source", "applied_manually", "undone_applied_at", "undone_applied_manually",
    "notes", "follow_up_at", "followed_up_at", "first_response_at", "board_updated_by", "board_updated_at",
    "board_position", "whatsapp_notified_at", "job_id", "dedupe_key",
    "score_confidence", "score_gates", "score_tier", "score_model", "close_reason", "duplicate_of", "date_posted",
)

# An older production shape: the first columns only, stage_history, no side tables.
OLD_JOBS_COLUMNS = (
    "url", "title", "salary", "description", "location", "site", "strategy", "discovered_at",
    "full_description", "application_url", "detail_scraped_at", "detail_error",
    "fit_score", "score_reasoning", "scored_at", "user_fit_score", "user_score_rationale", "user_score_at",
    "tailored_resume_path", "tailored_at", "applied_at", "apply_status",
)

EXPECTED_TABLES = {
    "jobs", "stage_history", "job_tombstones", "score_labels", "score_history", "llm_usage",
    "schema_meta", "brief_items",
}


@pytest.fixture
def db_path(tmp_path: Path):
    path = tmp_path / "jobwright.db"
    yield path
    close_connection(path)


def _tables(conn: sqlite3.Connection) -> set[str]:
    return {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}


def _columns(conn: sqlite3.Connection, table: str = "jobs") -> set[str]:
    return {r[1] for r in conn.execute(f"PRAGMA table_info({table})")}


def _schema(conn: sqlite3.Connection) -> list[tuple]:
    return sorted(
        (r[0], r[1], " ".join((r[2] or "").split()))
        for r in conn.execute("SELECT type, name, sql FROM sqlite_master WHERE name NOT LIKE 'sqlite_%'")
    )


def _meta(conn: sqlite3.Connection) -> dict[str, str]:
    return {r[0]: r[1] for r in conn.execute("SELECT key, value FROM schema_meta")}


def _build_old_db(path: Path, *, legacy_markers: bool) -> None:
    """A DB as an older jobwright left it: fewer jobs columns, no migrations table."""
    raw = sqlite3.connect(path)
    cols = ", ".join(f"{c} {'TEXT PRIMARY KEY' if c == 'url' else 'TEXT'}" for c in OLD_JOBS_COLUMNS)
    raw.execute(f"CREATE TABLE jobs ({cols})")
    raw.execute(
        "CREATE TABLE stage_history (id INTEGER PRIMARY KEY AUTOINCREMENT, job_url TEXT NOT NULL, "
        "from_stage TEXT, to_stage TEXT NOT NULL, actor TEXT NOT NULL, at TEXT NOT NULL, note TEXT)"
    )
    raw.execute(
        "INSERT INTO jobs (url, title, location, site, discovered_at, fit_score, user_fit_score) "
        "VALUES ('https://example.com/jobs/1', 'Analyst', 'Remote', 'greenhouse', '2026-01-02', '8', '9')"
    )
    # A URL pruned before tombstones existed: only stage_history remembers it.
    raw.execute(
        "INSERT INTO stage_history (job_url, from_stage, to_stage, actor, at) "
        "VALUES ('https://example.com/jobs/pruned', NULL, 'backlog', 'system', '2026-01-01')"
    )
    if legacy_markers:
        raw.execute("CREATE TABLE schema_meta (key TEXT PRIMARY KEY, value TEXT)")
        raw.execute("INSERT INTO schema_meta VALUES ('seed_tombstones_from_history_v1', '2026-01-01')")
        raw.execute("INSERT INTO schema_meta VALUES ('import_user_scores_v1', '2026-01-01')")
    raw.commit()
    raw.close()


def test_migration_list_is_numbered_and_append_only():
    versions = [v for v, _, _ in MIGRATIONS]
    assert versions == list(range(1, len(MIGRATIONS) + 1))
    assert LATEST_SCHEMA_VERSION == versions[-1]
    assert [name for _, name, _ in MIGRATIONS][:2] == ["baseline", "brief_items"]


def test_v1_snapshot_is_subset_of_registry():
    """Columns are never removed from _ALL_COLUMNS (migrations only add)."""
    assert set(V1_JOBS_COLUMNS) <= set(_ALL_COLUMNS)


def test_fresh_db_reaches_latest_version(db_path):
    conn = init_db(db_path)
    assert get_schema_version(conn) == LATEST_SCHEMA_VERSION
    assert EXPECTED_TABLES <= _tables(conn)
    assert set(_ALL_COLUMNS) <= _columns(conn)
    assert _meta(conn)["schema_version"] == str(LATEST_SCHEMA_VERSION)
    # Legacy one-off markers are still written, so older code never re-runs them.
    assert {"seed_tombstones_from_history_v1", "import_user_scores_v1"} <= set(_meta(conn))


def test_pre_migration_db_migrates_and_keeps_data(db_path):
    _build_old_db(db_path, legacy_markers=False)
    conn = init_db(db_path)
    assert get_schema_version(conn) == LATEST_SCHEMA_VERSION
    assert EXPECTED_TABLES <= _tables(conn)
    assert set(_ALL_COLUMNS) <= _columns(conn)
    row = conn.execute("SELECT title, funnel_stage, job_id FROM jobs").fetchone()
    assert row["title"] == "Analyst"
    assert row["funnel_stage"] == "backlog"  # new column default
    assert row["job_id"] == db_mod.job_id_for_url("https://example.com/jobs/1")  # per-start backfill
    # One-off data steps ran exactly once, inside migration 1.
    tomb = conn.execute("SELECT reason FROM job_tombstones WHERE url = 'https://example.com/jobs/pruned'").fetchone()
    assert tomb["reason"] == "historical_prune"
    labels = conn.execute("SELECT label_score FROM score_labels WHERE job_url = 'https://example.com/jobs/1'").fetchall()
    assert [r[0] for r in labels] == [9]


def test_pre_migration_db_with_markers_does_not_rerun_one_offs(db_path):
    _build_old_db(db_path, legacy_markers=True)
    conn = init_db(db_path)
    assert get_schema_version(conn) == LATEST_SCHEMA_VERSION
    assert conn.execute("SELECT COUNT(*) FROM job_tombstones").fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM score_labels").fetchone()[0] == 0
    assert _meta(conn)["seed_tombstones_from_history_v1"] == "2026-01-01"


def test_current_db_without_version_migrates_as_noop(db_path):
    """A production DB already at today's schema (written before numbered
    migrations existed) only gains the version row and brief_items."""
    conn = init_db(db_path)
    conn.execute("DROP TABLE brief_items")
    conn.execute("DELETE FROM schema_meta WHERE key = 'schema_version'")
    conn.commit()
    before = [r for r in _schema(conn) if r[1] != "brief_items"]
    before_meta = _meta(conn)
    assert run_migrations(conn) == list(range(1, LATEST_SCHEMA_VERSION + 1))
    assert [r for r in _schema(conn) if r[1] != "brief_items"] == before
    assert "brief_items" in _tables(conn)
    after_meta = _meta(conn)
    assert after_meta.pop("schema_version") == str(LATEST_SCHEMA_VERSION)
    assert after_meta == before_meta


def test_running_twice_is_a_noop(db_path):
    conn = init_db(db_path)
    schema, meta = _schema(conn), _meta(conn)
    assert run_migrations(conn) == []
    init_db(db_path)
    assert _schema(conn) == schema
    assert _meta(conn) == meta


def test_db_at_v1_gets_every_later_column(db_path):
    """A DB stopped at version 1 (v1 column snapshot) reaches the full schema."""
    raw = sqlite3.connect(db_path)
    cols = ", ".join(f"{c} {_ALL_COLUMNS[c]}" for c in V1_JOBS_COLUMNS)
    raw.execute(f"CREATE TABLE jobs ({cols})")
    raw.commit()
    raw.close()
    conn = get_connection(db_path)
    # The rest of what v1 created, without _add_missing_columns (which would
    # mask a column added to _ALL_COLUMNS without its own migration).
    conn.execute(db_mod._JOBS_BASE_DDL)
    for ddl in db_mod._AUX_DDL:
        conn.execute(ddl)
    conn.execute("INSERT OR REPLACE INTO schema_meta (key, value) VALUES ('schema_version', '1')")
    conn.commit()
    assert run_migrations(conn) == list(range(2, LATEST_SCHEMA_VERSION + 1))
    assert set(_ALL_COLUMNS) <= _columns(conn)
    assert EXPECTED_TABLES <= _tables(conn)


def test_failing_migration_rolls_back_and_keeps_version(db_path, monkeypatch):
    conn = init_db(db_path)

    def broken(c):
        c.execute("ALTER TABLE jobs ADD COLUMN half_done TEXT")
        raise RuntimeError("boom")

    monkeypatch.setattr(db_mod, "MIGRATIONS", [*MIGRATIONS, (LATEST_SCHEMA_VERSION + 1, "broken", broken)])
    monkeypatch.setattr(db_mod, "LATEST_SCHEMA_VERSION", LATEST_SCHEMA_VERSION + 1)
    with pytest.raises(RuntimeError):
        run_migrations(conn)
    assert get_schema_version(conn) == LATEST_SCHEMA_VERSION
    assert "half_done" not in _columns(conn)
    assert not conn.in_transaction


def test_new_step_is_applied_once_and_recorded(db_path, monkeypatch):
    conn = init_db(db_path)
    nxt = LATEST_SCHEMA_VERSION + 1
    step = [(nxt, "example_col", lambda c: db_mod._add_column(c, "jobs", "example_col", "TEXT"))]
    monkeypatch.setattr(db_mod, "MIGRATIONS", [*MIGRATIONS, *step])
    monkeypatch.setattr(db_mod, "LATEST_SCHEMA_VERSION", nxt)
    assert run_migrations(conn) == [nxt]
    assert run_migrations(conn) == []
    assert "example_col" in _columns(conn)
    assert _meta(conn)["schema_version"] == str(nxt)


def test_newer_db_version_is_left_alone(db_path):
    conn = init_db(db_path)
    conn.execute("UPDATE schema_meta SET value = ? WHERE key = 'schema_version'", (str(LATEST_SCHEMA_VERSION + 5),))
    conn.commit()
    assert run_migrations(conn) == []
    assert get_schema_version(conn) == LATEST_SCHEMA_VERSION + 5


def test_concurrent_migrations_apply_each_step_once(db_path, monkeypatch):
    """API and pipeline opening the same fresh DB at once: every step runs once."""
    calls: list[int] = []
    lock = threading.Lock()

    def counted(version, fn):
        def run(c):
            with lock:
                calls.append(version)
            fn(c)
        return run

    monkeypatch.setattr(db_mod, "MIGRATIONS", [(v, n, counted(v, f)) for v, n, f in MIGRATIONS])
    # Real DB files already exist in WAL mode; switching a brand-new file to WAL
    # from several connections at once can fail in get_connection itself.
    raw = sqlite3.connect(db_path)
    raw.execute("PRAGMA journal_mode=WAL")
    raw.close()
    workers = 4
    barrier = threading.Barrier(workers)
    applied: list[list[int]] = []
    errors: list[BaseException] = []

    def worker():
        try:
            conn = get_connection(db_path)
            barrier.wait(timeout=30)
            applied.append(run_migrations(conn))
        except BaseException as exc:  # noqa: BLE001 - surfaced by the assert below
            errors.append(exc)
        finally:
            close_connection(db_path)

    threads = [threading.Thread(target=worker) for _ in range(workers)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(60)
    assert not errors, errors
    assert sorted(v for got in applied for v in got) == list(range(1, LATEST_SCHEMA_VERSION + 1))
    assert sorted(calls) == list(range(1, LATEST_SCHEMA_VERSION + 1))
    conn = get_connection(db_path)
    assert get_schema_version(conn) == LATEST_SCHEMA_VERSION


def test_init_db_commits_pending_caller_writes(db_path):
    """init_db used to commit unconditionally; a pending write is not lost or blocking."""
    conn = init_db(db_path)
    conn.execute("INSERT INTO jobs (url, title) VALUES ('https://example.com/jobs/2', 'Pending')")
    assert conn.in_transaction
    init_db(db_path)
    other = sqlite3.connect(db_path)
    try:
        assert other.execute("SELECT title FROM jobs WHERE url = 'https://example.com/jobs/2'").fetchone() == ("Pending",)
    finally:
        other.close()


def test_ensure_brief_items_still_works_on_a_bare_db(tmp_path):
    from jobwright import briefstats

    path = tmp_path / "bare.db"
    conn = sqlite3.connect(path)
    briefstats.ensure_brief_items(conn)
    briefstats.ensure_brief_items(conn)
    assert "brief_items" in _tables(conn)
    conn.close()


def test_v3_apply_evidence_tables(db_path):
    """Migration 3 adds pending_inputs, submissions and apply_picks; rerun is a no-op."""
    conn = init_db(db_path)
    assert {"pending_inputs", "submissions", "apply_picks"} <= _tables(conn)
    conn.execute("DROP TABLE apply_picks")
    conn.execute("UPDATE schema_meta SET value = '2' WHERE key = 'schema_version'")
    conn.commit()
    assert run_migrations(conn) == [3]
    assert "apply_picks" in _tables(conn)
    assert run_migrations(conn) == []
