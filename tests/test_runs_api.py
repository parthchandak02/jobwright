"""Tests for the observable/controllable run API (runs.py)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from jobwright.database import close_connection, init_db


@pytest.fixture()
def api_client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    monkeypatch.setenv("JOBWRIGHT_DASHBOARD_USER", "testdash")
    monkeypatch.setenv("JOBWRIGHT_USERS_ROOT", str(tmp_path / "users"))
    users_root = tmp_path / "users"
    users_root.mkdir()
    (users_root / "users.yaml").write_text(
        "users:\n  - user_id: testdash\n    name: Test\n    apply_enabled: false\n",
        encoding="utf-8",
    )
    data_dir = users_root / "testdash"
    data_dir.mkdir()
    log_dir = data_dir / "logs"
    monkeypatch.setattr("jobwright.config.APP_DIR", data_dir)
    monkeypatch.setattr("jobwright.config.DB_PATH", data_dir / "jobwright.db")
    monkeypatch.setattr("jobwright.config.LOG_DIR", log_dir)

    import jobwright.users as users_mod

    monkeypatch.setattr(users_mod, "USERS_ROOT", users_root)
    monkeypatch.setattr(users_mod, "REGISTRY_PATH", users_root / "users.yaml")

    # Launch a harmless long-lived process instead of the real pipeline so the
    # start/stop lifecycle is fast and hermetic.
    def _fake_cmd(args, user_id):  # noqa: ANN001, ANN202
        return [sys.executable, "-c", "import time; time.sleep(30)"]

    monkeypatch.setattr("jobwright.web.routers.runs._jobwright_cmd", _fake_cmd)

    close_connection(data_dir / "jobwright.db")
    init_db(data_dir / "jobwright.db")

    from jobwright.web.app import app
    from jobwright.web.routers import runs as runs_mod

    with TestClient(app) as client:
        yield client

    # Teardown: never leave background processes running.
    for info in list(runs_mod._runs.values()):
        proc = info.get("proc")
        if proc is not None and proc.poll() is None:
            proc.kill()
            try:
                proc.wait(timeout=3)
            except Exception:
                pass
    runs_mod._runs.clear()
    close_connection(data_dir / "jobwright.db")


def test_run_lifecycle(api_client):
    # Registry-merge path must not crash when web_runs.json is absent.
    res = api_client.get("/api/runs")
    assert res.status_code == 200
    assert res.json()["runs"] == []

    # Start a run.
    res = api_client.post("/api/run", json={"stages": ["score"]})
    assert res.status_code == 200
    body = res.json()
    run_id = body["run_id"]
    assert body["pid"]
    assert body["user"] == "testdash"
    assert body["log_path"]
    assert Path(body["log_path"]).exists()

    # It shows up in the list, newest first.
    res = api_client.get("/api/runs")
    assert res.status_code == 200
    runs = res.json()["runs"]
    assert any(r["run_id"] == run_id for r in runs)
    listed = next(r for r in runs if r["run_id"] == run_id)
    assert listed["pid"] == body["pid"]
    assert listed["running"] is True
    assert listed["user"] == "testdash"

    # Single-run status includes pid.
    res = api_client.get(f"/api/runs/{run_id}")
    assert res.status_code == 200
    status = res.json()
    assert status["pid"] == body["pid"]
    assert status["running"] is True

    # Stop it.
    res = api_client.post(f"/api/runs/{run_id}/stop")
    assert res.status_code == 200
    assert res.json()["stopped"] is True

    # Unknown run -> 404.
    assert api_client.get("/api/runs/deadbeef").status_code == 404
    assert api_client.post("/api/runs/deadbeef/stop").status_code == 404


def test_registry_persists_across_memory_clear(api_client):
    res = api_client.post("/api/run", json={"stages": ["score"]})
    assert res.status_code == 200
    run_id = res.json()["run_id"]

    from jobwright.web.routers import runs as runs_mod

    # Simulate an API restart: drop in-memory state, keep the on-disk registry.
    for info in list(runs_mod._runs.values()):
        proc = info.get("proc")
        if proc is not None and proc.poll() is None:
            proc.kill()
    runs_mod._runs.clear()

    res = api_client.get("/api/runs")
    assert res.status_code == 200
    assert any(r["run_id"] == run_id for r in res.json()["runs"])

    res = api_client.get(f"/api/runs/{run_id}")
    assert res.status_code == 200
    assert res.json()["run_id"] == run_id
