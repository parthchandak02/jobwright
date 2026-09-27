"""Multi-user product APIs: onboarding, admin, WhatsApp picker, quality, job_id routes."""

from __future__ import annotations

import time

import pytest

pytest.importorskip("fastapi")
jwt = pytest.importorskip("jwt")


@pytest.fixture()
def api_env(tmp_path, monkeypatch):
    from cryptography.hazmat.primitives.asymmetric import rsa
    from fastapi.testclient import TestClient

    import jobwright.users as users_mod
    from jobwright.web import auth as auth_mod
    from jobwright.web import session as session_mod

    users_root = tmp_path / "users"
    users_root.mkdir()
    (users_root / "users.yaml").write_text("admins: [boss@example.com]\nusers: []\n", encoding="utf-8")
    monkeypatch.setattr(users_mod, "USERS_ROOT", users_root)
    monkeypatch.setattr(users_mod, "REGISTRY_PATH", users_root / "users.yaml")
    monkeypatch.setenv("JOBWRIGHT_AUTH_MODE", "cloudflare")
    monkeypatch.setenv("JOBWRIGHT_CF_TEAM_DOMAIN", "t.cloudflareaccess.com")
    monkeypatch.setenv("JOBWRIGHT_CF_AUD", "aud")
    private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public = private.public_key()

    class _K:
        key = public

    monkeypatch.setattr(auth_mod, "_jwks_client", lambda team: type("J", (), {"get_signing_key_from_jwt": lambda s, t: _K()})())
    monkeypatch.setattr("jobwright.hermes_cron._run_hermes", lambda args: {"stdout": ""})
    session_mod.forget_initialized()
    from jobwright.web.app import app

    def headers(email):
        now = int(time.time())
        tok = jwt.encode({"email": email, "aud": "aud", "iss": "https://t.cloudflareaccess.com", "iat": now,
                          "exp": now + 600}, private, algorithm="RS256")
        return {"Cf-Access-Jwt-Assertion": tok}

    with TestClient(app) as client:
        yield client, headers, users_root


def test_new_login_onboards_and_owns_profile(api_env):
    client, h, root = api_env
    ann = h("ann@example.com")
    st = client.get("/api/onboarding/status", headers=ann).json()
    assert st["has_profile"] is False
    res = client.post("/api/onboarding/profile", json={"name": "Ann Lee"}, headers=ann)
    assert res.status_code == 200, res.text
    uid = res.json()["user_id"]
    assert uid == "ann"
    client.cookies.set("jobwright_user", uid)
    assert client.post("/api/onboarding/profile", json={"name": "Ann again"}, headers=ann).status_code == 409
    draft = {
        "profile": {"personal": {"full_name": "Ann Lee", "phone": "+1 415 555 0100"},
                    "experience": {"target_role": "Program manager in education"}},
        "criteria": {"summary": "Education programs", "dealbreakers": [{"label": "Sales roles"}]},
        "searches": {"queries": [{"query": "education program manager", "tier": 1}],
                     "locations": [{"location": "Oakland, CA", "remote": False}, {"location": "Remote", "remote": True}]},
    }
    st = client.post("/api/onboarding/confirm", json=draft, headers=ann).json()
    assert st["steps"]["profile"] and st["steps"]["searches"] and st["steps"]["criteria"]
    assert not st["steps"]["whatsapp"] and st["complete"] is False
    crit = client.get("/api/criteria", headers=ann).json()
    assert crit["derived"] is False and crit["criteria"]["dealbreakers"][0]["id"] == "sales_roles"
    import yaml

    searches = yaml.safe_load((root / uid / "searches.yaml").read_text())
    assert "Oakland" in searches["location"]["accept_patterns"] and "Remote" in searches["location"]["accept_patterns"]


def test_non_admin_cannot_see_admin_or_other_profiles(api_env):
    client, h, _ = api_env
    client.post("/api/onboarding/profile", json={"name": "Bo"}, headers=h("bo@example.com"))
    assert client.get("/api/admin/users", headers=h("bo@example.com")).status_code == 403
    assert client.post("/api/onboarding/profile", json={"name": "X", "emails": ["x@y.z"]},
                       headers=h("bo@example.com")).status_code == 403
    boss = h("boss@example.com")
    users = client.get("/api/admin/users", headers=boss).json()["users"]
    assert [u["user_id"] for u in users] == ["bo"] and users[0]["emails"] == ["bo@example.com"]


def test_admin_settings_and_email_binding(api_env):
    client, h, _ = api_env
    boss = h("boss@example.com")
    res = client.post("/api/onboarding/profile", json={"name": "Cy", "emails": ["cy@example.com"]}, headers=boss)
    uid = res.json()["user_id"]
    assert client.patch(f"/api/admin/users/{uid}", json={"emails": ["cy@example.com", "cy2@example.com"]},
                        headers=boss).json()["emails"] == ["cy@example.com", "cy2@example.com"]
    me = client.get("/api/me", headers=h("cy2@example.com")).json()
    assert [p["user_id"] for p in me["profiles"]] == [uid]
    assert client.put("/api/admin/settings", json={"admins": ["other@example.com"]}, headers=boss).status_code == 400
    s = client.put("/api/admin/settings", json={"ops_target": "123@lid"}, headers=boss).json()
    assert s["ops_target"] == "whatsapp:123@lid"


