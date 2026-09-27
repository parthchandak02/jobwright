"""Duplicate open jobs already in the backlog: grouping, keeper choice, closing."""

from __future__ import annotations

import pytest
from typer.testing import CliRunner

import jobwright.config as cfg
from jobwright.database import close_connection, get_connection, init_db
from jobwright.discovery.dedupe import (
    collapse_duplicates,
    description_similarity,
    find_duplicate_groups,
)

JD = (
    "Google.org is looking for a Global Cybersecurity Manager to lead grant programs that help "
    "nonprofits and civil society organizations defend against cyber threats. You will manage "
    "partner portfolios, design funding strategies, measure impact, work with engineering "
    "volunteers, coordinate with policy teams, and report outcomes to leadership across regions. "
    "Minimum qualifications include experience in program management, cybersecurity, philanthropy."
)
OTHER_JD = (
    "Build data pipelines for ads ranking. Write Spark and SQL jobs, own dashboards, partner with "
    "product analysts, tune models, design experiments, maintain infrastructure, review code, "
    "mentor junior engineers, and drive quarterly roadmap planning for the measurement platform team "
    "while keeping reliability and latency targets for every downstream consumer of the data."
)


@pytest.fixture()
def db(tmp_path):
    cfg.set_app_dir(tmp_path)
    path = tmp_path / "jobwright.db"
    close_connection(path)
    init_db(path)
    yield get_connection()
    close_connection(path)


def _add(conn, url, *, title="Global Cybersecurity Manager, Google.org", company="Google",
         location="New York, NY", desc=JD, stage="backlog", fit=7, user_fit=None,
         resume=None, source="discovered", discovered="2026-09-20T00:00:00", key=True):
    from jobwright.discovery.dedupe import dedupe_key

    conn.execute(
        "INSERT INTO jobs (url, job_id, title, company, location, full_description, funnel_stage, "
        "fit_score, user_fit_score, tailored_resume_path, source, discovered_at, dedupe_key) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (url, url.rsplit("/", 1)[-1], title, company, location, desc, stage, fit, user_fit, resume,
         source, discovered, dedupe_key(title, company, location) if key else None),
    )
    conn.commit()


def _row(conn, url):
    return dict(conn.execute("SELECT * FROM jobs WHERE url = ?", (url,)).fetchone())


def test_description_similarity_needs_real_text():
    assert description_similarity(JD, JD + " Apply now.") >= 0.9
    assert description_similarity(JD, OTHER_JD) < 0.3
    assert description_similarity("short", "short") == 0.0


def test_primary_key_group_and_backfill(db):
    _add(db, "https://x/a", key=False)
    _add(db, "https://x/b", location="New York, New York", fit=8)
    _add(db, "https://x/c", title="Data Engineer", desc=OTHER_JD)
    groups = find_duplicate_groups(db)
    assert len(groups) == 1
    assert groups[0]["match"] == "key"
    assert groups[0]["keeper"]["url"] == "https://x/b"
    assert [j["url"] for j in groups[0]["losers"]] == ["https://x/a"]
    assert _row(db, "https://x/a")["dedupe_key"] == "google|global cybersecurity manager google org|new york"


def test_multi_location_posting_groups_by_description(db):
    _add(db, "https://x/ny")
    _add(db, "https://x/sf", location="San Francisco, CA", desc=JD + " Location: San Francisco.")
    _add(db, "https://x/dc", location="Washington, DC", desc=OTHER_JD)
    groups = find_duplicate_groups(db)
    assert len(groups) == 1
    assert groups[0]["match"] == "description"
    assert {groups[0]["keeper"]["url"], *(j["url"] for j in groups[0]["losers"])} == {
        "https://x/ny", "https://x/sf",
    }


def test_keeper_order_stage_label_materials_fit_recency(db):
    _add(db, "https://x/1", fit=9, discovered="2026-09-25")
    _add(db, "https://x/2", location="New York", resume="/tmp/r.pdf", fit=5)
    _add(db, "https://x/3", location="New York City", user_fit=3, fit=2)
    assert find_duplicate_groups(db)[0]["keeper"]["url"] == "https://x/3"
    _add(db, "https://x/4", location="NYC, New York", stage="prepare", fit=1)
    assert find_duplicate_groups(db)[0]["keeper"]["url"] == "https://x/4"

    db.execute("DELETE FROM jobs WHERE url IN ('https://x/3', 'https://x/4')")
    db.commit()
    assert find_duplicate_groups(db)[0]["keeper"]["url"] == "https://x/2"


def test_label_row_counts_for_keeper(db):
    _add(db, "https://x/1", fit=9)
    _add(db, "https://x/2", location="New York", fit=4)
    db.execute(
        "INSERT INTO score_labels (job_url, label_score, source, created_at) "
        "VALUES ('https://x/2', 8, 'dashboard', '2026-09-21')"
    )
    db.commit()
    assert find_duplicate_groups(db)[0]["keeper"]["url"] == "https://x/2"


def test_dry_run_changes_nothing(db):
    _add(db, "https://x/1", fit=9)
    _add(db, "https://x/2", location="New York", fit=4)
    out = collapse_duplicates(db, apply=False)
    assert out["group_count"] == 1 and out["closed"] == 0
    assert _row(db, "https://x/2")["funnel_stage"] == "backlog"
    assert db.execute("SELECT COUNT(*) FROM job_tombstones").fetchone()[0] == 0


