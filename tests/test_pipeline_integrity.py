"""Pipeline integrity: run lock, run summary, tombstones, cross-board dedupe."""

from __future__ import annotations

import json
import sqlite3

import pytest

import jobwright.config as cfg
from jobwright.database import close_connection, get_connection, init_db, insert_manual_job, tombstone_jobs


@pytest.fixture()
def db(tmp_path):
    cfg.set_app_dir(tmp_path)
    path = tmp_path / "jobwright.db"
    close_connection(path)
    init_db(path)
    yield get_connection()
    close_connection(path)


def _insert(conn, url, title="Program Manager", company="Acme Foundation", location="Oakland, CA", site="indeed"):
    conn.execute(
        "INSERT INTO jobs (url, title, company, location, site, discovered_at) VALUES (?, ?, ?, ?, ?, datetime('now'))",
        (url, title, company, location, site),
    )
    conn.commit()


def test_tombstoned_url_cannot_be_reinserted(db):
    _insert(db, "https://x/1")
    assert tombstone_jobs(db, [("https://x/1", "prune:low score:2")]) == 1
    with pytest.raises(sqlite3.IntegrityError):
        _insert(db, "https://x/1")
    reason = db.execute("SELECT reason FROM job_tombstones WHERE url='https://x/1'").fetchone()[0]
    assert reason == "prune:low score:2"


def test_plain_delete_is_tombstoned_by_trigger(db):
    _insert(db, "https://x/2")
    db.execute("DELETE FROM jobs WHERE url='https://x/2'")
    db.commit()
    assert db.execute("SELECT reason FROM job_tombstones WHERE url='https://x/2'").fetchone()[0] == "deleted"


def test_manual_add_revives_tombstoned_url(db):
    _insert(db, "https://x/3")
    tombstone_jobs(db, [("https://x/3", "prune")])
    insert_manual_job("https://x/3", title="Back", company="C")
    assert db.execute("SELECT title, job_id FROM jobs WHERE url='https://x/3'").fetchone()[0] == "Back"


def test_known_urls_include_tombstones(db):
    from jobwright.discovery.known_urls import load_known_urls

    _insert(db, "https://x/4")
    tombstone_jobs(db, [("https://x/4", "prune")])
    assert "https://x/4" in load_known_urls(db)


def test_dedupe_removes_cross_board_repost(db):
    from jobwright.discovery.dedupe import dedupe_new_jobs

    _insert(db, "https://linkedin/1", title="Program Officer (Remote)", company="Acme Foundation, Inc.", site="linkedin")
    _insert(db, "https://indeed/9", title="Program Officer", company="acme foundation", site="indeed")
    _insert(db, "https://indeed/10", title="Program Officer - Education", company="Acme Foundation", site="indeed")
    stats = dedupe_new_jobs(db)
    urls = {r[0] for r in db.execute("SELECT url FROM jobs")}
    assert urls == {"https://linkedin/1", "https://indeed/10"}
    assert stats["duplicates"] == 1
    reason = db.execute("SELECT reason FROM job_tombstones WHERE url='https://indeed/9'").fetchone()[0]
    assert reason == "duplicate:https://linkedin/1"


def test_dedupe_blocks_repost_of_removed_job(db):
    from jobwright.discovery.dedupe import dedupe_new_jobs

    _insert(db, "https://a/1")
    dedupe_new_jobs(db)
    tombstone_jobs(db, [("https://a/1", "prune:off-track")])
    _insert(db, "https://a/2")
    dedupe_new_jobs(db)
    assert db.execute("SELECT COUNT(*) FROM jobs").fetchone()[0] == 0


def test_dedupe_never_removes_human_or_manual_jobs(db):
    from jobwright.discovery.dedupe import dedupe_new_jobs

    _insert(db, "https://a/1")
    dedupe_new_jobs(db)
    insert_manual_job("https://manual/1", title="Program Manager", company="Acme Foundation", location="Oakland, CA")
    dedupe_new_jobs(db)
    assert db.execute("SELECT COUNT(*) FROM jobs").fetchone()[0] == 2


def test_pipeline_lock_is_exclusive(tmp_path):
    from jobwright.pipeline import PipelineLocked, pipeline_lock

    cfg.set_app_dir(tmp_path)
    with pipeline_lock():
        with pytest.raises(PipelineLocked):
            with pipeline_lock():
                pass
    with pipeline_lock():
        pass


def test_locked_run_returns_error_without_running(tmp_path, monkeypatch):
    from jobwright import pipeline

    cfg.set_app_dir(tmp_path)
    close_connection(tmp_path / "jobwright.db")
    called = []
    monkeypatch.setitem(pipeline._STAGE_RUNNERS, "enrich", lambda **kw: called.append(1) or {"status": "ok"})
    with pipeline.pipeline_lock():
        result = pipeline.run_pipeline(stages=["enrich"])
    assert result.get("locked") and not called
    close_connection(tmp_path / "jobwright.db")


def test_run_summary_records_stage_failures(tmp_path, monkeypatch):
    from jobwright import pipeline

    cfg.set_app_dir(tmp_path)
    close_connection(tmp_path / "jobwright.db")
    monkeypatch.setitem(pipeline._STAGE_RUNNERS, "enrich", lambda **kw: {"status": "error: all 3 enrichments failed"})
    monkeypatch.setitem(pipeline._STAGE_RUNNERS, "score", lambda **kw: {"status": "ok", "scored": 4})
    result = pipeline.run_pipeline(stages=["enrich", "score"])
    assert result["errors"] == {"enrich": "error: all 3 enrichments failed"}
    summary = json.loads((tmp_path / "logs" / "last_run.json").read_text())
    assert summary["ok"] is False and summary["stages"][1]["detail"]["scored"] == 4
    close_connection(tmp_path / "jobwright.db")


def test_tailor_stage_reports_total_failure(monkeypatch):
    from jobwright import pipeline

    monkeypatch.setattr(
        "jobwright.scoring.tailor.run_tailoring",
        lambda **kw: {"approved": 0, "failed": 2, "errors": 1, "elapsed": 1.0},
    )
    assert pipeline._run_tailor()["status"].startswith("error")


def test_history_seed_tombstones_pruned_urls(tmp_path):
    path = tmp_path / "old.db"
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE jobs (url TEXT PRIMARY KEY, title TEXT)")
    conn.execute(
        "CREATE TABLE stage_history (id INTEGER PRIMARY KEY, job_url TEXT, from_stage TEXT, to_stage TEXT, actor TEXT, at TEXT, note TEXT)"
    )
    conn.execute("INSERT INTO jobs VALUES ('https://kept', 'k')")
    conn.executemany(
        "INSERT INTO stage_history (job_url, to_stage, actor, at) VALUES (?, 'backlog', 'agent', 'x')",
        [("https://kept",), ("https://gone",)],
    )
    conn.commit()
    conn.close()
    close_connection(path)
    c = init_db(path)
    assert {r[0] for r in c.execute("SELECT url FROM job_tombstones")} == {"https://gone"}
    close_connection(path)