def test_whatsapp_chat_is_admin_managed(api_env, monkeypatch):
    client, h, _ = api_env
    di = h("di@example.com")
    client.post("/api/onboarding/profile", json={"name": "Di"}, headers=di)
    client.cookies.set("jobwright_user", "di")
    monkeypatch.setattr("jobwright.whatsapp._hermes_targets", lambda: [
        {"id": "111@g.us", "name": "111", "type": "group"}, {"id": "9@lid", "name": "Parth", "type": "dm"},
    ])
    monkeypatch.setattr("jobwright.whatsapp.bridge_status", lambda: "connected")
    monkeypatch.setattr("jobwright.whatsapp._bridge_chat", lambda jid: {
        "111@g.us": {"name": "Di job search", "participants": ["9@s.whatsapp.net"]},
    }.get(jid))
    sent = []
    monkeypatch.setattr("jobwright.whatsapp.send_test", lambda target, name="": sent.append(target))

    assert client.get("/api/whatsapp/chats", headers=di).status_code == 403
    r = client.put("/api/profile", json={"whatsapp_target": "whatsapp:222@g.us"}, headers=di)
    assert r.status_code == 403
    assert client.post("/api/whatsapp/test", json={}, headers=di).status_code == 400

    boss = h("boss@example.com")
    names = {c["name"] for c in client.get("/api/whatsapp/chats", headers=boss).json()["chats"]}
    assert {"Di job search", "Parth"} <= names
    r = client.put("/api/profile", json={"whatsapp_target": "whatsapp:111@g.us"}, headers=boss)
    assert r.status_code == 200 and r.json()["whatsapp_chat_name"] == "Di job search"

    assert client.post("/api/whatsapp/test", json={"target": "whatsapp:9@lid"}, headers=di).json()["target"] \
        == "whatsapp:111@g.us"
    assert sent == ["whatsapp:111@g.us"]
    profile = client.get("/api/profile", headers=di).json()
    assert profile["whatsapp_chat_name"] == "Di job search"


def test_job_id_routes_and_labels(api_env):
    client, h, _ = api_env
    ann = h("ann@example.com")
    client.post("/api/onboarding/profile", json={"name": "Ann"}, headers=ann)
    client.cookies.set("jobwright_user", "ann")
    res = client.post("/api/jobs", json={"url": "https://ex.com/job?a=%20b", "title": "PM", "company": "Co"},
                      headers=ann)
    assert res.status_code == 200, res.text
    job_id = res.json()["job_id"]
    assert client.get(f"/api/jobs/{job_id}", headers=ann).json()["title"] == "PM"
    res = client.patch(f"/api/jobs/{job_id}", json={"user_fit_score": 2, "user_score_reasons": ["too senior"]},
                       headers=ann)
    assert res.status_code == 200, res.text
    labels = client.get(f"/api/jobs/{job_id}/labels", headers=ann).json()["labels"]
    assert labels[0]["label_score"] == 2 and labels[0]["reasons"] == ["too senior"]
    q = client.get("/api/quality", headers=ann).json()
    assert q["labels_total"] == 1
    assert client.get("/api/jobs/000000000000", headers=ann).status_code == 404


def test_admin_costs_per_profile_admin_only(api_env, monkeypatch):
    import sqlite3
    from datetime import UTC, datetime, timedelta

    from jobwright.database import close_connection, init_db

    client, h, root = api_env
    for name in ("Ann", "Bo"):
        client.post("/api/onboarding/profile", json={"name": name}, headers=h(f"{name.lower()}@example.com"))
    monkeypatch.setenv("JOBWRIGHT_LLM_PRICES", '{"glm": [1.0, 2.0]}')
    db = root / "ann" / "jobwright.db"
    close_connection(db)
    init_db(db)
    close_connection(db)
    conn = sqlite3.connect(db)
    now = datetime.now(UTC)
    rows = [
        ((now - timedelta(days=1)).isoformat(), "accounts/fireworks/models/glm", 1_000_000, 500_000, None),
        ((now - timedelta(days=2)).isoformat(), "other", 100, 50, 0.25),
        ((now - timedelta(days=45)).isoformat(), "other", 999_999, 999_999, 9.0),
    ]
    conn.executemany("INSERT INTO llm_usage (at, model, prompt_tokens, completion_tokens, cost_usd) "
                     "VALUES (?, ?, ?, ?, ?)", rows)
    conn.commit()
    conn.close()

    assert client.get("/api/admin/costs", headers=h("ann@example.com")).status_code == 403
    data = client.get("/api/admin/costs", headers=h("boss@example.com")).json()
    by_user = {u["user_id"]: u for u in data["users"]}
    assert data["days"] == 30
    assert by_user["ann"]["total_tokens"] == 1_500_150 and by_user["ann"]["calls"] == 2
    assert by_user["ann"]["cost_usd"] == 2.25
    assert by_user["bo"]["total_tokens"] == 0 and by_user["bo"]["cost_usd"] is None
    assert data["total"]["cost_usd"] == 2.25 and data["total"]["total_tokens"] == 1_500_150
