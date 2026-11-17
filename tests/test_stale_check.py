"""Tests for scripts/stale_check.py: candidate filter and CLI help.

No live Playwright: the weekly recheck opens real job URLs; these tests cover
selection rules and that --help stays wired.
"""

from __future__ import annotations

import importlib.util
import sqlite3
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

import jobwright.config as cfg
from jobwright.database import close_connection, get_connection, init_db

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "scripts" / "stale_check.py"


def _load_stale_check():
    spec = importlib.util.spec_from_file_location("stale_check_under_test", SCRIPT)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture()
def db(tmp_path: Path):
    cfg.set_app_dir(tmp_path)
    path = tmp_path / "jobwright.db"
    close_connection(path)
    init_db(path)
    yield get_connection()
    close_connection(path)


def _insert(
    conn: sqlite3.Connection,
    url: str,
    *,
    title: str = "Program Manager",
    funnel_stage: str = "backlog",
    board_updated_by: str | None = None,
    detail_scraped_at: str | None = "2026-01-01T00:00:00+00:00",
    discovered_at: str | None = None,
) -> None:
    if discovered_at is None:
        discovered_at = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
    conn.execute(
        "INSERT INTO jobs ("
        "url, title, company, site, funnel_stage, board_updated_by, "
        "detail_scraped_at, discovered_at"
        ") VALUES (?, ?, 'Acme', 'indeed', ?, ?, ?, ?)",
        (url, title, funnel_stage, board_updated_by, detail_scraped_at, discovered_at),
    )
    conn.commit()


def test_candidate_rows_keeps_old_enriched_backlog_only(db):
    stale = _load_stale_check()
    old = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
    recent = (datetime.now(timezone.utc) - timedelta(days=3)).isoformat()

    _insert(db, "https://example.com/keep", discovered_at=old)
    _insert(db, "https://example.com/fresh", discovered_at=recent)
    _insert(db, "https://example.com/no-detail", discovered_at=old, detail_scraped_at=None)
    _insert(db, "https://example.com/human", discovered_at=old, board_updated_by="human")
    _insert(db, "https://example.com/applied", discovered_at=old, funnel_stage="applied")
    _insert(db, "https://example.com/prepare", discovered_at=old, funnel_stage="prepare")

    rows = stale._candidate_rows(db, max_age_days=14)
    urls = {r["url"] for r in rows}
    assert urls == {"https://example.com/keep"}


def test_live_check_marks_404_and_closed_copy():
    stale = _load_stale_check()

    class FakeResp:
        def __init__(self, status: int):
            self.status = status

    class FakePage:
        def __init__(self, *, status: int = 200, body: str = "<html>open role</html>"):
            self._status = status
            self._body = body

        def goto(self, url, timeout=30000):
            return FakeResp(self._status)

        def wait_for_load_state(self, *a, **k):
            return None

        def content(self):
            return self._body

    assert stale._live_check(FakePage(status=404), "https://example.com/x") == "HTTP 404"
    assert stale._live_check(FakePage(status=410), "https://example.com/x") == "HTTP 410"
    closed = FakePage(body="<p>This job no longer exists on our careers site.</p>")
    assert stale._live_check(closed, "https://example.com/x") == "this job no longer exists"
    assert stale._live_check(FakePage(), "https://example.com/x") is None


def test_stale_check_help_exits_zero():
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--help"],
        cwd=REPO,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0
    assert "--dry-run" in result.stdout
    assert "--max-age-days" in result.stdout