def test_apply_closes_loser_keeps_row_and_labels(db):
    _add(db, "https://x/keep", fit=9, stage="prepare")
    _add(db, "https://x/lose", location="New York", fit=4)
    db.execute("UPDATE jobs SET notes = 'my note' WHERE url = 'https://x/lose'")
    db.execute(
        "INSERT INTO score_labels (job_url, label_score, source, created_at) "
        "VALUES ('https://x/lose', 3, 'dashboard', '2026-09-21')"
    )
    db.commit()
    out = collapse_duplicates(db, apply=True)
    assert out["closed"] == 1
    loser = _row(db, "https://x/lose")
    assert loser["funnel_stage"] == "closed"
    assert loser["outcome"] == "duplicate"
    assert loser["close_reason"] == "duplicate"
    assert loser["duplicate_of"] == "keep"
    assert loser["notes"] == "my note\nDuplicate of job keep"
    assert _row(db, "https://x/keep")["funnel_stage"] == "prepare"
    reason = db.execute("SELECT reason FROM job_tombstones WHERE url = 'https://x/lose'").fetchone()[0]
    assert reason == "duplicate:https://x/keep"
    assert db.execute("SELECT COUNT(*) FROM score_labels WHERE job_url = 'https://x/lose'").fetchone()[0] == 1
    note = db.execute(
        "SELECT note, actor FROM stage_history WHERE job_url = 'https://x/lose' AND to_stage = 'closed'"
    ).fetchone()
    assert tuple(note) == ("duplicate_of:keep", "system")
    assert collapse_duplicates(db, apply=True)["group_count"] == 0


def test_applied_or_manual_losers_are_reported_not_closed(db):
    _add(db, "https://x/offer", stage="offer", fit=5)
    _add(db, "https://x/applied", location="New York", stage="applied", fit=9)
    _add(db, "https://x/manual", location="NYC, NY", source="manual", fit=9)
    _add(db, "https://x/plain", location="New York, New York", fit=9)
    out = collapse_duplicates(db, apply=True)
    assert out["closed"] == 1
    assert {b["url"] for b in out["blocked"]} == {"https://x/offer", "https://x/manual"}
    assert _row(db, "https://x/offer")["funnel_stage"] == "offer"
    assert _row(db, "https://x/applied")["funnel_stage"] == "applied"
    assert _row(db, "https://x/manual")["funnel_stage"] == "backlog"
    assert _row(db, "https://x/plain")["funnel_stage"] == "closed"


def test_closed_jobs_are_ignored(db):
    _add(db, "https://x/1", stage="closed")
    _add(db, "https://x/2", location="New York")
    assert find_duplicate_groups(db) == []


def test_repost_of_closed_duplicate_is_tombstoned_at_discovery(db):
    from jobwright.discovery.dedupe import dedupe_new_jobs

    _add(db, "https://x/keep", fit=9)
    _add(db, "https://x/lose", location="New York", fit=4)
    collapse_duplicates(db, apply=True)
    _add(db, "https://x/repost", location="New York", key=False)
    assert dedupe_new_jobs(db)["duplicates"] == 1
    assert db.execute("SELECT 1 FROM jobs WHERE url = 'https://x/repost'").fetchone() is None


def test_cli_dedupe_preview_and_apply(db, monkeypatch):
    from jobwright import cli

    monkeypatch.setattr(cli, "_bootstrap", lambda: None)
    _add(db, "https://x/keep", fit=9)
    _add(db, "https://x/lose", location="New York", fit=4)
    runner = CliRunner()
    preview = runner.invoke(cli.app, ["dedupe"])
    assert preview.exit_code == 0, preview.output
    assert "Would close 1" in preview.output
    assert _row(db, "https://x/lose")["funnel_stage"] == "backlog"
    applied = runner.invoke(cli.app, ["dedupe", "--apply"])
    assert applied.exit_code == 0, applied.output
    assert "Closed 1" in applied.output
    assert _row(db, "https://x/lose")["funnel_stage"] == "closed"


def test_score_stage_collapses_duplicates(db, monkeypatch):
    import jobwright.pipeline as pipeline
    import jobwright.scoring.scorer as scorer

    monkeypatch.setattr(scorer, "run_scoring", lambda: {"scored": 0, "errors": 0})
    monkeypatch.setattr("jobwright.discovery.cleanup.prune_after_score", lambda conn, dry_run: {})
    _add(db, "https://x/keep", fit=9)
    _add(db, "https://x/lose", location="New York", fit=4)
    out = pipeline._run_score()
    assert out["collapse"] == {"group_count": 1, "closed": 1, "blocked": 0}
    assert _row(db, "https://x/lose")["outcome"] == "duplicate"


def test_board_card_links_duplicate(db):
    from jobwright.web.routers.board import get_job_by_short_id

    _add(db, "https://x/keep", fit=9)
    _add(db, "https://x/lose", location="New York", fit=4)
    collapse_duplicates(db, apply=True)
    card = get_job_by_short_id("lose")
    assert card["duplicate_of"] == {
        "job_id": "keep", "title": "Global Cybersecurity Manager, Google.org", "company": "Google",
    }
    assert get_job_by_short_id("keep")["duplicate_of"] is None


def test_notify_collapses_multi_location_posting(db):
    from jobwright.notify import _dedupe_for_notify

    jobs = [
        {"url": "https://x/ny", "title": "Global Cybersecurity Manager, Google.org", "company": "Google",
         "location": "New York, NY", "full_description": JD},
        {"url": "https://x/sf", "title": "Global Cybersecurity Manager, Google.org", "company": "Google LLC",
         "location": "San Francisco, CA", "full_description": JD},
    ]
    assert [j["url"] for j in _dedupe_for_notify(db, jobs)] == ["https://x/ny"]
