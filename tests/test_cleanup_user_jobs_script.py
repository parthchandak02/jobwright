"""Tests for scripts/cleanup_user_jobs.sh: flag docs and hermetic dry-run.

Live prune rules live in tests/test_discovery_cleanup.py. This file only
checks the shell entrypoint stays wired and defaults to dry-run.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

import jobwright.config as cfg
from jobwright.database import close_connection, get_connection, init_db

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "scripts" / "cleanup_user_jobs.sh"

SEARCH_CFG = {
    "queries": [{"query": "program manager", "tier": 1}],
    "locations": [{"location": "San Francisco, CA", "remote": False}],
    "excluded_titles": ["Intern"],
    "salary_floor": 100000,
}


@pytest.fixture()
def user_dir(tmp_path: Path) -> Path:
    app = tmp_path / "user1"
    app.mkdir()
    (app / "searches.yaml").write_text(yaml.safe_dump(SEARCH_CFG), encoding="utf-8")
    cfg.set_app_dir(app)
    db_path = app / "jobwright.db"
    close_connection(db_path)
    conn = init_db(db_path)
    conn.execute(
        "INSERT INTO jobs (url, title, company, site, salary, funnel_stage, location) "
        "VALUES (?, ?, 'Acme', 'Dice', '$65,000', 'backlog', 'San Francisco, CA')",
        ("https://example.com/noise", "Program Manager"),
    )
    conn.execute(
        "INSERT INTO jobs (url, title, company, site, salary, funnel_stage, location) "
        "VALUES (?, ?, 'Acme', 'indeed', '$180,000', 'backlog', 'San Francisco, CA')",
        ("https://example.com/keep", "Program Manager"),
    )
    conn.commit()
    close_connection(db_path)
    return app


def test_cleanup_script_documents_flags_and_entrypoint():
    text = SCRIPT.read_text(encoding="utf-8")
    assert text.startswith("#!/usr/bin/env bash")
    assert "prune_noise_jobs" in text
    assert "--apply" in text
    assert "--reset" in text
    assert "JOBWRIGHT_USER=richa bash scripts/cleanup_user_jobs.sh" in text
    assert "dry-run prune" in text


def test_cleanup_script_dry_run_default_prints_stats_and_keeps_rows(user_dir: Path):
    if shutil.which("bash") is None:
        pytest.skip("bash not available")

    env = {
        **os.environ,
        "JOBWRIGHT_REPO": str(REPO),
        "JOBWRIGHT_DIR": str(user_dir),
        "JOBWRIGHT_ENV": str(user_dir / "missing.env"),
        "JOBWRIGHT_HERMES_DRY_RUN": "1",
        "PYTHONPATH": f"{REPO / 'src'}{os.pathsep}{os.environ.get('PYTHONPATH', '')}",
    }
    env.pop("JOBWRIGHT_USER", None)

    result = subprocess.run(
        ["bash", str(SCRIPT)],
        cwd=REPO,
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    stats = json.loads(result.stdout)
    assert stats["dry_run"] is True
    assert stats["total"] == 2
    assert stats["deleted"] >= 1
    assert "reset" not in stats

    cfg.set_app_dir(user_dir)
    conn = get_connection()
    try:
        urls = {r[0] for r in conn.execute("SELECT url FROM jobs").fetchall()}
    finally:
        close_connection(cfg.DB_PATH)
    assert urls == {"https://example.com/noise", "https://example.com/keep"}
