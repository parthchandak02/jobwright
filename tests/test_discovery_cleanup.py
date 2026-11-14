"""Tests for discovery/cleanup.py: noise pruning, post-score pruning, score guards, and card protection."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
import yaml

import jobwright.config as cfg
from jobwright.database import close_connection, get_connection, init_db
from jobwright.discovery.cleanup import (
    _row_is_protected,
    job_is_noise,
    prune_after_score,
    prune_noise_jobs,
    reapply_fit_score_guards,
)
from jobwright.discovery.known_urls import load_known_urls

BASE_CFG = {
    "exclude_titles": ["account executive", "gtm"],
    "exclude_companies": ["Spam Staffing"],
    "block_sites": ["CustomBadBoard"],
    "min_salary": 115000,
    "defaults": {},
    "location": {
        "accept_patterns": ["San Francisco", "CA", "Remote"],
        "reject_patterns": ["Texas", "Austin"],
    },
}


@pytest.fixture()
def db(tmp_path: Path):
    cfg.set_app_dir(tmp_path)
    path = tmp_path / "jobwright.db"
    close_connection(path)
    init_db(path)
    yield get_connection()
    close_connection(path)


def _insert_job(
    conn: sqlite3.Connection,
    url: str,
    *,
    title: str = "Program Manager",
    company: str = "Acme Foundation",
    site: str = "indeed",
    location: str = "San Francisco, CA",
    salary: str | None = "$150,000",
    description: str | None = "Lead community impact programs.",
    full_description: str | None = None,
    fit_score: int | None = None,
    funnel_stage: str = "backlog",
    board_updated_by: str | None = None,
    user_fit_score: int | None = None,
    source: str | None = None,
) -> None:
    conn.execute(
        "INSERT INTO jobs ("
        "url, title, company, site, location, salary, description, full_description, "
        "fit_score, funnel_stage, board_updated_by, user_fit_score, source, discovered_at"
        ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))",
        (
            url,
            title,
            company,
            site,
            location,
            salary,
            description,
            full_description,
            fit_score,
            funnel_stage,
            board_updated_by,
            user_fit_score,
            source,
        ),
    )
    conn.commit()


# ---------------------------------------------------------------------------
# _row_is_protected
# ---------------------------------------------------------------------------


def test_row_is_protected_guards_human_rated_manual_and_later_stages(db):
    _insert_job(db, "https://example.com/plain")
    _insert_job(db, "https://example.com/human", board_updated_by="human")
    _insert_job(db, "https://example.com/rated", user_fit_score=3)
    _insert_job(db, "https://example.com/manual", source="manual")
    for stage in ("prepare", "applied", "in_progress", "offer", "closed"):
        _insert_job(db, f"https://example.com/stage-{stage}", funnel_stage=stage)

    rows = {r["url"]: r for r in db.execute("SELECT * FROM jobs").fetchall()}

    assert _row_is_protected(rows["https://example.com/plain"]) is False
    assert _row_is_protected(rows["https://example.com/human"]) is True
    assert _row_is_protected(rows["https://example.com/rated"]) is True
    assert _row_is_protected(rows["https://example.com/manual"]) is True
    for stage in ("prepare", "applied", "in_progress", "offer", "closed"):
        assert _row_is_protected(rows[f"https://example.com/stage-{stage}"]) is True


def test_row_is_protected_handles_minimal_row_without_optional_columns():
    mem = sqlite3.connect(":memory:")
    mem.row_factory = sqlite3.Row
    mem.execute("CREATE TABLE jobs (url TEXT PRIMARY KEY, board_updated_by TEXT)")
    mem.execute("INSERT INTO jobs VALUES ('https://example.com/1', NULL)")
    row = mem.execute("SELECT * FROM jobs").fetchone()
    assert _row_is_protected(row) is False
    mem.close()


# ---------------------------------------------------------------------------
# job_is_noise
# ---------------------------------------------------------------------------


def _fetch_row(conn: sqlite3.Connection, url: str) -> sqlite3.Row:
    conn.row_factory = sqlite3.Row
    return conn.execute("SELECT * FROM jobs WHERE url = ?", (url,)).fetchone()


def test_job_is_noise_covers_sites_companies_urls_and_csr(db):
    _insert_job(db, "https://example.com/clean")
    _insert_job(db, "https://example.com/dice", site="Dice")
    _insert_job(db, "https://example.com/custom-site", site=" custombadboard ")
    _insert_job(db, "https://example.com/exc-co", company="Acme Spam Staffing LLC")
    _insert_job(db, "https://jobbank.gc.ca/job/123", site="indeed")
    _insert_job(db, "https://www.randstad.ca/jobs/1", site="indeed")
    _insert_job(db, "https://example.com/csr-bad", title="CSR Receptionist (Temporary, Remote)")
    _insert_job(db, "https://example.com/csr-good", title="Corporate Social Responsibility (CSR) Manager")
    db.commit()

    clean, reason = job_is_noise(_fetch_row(db, "https://example.com/clean"), BASE_CFG)
    assert (clean, reason) == (False, "")

    is_noise, reason = job_is_noise(_fetch_row(db, "https://example.com/dice"), BASE_CFG)
    assert is_noise and reason == "blocked site: Dice"

    is_noise, reason = job_is_noise(_fetch_row(db, "https://example.com/custom-site"), BASE_CFG)
    assert is_noise and reason.startswith("blocked site:")

    is_noise, reason = job_is_noise(_fetch_row(db, "https://example.com/exc-co"), BASE_CFG)
    assert is_noise and reason.startswith("excluded company:")

    is_noise, reason = job_is_noise(_fetch_row(db, "https://jobbank.gc.ca/job/123"), BASE_CFG)
    assert is_noise and reason == "blocked url: .gc.ca"

    is_noise, reason = job_is_noise(_fetch_row(db, "https://www.randstad.ca/jobs/1"), BASE_CFG)
    assert is_noise and reason == "blocked url: randstad.ca"

    is_noise, reason = job_is_noise(_fetch_row(db, "https://example.com/csr-bad"), BASE_CFG)
    assert is_noise and reason.startswith("csr false positive:")

    csr_good, _ = job_is_noise(_fetch_row(db, "https://example.com/csr-good"), BASE_CFG)
    assert csr_good is False


def test_job_is_noise_railroad_titles_and_carveouts(db):
    _insert_job(db, "https://example.com/rail-1", title="Locomotive Engineer / Conductor")
    _insert_job(db, "https://example.com/rail-2", title="Freight Brakeman")
    _insert_job(db, "https://example.com/rail-3", title="Bayway Terminal Shift Lead")
    _insert_job(db, "https://example.com/cos", title="Chief of Staff, Program Conductor Engineer")
    _insert_job(db, "https://example.com/ops", title="Operations Conductor - Engineer")

    for u in ("rail-1", "rail-2", "rail-3"):
        flagged, reason = job_is_noise(_fetch_row(db, f"https://example.com/{u}"), BASE_CFG)
        assert flagged and reason.startswith("noise title:"), u

    for u in ("cos", "ops"):
        flagged, _ = job_is_noise(_fetch_row(db, f"https://example.com/{u}"), BASE_CFG)
        assert flagged is False, u


def test_job_is_noise_location_remote_scope_and_title_vs_salary(db):
    _insert_job(db, "https://example.com/tx", location="Austin, TX")
    _insert_job(db, "https://example.com/remote-emea", location="Remote - EMEA")
    _insert_job(db, "https://example.com/exc-title", title="Enterprise Account Executive")
    _insert_job(db, "https://example.com/low-pay", salary="$75,000/yr")
    _insert_job(
        db,
        "https://example.com/low-pay-desc",
        salary=None,
        description=None,
        full_description="Base compensation is $72,000 per year.",
    )

    flagged, reason = job_is_noise(_fetch_row(db, "https://example.com/tx"), BASE_CFG)
    assert flagged and reason.startswith("location:")

    # Default remote_scope is "us": international-remote markers like EMEA are filtered out.
    flagged, reason = job_is_noise(_fetch_row(db, "https://example.com/remote-emea"), BASE_CFG)
    assert flagged and reason.startswith("location:")

    # With locations[].remote_scope == "any", international remote is kept.
    cfg_any = {
        **BASE_CFG,
        "locations": [{"location": "Remote", "remote": True, "remote_scope": "any"}],
    }
    flagged, _ = job_is_noise(_fetch_row(db, "https://example.com/remote-emea"), cfg_any)
    assert flagged is False

    flagged, reason = job_is_noise(_fetch_row(db, "https://example.com/exc-title"), BASE_CFG)
    assert flagged and reason.startswith("excluded title:")

    flagged, reason = job_is_noise(_fetch_row(db, "https://example.com/low-pay"), BASE_CFG)
    assert flagged and reason == "salary/title filter"

    flagged, reason = job_is_noise(_fetch_row(db, "https://example.com/low-pay-desc"), BASE_CFG)
    assert flagged and reason == "salary/title filter"


# ---------------------------------------------------------------------------
# prune_noise_jobs
# ---------------------------------------------------------------------------


def test_prune_noise_jobs_dry_run_vs_live_tombstones_and_protects_cards(db, tmp_path: Path):
    # Write searches.yaml so search_cfg=None path is also exercised.
    (tmp_path / "searches.yaml").write_text(yaml.safe_dump(BASE_CFG), encoding="utf-8")

    # Noise candidates in backlog (should be pruned).
    _insert_job(db, "https://example.com/noise-site", site="Dice")
    _insert_job(db, "https://example.com/noise-pay", salary="$65,000")
    # Clean backlog job (must stay).
    _insert_job(db, "https://example.com/keep-clean")
    # Protected noise jobs (must NEVER be deleted).
    _insert_job(db, "https://example.com/prot-human", site="Dice", board_updated_by="human")
    _insert_job(db, "https://example.com/prot-rated", site="Dice", user_fit_score=4)
    _insert_job(db, "https://example.com/prot-manual", site="Dice", source="manual")
    _insert_job(db, "https://example.com/prot-prepare", site="Dice", funnel_stage="prepare")
    _insert_job(db, "https://example.com/prot-applied", site="Dice", funnel_stage="applied")

    dry = prune_noise_jobs(db, dry_run=True)
    assert dry == {
        "total": 8,
        "deleted": 2,
        "kept": 6,
        "reasons": {"blocked site": 1, "salary/title filter": 1},
        "dry_run": True,
    }
    assert db.execute("SELECT COUNT(*) FROM jobs").fetchone()[0] == 8
    assert db.execute("SELECT COUNT(*) FROM job_tombstones").fetchone()[0] == 0

    applied = prune_noise_jobs(db, dry_run=False)
    assert applied["deleted"] == 2
    assert applied["kept"] == 6
    assert applied["dry_run"] is False

    remaining = {r[0] for r in db.execute("SELECT url FROM jobs").fetchall()}
    assert remaining == {
        "https://example.com/keep-clean",
        "https://example.com/prot-human",
        "https://example.com/prot-rated",
        "https://example.com/prot-manual",
        "https://example.com/prot-prepare",
        "https://example.com/prot-applied",
    }

    tombstones = {
        r[0]: r[1]
        for r in db.execute("SELECT url, reason FROM job_tombstones").fetchall()
    }
    assert tombstones["https://example.com/noise-site"].startswith("noise:blocked site:")
    assert tombstones["https://example.com/noise-pay"] == "noise:salary/title filter"
    assert "https://example.com/noise-site" in load_known_urls(db)
    with pytest.raises(sqlite3.IntegrityError):
        _insert_job(db, "https://example.com/noise-site")


def test_prune_noise_jobs_reset_dry_run_and_apply(db):
    _insert_job(db, "https://example.com/a")
    _insert_job(db, "https://example.com/b", funnel_stage="applied")
    db.execute(
        "INSERT INTO job_tombstones (url, title, reason, removed_at) "
        "VALUES ('https://example.com/old', 'Old', 'prune:low', datetime('now'))"
    )
    db.commit()

    dry = prune_noise_jobs(db, BASE_CFG, dry_run=True, reset=True)
    assert dry == {
        "total": 2,
        "deleted": 2,
        "kept": 0,
        "reasons": {"reset": 2},
        "dry_run": True,
        "reset": True,
    }
    assert db.execute("SELECT COUNT(*) FROM jobs").fetchone()[0] == 2
    assert db.execute("SELECT COUNT(*) FROM job_tombstones").fetchone()[0] == 1

    res = prune_noise_jobs(db, BASE_CFG, dry_run=False, reset=True)
    assert res["deleted"] == 2
    assert res["reset"] is True
    assert db.execute("SELECT COUNT(*) FROM jobs").fetchone()[0] == 0
    assert db.execute("SELECT COUNT(*) FROM job_tombstones").fetchone()[0] == 0


# ---------------------------------------------------------------------------
# reapply_fit_score_guards and prune_after_score
# ---------------------------------------------------------------------------


def test_reapply_fit_score_guards_caps_excluded_and_mission_offtrack(db, tmp_path: Path):
    mission_cfg = {
        **BASE_CFG,
        "scoring": {"mission_guard": True},
    }
    (tmp_path / "searches.yaml").write_text(yaml.safe_dump(mission_cfg), encoding="utf-8")

    _insert_job(db, "https://example.com/gtm-high", title="GTM Manager", fit_score=9)
    _insert_job(
        db,
        "https://example.com/cos-corp",
        title="Chief of Staff",
        company="Generic Corp",
        full_description="Drive quarterly revenue operations.",
        fit_score=8,
    )
    _insert_job(
        db,
        "https://example.com/cos-impact",
        title="Chief of Staff",
        company="Acme Foundation",
        full_description="Lead philanthropy and grantmaking.",
        fit_score=8,
    )
    _insert_job(db, "https://example.com/already-low", title="GTM Lead", fit_score=3)

    updated = reapply_fit_score_guards(db)
    assert updated == 2

    scores = {r[0]: r[1] for r in db.execute("SELECT url, fit_score FROM jobs").fetchall()}
    assert scores["https://example.com/gtm-high"] == 4
    assert scores["https://example.com/cos-corp"] == 4
    assert scores["https://example.com/cos-impact"] == 8
    assert scores["https://example.com/already-low"] == 3


def test_prune_after_score_handles_mission_guard_unscored_protected_and_tombstones(db, tmp_path: Path):
    mission_cfg = {
        **BASE_CFG,
        "scoring": {"mission_guard": True},
    }
    (tmp_path / "searches.yaml").write_text(yaml.safe_dump(mission_cfg), encoding="utf-8")

    # Should be deleted:
    _insert_job(db, "https://example.com/noise", site="Dice", fit_score=8)
    _insert_job(
        db,
        "https://example.com/off-track",
        title="Strategy Manager",
        company="Generic Corp",
        full_description="Corporate retail planning.",
        fit_score=7,
    )
    _insert_job(
        db,
        "https://example.com/low-score",
        title="Program Officer",
        company="Acme Foundation",
        full_description="Social impact grantmaking.",
        fit_score=3,
    )

    # Should be kept:
    _insert_job(
        db,
        "https://example.com/unscored",
        title="Program Officer",
        company="Acme Foundation",
        fit_score=None,
    )
    _insert_job(
        db,
        "https://example.com/kept-impact",
        title="Program Officer",
        company="Acme Foundation",
        full_description="Social impact grantmaking.",
        fit_score=7,
    )
    # Protected despite off-track / low score / noise:
    _insert_job(db, "https://example.com/prot-rated", site="Dice", fit_score=2, user_fit_score=2)
    _insert_job(db, "https://example.com/prot-manual", site="Dice", fit_score=2, source="manual")
    _insert_job(db, "https://example.com/prot-in-prog", site="Dice", fit_score=2, funnel_stage="in_progress")

    # Dry run via default conn=None and search_cfg=None leaves DB untouched.
    dry = prune_after_score(dry_run=True)
    assert dry["deleted"] == 3
    assert dry["kept"] == 5
    assert dry["total"] == 8
    assert dry["reasons"] == {"blocked site": 1, "off-track": 1, "low score": 1}
    assert db.execute("SELECT COUNT(*) FROM jobs").fetchone()[0] == 8

    # Live run removes the 3 bad backlog rows and writes prune:* tombstones.
    res = prune_after_score(dry_run=False)
    assert res["deleted"] == 3
    assert res["kept"] == 5

    kept_urls = {r[0] for r in db.execute("SELECT url FROM jobs").fetchall()}
    assert kept_urls == {
        "https://example.com/unscored",
        "https://example.com/kept-impact",
        "https://example.com/prot-rated",
        "https://example.com/prot-manual",
        "https://example.com/prot-in-prog",
    }

    tombstones = {
        r[0]: r[1]
        for r in db.execute("SELECT url, reason FROM job_tombstones").fetchall()
    }
    assert tombstones["https://example.com/noise"].startswith("prune:blocked site:")
    assert tombstones["https://example.com/off-track"] == "prune:off-track"
    assert tombstones["https://example.com/low-score"] == "prune:low score:3"


def test_prune_after_score_keeps_offtrack_when_mission_guard_off_and_respects_threshold(db):
    _insert_job(
        db,
        "https://example.com/corp-ops",
        title="Strategy Manager",
        company="Generic Corp",
        full_description="Corporate retail planning.",
        fit_score=5,
    )
    _insert_job(
        db,
        "https://example.com/borderline",
        title="Program Officer",
        company="Acme Foundation",
        full_description="Social impact grantmaking.",
        fit_score=4,
    )

    # Without scoring.mission_guard=True, corp-ops is NOT dropped as off-track.
    res = prune_after_score(db, BASE_CFG, dry_run=False, drop_at_or_below=3)
    assert res["deleted"] == 0
    assert res["kept"] == 2

    # Raising drop_at_or_below=4 prunes fit_score == 4 while keeping fit_score == 5.
    res2 = prune_after_score(db, BASE_CFG, dry_run=False, drop_at_or_below=4)
    assert res2["deleted"] == 1
    kept = [r[0] for r in db.execute("SELECT url FROM jobs").fetchall()]
    assert kept == ["https://example.com/corp-ops"]
