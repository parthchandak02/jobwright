"""Smoke tests for Kanban FastAPI routers (no live server required)."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from jobwright.database import close_connection, get_connection, init_db, insert_manual_job


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

        import jobwright.config as _cfg


        _cfg.set_app_dir(data_dir)
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
        "jobwright.web.routers.system.ensure_brief_cron",
        lambda uid, sched: {"ok": True, "name": f"jobwright-brief-{uid}", "cron_id": "abc123", "error": None},
    )
    monkeypatch.setattr("jobwright.onboarding.is_set_up", lambda uid: True)
    monkeypatch.setattr("jobwright.welcome.send_welcome_async", lambda uid: None)
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


def test_put_searches_keeps_remote_scope_and_accepts_new_cities(api_client):
    import jobwright.config as cfg

    cfg.SEARCH_CONFIG_PATH.write_text(
        "location:\n  accept_patterns: [Chicago]\n  reject_patterns: [India]\n", encoding="utf-8"
    )
    res = api_client.put(
        "/api/settings/searches",
        json={"locations": [
            {"location": "Denver, CO", "remote": False, "remote_scope": "any"},
            {"location": "Remote", "remote": True, "remote_scope": "bogus"},
        ]},
    )
    assert res.status_code == 200
    saved = yaml.safe_load(cfg.SEARCH_CONFIG_PATH.read_text(encoding="utf-8"))
    assert saved["locations"] == [
        {"location": "Denver, CO", "remote": False},
        {"location": "Remote", "remote": True, "remote_scope": "us"},
    ]
    assert saved["location"]["accept_patterns"] == ["Chicago", "Denver", "CO", "Remote"]
    assert saved["location"]["reject_patterns"] == ["India"]


def test_put_searches_sets_preserves_and_clears_defaults(api_client):
    import jobwright.config as cfg

    cfg.SEARCH_CONFIG_PATH.write_text("defaults:\n  country_indeed: usa\n", encoding="utf-8")

    # Set both defaults
    res = api_client.put(
        "/api/settings/searches",
        json={"hours_old": 48, "results_per_site": 25},
    )
    assert res.status_code == 200
    searches = api_client.get("/api/settings").json()["searches"]
    assert searches["hours_old"] == 48
    assert searches["results_per_site"] == 25

    # Omitting results_per_site leaves it unchanged
    res = api_client.put("/api/settings/searches", json={"hours_old": 96})
    assert res.status_code == 200
    searches = api_client.get("/api/settings").json()["searches"]
    assert searches["hours_old"] == 96
    assert searches["results_per_site"] == 25

    # Clearing hours_old removes it from defaults while preserving results_per_site
    res = api_client.put("/api/settings/searches", json={"hours_old": None})
    assert res.status_code == 200
    searches = api_client.get("/api/settings").json()["searches"]
    assert searches["hours_old"] is None
    assert searches["results_per_site"] == 25
    saved = yaml.safe_load(cfg.SEARCH_CONFIG_PATH.read_text(encoding="utf-8"))
    assert "hours_old" not in saved["defaults"]
    assert saved["defaults"]["results_per_site"] == 25

    # Clearing results_per_site removes it from defaults while preserving other keys
    res = api_client.put("/api/settings/searches", json={"results_per_site": None})
    assert res.status_code == 200
    searches = api_client.get("/api/settings").json()["searches"]
    assert searches["hours_old"] is None
    assert searches["results_per_site"] is None
    saved = yaml.safe_load(cfg.SEARCH_CONFIG_PATH.read_text(encoding="utf-8"))
    assert "results_per_site" not in saved["defaults"]
    assert saved["defaults"]["country_indeed"] == "usa"


def test_put_searches_rejects_invalid_numeric_bounds(api_client):
    for bad_payload in (
        {"hours_old": 0},
        {"hours_old": -12},
        {"results_per_site": 0},
        {"results_per_site": -5},
        {"min_salary": -1},
    ):
        res = api_client.put("/api/settings/searches", json=bad_payload)
        assert res.status_code in (400, 422), (bad_payload, res.status_code, res.text)

    # Valid boundary values still succeed
    res = api_client.put(
        "/api/settings/searches",
        json={"min_salary": 0, "hours_old": 1, "results_per_site": 1},
    )
    assert res.status_code == 200
    searches = api_client.get("/api/settings").json()["searches"]
    assert searches["min_salary"] == 0
    assert searches["hours_old"] == 1
    assert searches["results_per_site"] == 1

    res = api_client.put("/api/settings/searches", json={"min_salary": None})
    assert res.status_code == 200
    assert api_client.get("/api/settings").json()["searches"]["min_salary"] is None


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

    res = api_client.get(f"/api/jobs/{enc}/materials/resume.pdf")
    assert res.status_code == 404

    res = api_client.get(f"/api/jobs/{enc}/materials/cover.pdf")
    assert res.status_code == 404

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


def test_job_connections_drops_job_posting_web_results(api_client):
    import json

    from jobwright import config

    url = "https://example.com/web-smoke"
    enc = __import__("urllib.parse").parse.quote(url, safe="")
    network = Path(config.NETWORK_DIR)
    network.mkdir(parents=True, exist_ok=True)
    (network / "job_contacts_latest.json").write_text(
        json.dumps(
            {
                "jobs": {
                    url: {
                        "title": "Programme Coordinator, Trustlaw",
                        "company": "Thomson Reuters",
                        "csv_contacts": [],
                        "web_contacts": [
                            {
                                "name": "Programme Coordinator",
                                "role": "Programme Coordinator, Trustlaw-Thomson Reuters Foundation",
                                "source_url": (
                                    "https://thomsonreuters.wd5.myworkdayjobs.com/job/x"
                                ),
                                "note": "Public web result",
                                "source": "web",
                            },
                            {
                                "name": "Pat Lee",
                                "role": "Recruiter at Acme",
                                "source_url": "https://www.linkedin.com/in/pat-lee",
                                "note": "Hiring contact",
                                "source": "web",
                            },
                        ],
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    res = api_client.get(f"/api/jobs/{enc}/connections")
    assert res.status_code == 200
    web = res.json()["web_contacts"]
    assert len(web) == 1
    assert web[0]["name"] == "Pat Lee"
    assert web[0]["url"] == "https://www.linkedin.com/in/pat-lee"
    assert web[0]["why"] == "Hiring contact"


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
    assert res.status_code == 404

def test_dismiss_with_reason_records_label_and_undo_applied(api_client):
    from jobwright.database import get_connection

    url = "https://example.com/web-smoke"
    res = api_client.post(f"/api/jobs/{url}/move", json={"to_stage": "applied"})
    assert res.status_code == 200
    res = api_client.post(f"/api/jobs/{url}/move", json={"to_stage": "backlog"})
    row = get_connection().execute("SELECT applied_at, applied_manually FROM jobs WHERE url = ?", (url,)).fetchone()
    assert row[0] is None and not row[1]
    res = api_client.post(
        f"/api/jobs/{url}/move",
        json={"to_stage": "closed", "outcome": "not_interested", "reasons": ["Too senior", "Wrong location"]},
    )
    assert res.status_code == 200, res.text
    card = res.json()["job"]
    assert card["close_reason"] == "Too senior, Wrong location" and card["user_fit_score"] == 2
    labels = api_client.get(f"/api/jobs/{card['job_id']}/labels").json()["labels"]
    assert labels[0]["source"] == "dismiss" and labels[0]["reasons"] == ["Too senior", "Wrong location"]


def test_search_finds_jobs_by_any_field_and_ranks_title_first(api_client) -> None:
    from jobwright.database import get_connection

    insert_manual_job("https://example.com/s1", title="Data Analyst", company="Acme", funnel_stage="backlog")
    insert_manual_job("https://example.com/s2", title="Designer", company="Data Corp", funnel_stage="closed")
    insert_manual_job("https://example.com/s3", title="Engineer", company="Zed", funnel_stage="prepare")
    conn = get_connection()
    conn.execute(
        "UPDATE jobs SET full_description = ? WHERE url = ?",
        ("We build tools. You will work with data pipelines every day.", "https://example.com/s3"),
    )
    conn.commit()

    body = api_client.get("/api/search", params={"q": "data"}).json()
    urls = [r["url"] for r in body["results"]]
    assert urls[0] == "https://example.com/s1"  # title beats company beats description
    assert set(urls) == {"https://example.com/s1", "https://example.com/s2", "https://example.com/s3"}
    s3 = next(r for r in body["results"] if r["url"] == "https://example.com/s3")
    assert "data pipelines" in s3["snippet"]
    assert len(s3["job_id"]) == 12

    # Every word must match somewhere.
    both = api_client.get("/api/search", params={"q": "data acme"}).json()
    assert [r["url"] for r in both["results"]] == ["https://example.com/s1"]

    # LIKE wildcards are literal.
    assert api_client.get("/api/search", params={"q": "%"}).json()["results"] == []
    assert api_client.get("/api/search", params={"q": "  "}).json()["results"] == []


def test_patch_application_url_save_clear_and_reject(api_client):
    from urllib.parse import quote

    enc = quote("https://example.com/web-smoke", safe="")
    res = api_client.patch(f"/api/jobs/{enc}", json={"application_url": " https://boards.greenhouse.io/co/jobs/1 "})
    assert res.status_code == 200
    assert res.json()["application_url"] == "https://boards.greenhouse.io/co/jobs/1"
    row = get_connection().execute(
        "SELECT application_url_source, application_ats FROM jobs WHERE url = ?", ("https://example.com/web-smoke",)
    ).fetchone()
    assert row["application_url_source"] == "dashboard"
    assert row["application_ats"] == "greenhouse"

    for bad in ("ftp://example.com/x", "not a link", "https://www.linkedin.com/jobs/view/1"):
        assert api_client.patch(f"/api/jobs/{enc}", json={"application_url": bad}).status_code == 400

    res = api_client.patch(f"/api/jobs/{enc}", json={"application_url": ""})
    assert res.status_code == 200
    assert res.json()["application_url"] == "https://example.com/web-smoke"
    row = get_connection().execute(
        "SELECT application_url, application_url_source FROM jobs WHERE url = ?", ("https://example.com/web-smoke",)
    ).fetchone()
    assert row["application_url"] is None and row["application_url_source"] is None


def test_stage_history_tracks_lane_transitions(api_client):
    from urllib.parse import quote

    url = "https://example.com/web-smoke"
    enc = quote(url, safe="")
    assert api_client.post(f"/api/jobs/{enc}/move", json={"to_stage": "prepare"}).status_code == 200
    assert api_client.post(f"/api/jobs/{enc}/move", json={"to_stage": "applied"}).status_code == 200

    res = api_client.get(f"/api/jobs/{enc}/history")
    assert res.status_code == 200
    body = res.json()
    assert body["url"] == url
    transitions = [(h["from_stage"], h["to_stage"]) for h in body["history"]]
    assert ("backlog", "prepare") in transitions
    assert ("prepare", "applied") in transitions


def test_custom_answers_and_undo_api(api_client):
    assert api_client.put("/api/answers/custom", json={"question": "   ", "value": "Yes"}).status_code == 400

    first = api_client.put(
        "/api/answers/custom",
        json={"question": "Do you hold a PMP certification?", "value": "No"},
    )
    assert first.status_code == 200
    assert list(first.json()["custom"].values())[0]["value"] == "No"

    updated = api_client.put(
        "/api/answers/custom",
        json={"question": "Do you hold a PMP certification?", "value": "Yes"},
    )
    assert updated.status_code == 200
    assert list(updated.json()["custom"].values())[0]["value"] == "Yes"

    undone = api_client.post(
        "/api/answers/undo",
        json={"question": "Do you hold a PMP certification?"},
    )
    assert undone.status_code == 200
    assert list(undone.json()["custom"].values())[0]["value"] == "No"

    # Second undo removes the entry since it had no prior value; third returns 404.
    cleared = api_client.post(
        "/api/answers/undo",
        json={"question": "Do you hold a PMP certification?"},
    )
    assert cleared.status_code == 200
    assert cleared.json()["custom"] == {}
    assert (
        api_client.post(
            "/api/answers/undo",
            json={"question": "Do you hold a PMP certification?"},
        ).status_code
        == 404
    )
    assert api_client.post("/api/answers/undo", json={}).status_code == 400
    assert api_client.post("/api/answers/undo", json={"key": "not_a_key"}).status_code == 400


def test_notify_preview_and_send_api(api_client, monkeypatch: pytest.MonkeyPatch):
    from jobwright import notify
    from jobwright.database import get_connection, job_id_for_url

    url = "https://example.com/web-smoke"
    conn = get_connection()
    conn.execute(
        "UPDATE jobs SET funnel_stage = 'prepare', fit_score = 9, discovered_at = datetime('now') WHERE url = ?",
        (url,),
    )
    conn.commit()

    preview = api_client.get("/api/notify/preview")
    assert preview.status_code == 200
    body = preview.json()
    assert body["dry_run"] is True
    assert body["jobs"][0]["job_id"] == job_id_for_url(url)
    assert conn.execute("SELECT whatsapp_notified_at FROM jobs WHERE url = ?", (url,)).fetchone()[0] is None

    # Missing whatsapp_target maps ValueError to HTTP 400.
    res = api_client.post("/api/notify")
    assert res.status_code == 400

    # Configure target and verify Hermes failure maps RuntimeError to HTTP 502.
    monkeypatch.setattr(
        notify, "get_user", lambda _uid: type("U", (), {"whatsapp_target": "whatsapp:120363999999999901@g.us"})()
    )

    def _fail(*_a, **_k):
        raise RuntimeError("hermes bridge unavailable")

    monkeypatch.setattr(notify, "send_via_hermes", _fail)
    assert api_client.post("/api/notify").status_code == 502

    # Successful send stamps whatsapp_notified_at.
    sent: list[tuple[str, str]] = []
    monkeypatch.setattr(notify, "send_via_hermes", lambda msg, target: sent.append((msg, target)))
    ok = api_client.post("/api/notify")
    assert ok.status_code == 200
    assert ok.json()["sent"] == 1
    assert len(sent) == 1
    assert conn.execute("SELECT whatsapp_notified_at FROM jobs WHERE url = ?", (url,)).fetchone()[0] is not None


def test_job_by_short_id_detail_and_patch_fields(api_client):
    from urllib.parse import quote

    from jobwright.database import get_connection, job_id_for_url

    url = "https://example.com/web-smoke"
    enc = quote(url, safe="")
    jid = job_id_for_url(url)

    conn = get_connection()
    conn.execute(
        "UPDATE jobs SET location = 'Austin, TX', full_description = 'Work from home role', "
        "score_reasoning = 'Strong SQL fit', apply_error = 'needs you: Verify email code' WHERE url = ?",
        (url,),
    )
    conn.commit()

    by_id = api_client.get(f"/api/jobs/by-id/{jid}")
    assert by_id.status_code == 200
    assert by_id.json()["url"] == url
    assert by_id.json()["needs_you"] == "Verify email code"
    assert api_client.get("/api/jobs/by-id/000000000000").status_code == 404

    detail = api_client.get(f"/api/jobs/{enc}")
    assert detail.status_code == 200
    dbody = detail.json()
    assert dbody["full_description"] == "Work from home role"
    assert dbody["work_model"] == "remote"
    assert dbody["score_reasoning"] == "Strong SQL fit"
    assert dbody["apply_error"] == "needs you: Verify email code"

    assert api_client.patch(f"/api/jobs/{enc}", json={"outcome": "invalid_outcome"}).status_code == 400
    assert api_client.patch(f"/api/jobs/{enc}", json={"user_fit_score": 11, "user_score_rationale": "x"}).status_code == 400
    assert api_client.patch(f"/api/jobs/{enc}", json={"user_fit_score": 8}).status_code == 400

    patched = api_client.patch(
        f"/api/jobs/{enc}",
        json={
            "title": "Senior Analyst",
            "company": "Example Org",
            "notes": "Referral pending",
            "follow_up_at": "2026-12-01",
            "close_reason": "  Role paused  ",
            "user_fit_score": 9,
            "user_score_rationale": "Exact domain match",
        },
    )
    assert patched.status_code == 200
    pbody = patched.json()
    assert pbody["title"] == "Senior Analyst"
    assert pbody["company"] == "Example Org"
    assert pbody["notes"] == "Referral pending"
    assert pbody["follow_up_at"] == "2026-12-01"
    assert pbody["close_reason"] == "Role paused"
    assert pbody["user_fit_score"] == 9
    assert pbody["fit_score"] == 9

    cleared = api_client.patch(f"/api/jobs/{enc}", json={"clear_user_score": True, "follow_up_at": ""})
    assert cleared.status_code == 200
    assert cleared.json()["user_fit_score"] is None
    assert cleared.json()["follow_up_at"] is None


def test_undo_applied_move_restores_original_applied_stamps(api_client):
    from urllib.parse import quote

    from jobwright.database import get_connection

    url = "https://example.com/web-smoke"
    enc = quote(url, safe="")
    conn = get_connection()

    assert api_client.post(f"/api/jobs/{enc}/move", json={"to_stage": "applied"}).status_code == 200
    early_stamp = "2026-10-01T12:00:00+00:00"
    conn.execute("UPDATE jobs SET applied_at = ?, applied_manually = 1 WHERE url = ?", (early_stamp, url))
    conn.commit()

    # Accidental move back to prepare stashes applied_at in undone_applied_at.
    assert api_client.post(f"/api/jobs/{enc}/move", json={"to_stage": "prepare"}).status_code == 200
    stashed = conn.execute(
        "SELECT applied_at, undone_applied_at, undone_applied_manually FROM jobs WHERE url = ?", (url,)
    ).fetchone()
    assert stashed["applied_at"] is None
    assert stashed["undone_applied_at"] == early_stamp
    assert stashed["undone_applied_manually"] == 1

    # Moving straight back to applied restores the original timestamp and manual flag.
    restored = api_client.post(f"/api/jobs/{enc}/move", json={"to_stage": "applied"})
    assert restored.status_code == 200
    card = restored.json()["job"]
    assert card["applied_at"] == early_stamp
    assert card["applied_manually"] is True
