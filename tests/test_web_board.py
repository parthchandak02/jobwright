"""Smoke tests for Kanban FastAPI routers (no live server required)."""

from __future__ import annotations

from pathlib import Path

import pytest

from jobwright.database import close_connection, init_db, insert_manual_job


@pytest.fixture()
def api_client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    monkeypatch.setenv("JOBWRIGHT_DASHBOARD_USER", "testdash")
    monkeypatch.setenv("JOBWRIGHT_USERS_ROOT", str(tmp_path / "users"))
    users_root = tmp_path / "users"
    users_root.mkdir()
    (users_root / "users.yaml").write_text(
        "users:\n  - user_id: testdash\n    name: Test\n    apply_enabled: false\n"
        "    schedule: 0 6 * * *\n",
        encoding="utf-8",
    )
    data_dir = users_root / "testdash"
    data_dir.mkdir()
    monkeypatch.setattr("jobwright.config.APP_DIR", data_dir)
    monkeypatch.setattr("jobwright.config.DB_PATH", data_dir / "jobwright.db")
    monkeypatch.setattr("jobwright.config.TAILORED_DIR", data_dir / "tailored_resumes")
    monkeypatch.setattr("jobwright.config.COVER_LETTER_DIR", data_dir / "cover_letters")
    monkeypatch.setattr("jobwright.config.NETWORK_DIR", data_dir / "network")
    monkeypatch.setattr("jobwright.config.LOG_DIR", data_dir / "logs")

    # Rebuild users module roots for this test
    import jobwright.users as users_mod

    monkeypatch.setattr(users_mod, "USERS_ROOT", users_root)
    monkeypatch.setattr(users_mod, "REGISTRY_PATH", users_root / "users.yaml")

    close_connection(data_dir / "jobwright.db")
    init_db(data_dir / "jobwright.db")
    insert_manual_job(
        "https://example.com/web-smoke",
        title="Smoke Role",
        company="TestCo",
        funnel_stage="backlog",
    )

    from jobwright.web.app import app

    with TestClient(app) as client:
        yield client
    close_connection(data_dir / "jobwright.db")


def test_derive_work_model():
    from jobwright.web.routers.board import _derive_work_model

    assert _derive_work_model("San Francisco, CA (Remote)") == "remote"
    assert _derive_work_model("New York, NY (Hybrid)") == "hybrid"
    assert _derive_work_model("Austin, TX") == "onsite"
    assert _derive_work_model(None) is None
    assert _derive_work_model("") is None


def test_derive_sponsorship_status():
    from jobwright.enrichment.sponsorship import derive_sponsorship_status

    assert derive_sponsorship_status(None) == "not_found"
    assert derive_sponsorship_status("") == "not_found"
    assert (
        derive_sponsorship_status("Must be authorized to work without sponsorship.")
        == "not_required"
    )
    assert (
        derive_sponsorship_status("This position is not eligible for Visa sponsorship.")
        == "not_required"
    )
    assert (
        derive_sponsorship_status("We offer visa sponsorship for qualified candidates.")
        == "required"
    )
    assert derive_sponsorship_status("Executive sponsor for partner programs.") == "not_found"


def test_health(api_client):
    res = api_client.get("/api/health")
    assert res.status_code == 200
    assert res.json()["ok"] is True


def test_profile_includes_schedule(api_client):
    res = api_client.get("/api/profile")
    assert res.status_code == 200
    body = res.json()
    assert body["schedule"] == "0 6 * * *"
    assert body["schedule_label"] == "Every day at 6:00 AM"
    assert body["timezone"]
    assert body["brief_cron_name"] == "jobwright-brief-testdash"
    assert "whatsapp_target" in body


def test_put_profile_saves_schedule(api_client, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(
        "jobwright.web.routers.system.sync_brief_cron",
        lambda uid, sched, deliver: {
            "synced": True,
            "name": f"jobwright-brief-{uid}",
            "cron_id": "abc123",
            "error": None,
        },
    )
    res = api_client.put(
        "/api/profile",
        json={"schedule": "30 7 * * *", "whatsapp_target": "15551212"},
    )
    assert res.status_code == 200
    body = res.json()
    assert body["schedule"] == "30 7 * * *"
    assert body["schedule_label"] == "Every day at 7:30 AM"
    assert body["whatsapp_target"] == "whatsapp:15551212"
    assert body["cron_synced"] is True

    res = api_client.put("/api/profile", json={"schedule": "0 */3 * * 1-5"})
    assert res.status_code == 400


def test_board_lists_job(api_client):
    res = api_client.get("/api/board")
    assert res.status_code == 200
    body = res.json()
    assert "backlog" in body["columns"]
    urls = [j["url"] for j in body["columns"]["backlog"]]
    assert "https://example.com/web-smoke" in urls


def test_move_and_response(api_client):
    url = "https://example.com/web-smoke"
    enc = __import__("urllib.parse").parse.quote(url, safe="")
    res = api_client.post(f"/api/jobs/{enc}/move", json={"to_stage": "applied"})
    assert res.status_code == 200
    assert res.json()["job"]["funnel_stage"] == "applied"

    res = api_client.post(f"/api/jobs/{enc}/response")
    assert res.status_code == 200
    assert res.json()["first_response_at"]


def test_job_subroutes_not_shadowed(api_client):
    """Specific /jobs/{url}/materials|connections must win over /jobs/{url:path}."""
    url = "https://example.com/web-smoke"
    enc = __import__("urllib.parse").parse.quote(url, safe="")

    res = api_client.get(f"/api/jobs/{enc}/materials")
    assert res.status_code == 200
    body = res.json()
    assert body["url"] == url
    assert "resume_docx" in body
    assert "resume_md" in body
    assert "resume_preview" in body
    assert "cover_preview" in body
    assert "resume_pdf" in body
    assert "cover_pdf" in body

    res = api_client.get(f"/api/jobs/{enc}/connections")
    assert res.status_code == 200
    body = res.json()
    assert body["url"] == url
    assert body["csv_contacts"] == []
    assert body["web_contacts"] == []
    assert body["manual_contacts"] == []


def test_manual_connections_api(api_client, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    url = "https://example.com/web-smoke"
    enc = __import__("urllib.parse").parse.quote(url, safe="")
    network = tmp_path / "users" / "testdash" / "network"
    network.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr("jobwright.network.manual_connections.config.NETWORK_DIR", network)

    res = api_client.post(
        f"/api/jobs/{enc}/connections",
        json={
            "first_name": "Pat",
            "last_name": "Lee",
            "url": "https://www.linkedin.com/in/pat-lee",
        },
    )
    assert res.status_code == 200
    body = res.json()
    assert len(body["manual_contacts"]) == 1
    contact_id = body["contact"]["id"]

    res = api_client.get(f"/api/jobs/{enc}/connections")
    assert res.status_code == 200
    assert len(res.json()["manual_contacts"]) == 1

    res = api_client.delete(f"/api/jobs/{enc}/connections/{contact_id}")
    assert res.status_code == 200
    assert res.json()["manual_contacts"] == []


def test_users_and_session(api_client):
    res = api_client.get("/api/users")
    assert res.status_code == 200
    body = res.json()
    assert any(u["user_id"] == "testdash" for u in body["users"])

    res = api_client.post("/api/session", json={"user_id": "testdash"})
    assert res.status_code == 200
    assert res.json()["user_id"] == "testdash"
    assert "jobwright_user" in res.cookies

    res = api_client.post("/api/session", json={"user_id": "nope"})
    assert res.status_code == 400